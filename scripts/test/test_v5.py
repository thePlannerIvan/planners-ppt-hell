"""v5 behavioral regressions. Synthetic approvals are isolated test fixtures only."""
import json
from pathlib import Path
from datetime import datetime, timezone
import re
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'orchestrate'))
from canvas_frame import FRAME_H_INT, FRAME_VIEWBOX, FRAME_W_INT
from project_state import (CONTENT, PNG, PROJECT, REVIEW, SVG, TEMPLATE_REVIEW_SNAPSHOT,
                           VALIDATION, approvals, approved, content, digest, images,
                           manifest, read, review_snapshot, sha, sync, template_version,
                           versions, write)
from ppt_pipeline import next_action, make_review, resolve, export, unresolved
from review_feedback import archive_consumed, consume
from validate_svg_layout import validate_file
S=Path(__file__).resolve().parents[1]

class V5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'project'
        src=Path(self.tmp.name)/'source.md';src.write_text('# Demo\nEvidence 42% with qualification.\n')
        subprocess.run([sys.executable,str(S/'init_svg_project.py'),str(self.root),'--source',str(src)],check=True,capture_output=True)
        write(self.root/CONTENT,{'project':'Test','pages':[{'page_key':k,'title':k,'content':'42% with qualification','source_assets':[]} for k in ['alpha','omega']]})
        sync(self.root)
        for k in ['alpha','omega']:self.svg(k)
        self.seal()
    def tearDown(self):self.tmp.cleanup()
    def svg(self,k,text='Evidence'):
        (self.root/SVG/(k+'.svg')).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" viewBox="{FRAME_VIEWBOX}"><rect width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#FFFFFF"/><text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">'+text+'</text></svg>')
    def seal(self):
        ins={}
        for k,v in versions(self.root).items():
            png=self.root/PNG/(k+'.png');png.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(192,108),'white').save(png)
            rec={'version':v,'errors':0,'png_sha256':sha(png),'validator':{}}
            write(self.root/VALIDATION/(k+'.json'),rec);ins[k]={'render_token':digest(rec),'note':'Synthetic test fixture','first_glance':'fixture focal element','design_check':'fixture rule check','position':'x=120,y=150,w=400,h=80','verdict':'clean','must_fix':False}
        write(self.root/VALIDATION/'inspections.json',ins)
    def payload(self):
        snap=make_review(self.root)
        return {'review_id':snap['review_id'],'pages':{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in snap['versions']},'overall_feedback':''}
    def submit(self,payload,stamp=None):
        """按新接缝走一遍：**页面经宿主写整份状态**（宿主原样落盘），Skill 侧再**收件**。

        写反馈的人从 review_server 变成了页面，所以旧的一步 `save_feedback` 拆成两个口：
        页面写文件、`consume`（模型这一侧）校验并规范化。测试照这条接缝驱动，
        校验失败（形状/绑定）仍然在这里抛 ValueError —— 与以前一样是硬失败。
        """
        document={**payload,'provenance':{'source':'review_page','transport':'http',
            'submitted_at':stamp or datetime.now(timezone.utc).isoformat()}}
        write(self.root/REVIEW/'feedback.json',document)
        return consume(self.root)

    def review_data(self):
        """把审阅页里那份 `const data={…}` 读出来——页面看到的就是它。"""
        page=(self.root/'02_visual_review.html').read_text(encoding='utf-8')
        match=re.search(r'const data=(\{.*?\});\n',page,re.S)
        self.assertIsNotNone(match,'审阅页里应有 const data={…}')
        return json.loads(match.group(1))
    def page_data(self,key):
        return next(item for item in self.review_data()['pages'] if item['key']==key)
    def test_no_layout_or_batch_gate(self):
        m=manifest(self.root);self.assertNotIn('batch_size',m);self.assertFalse((self.root/'_internal/01_layout_plan').exists());self.assertEqual(next_action(self.root)['state'],'VISUAL_REVIEW')
    def test_stable_ids_reorder_without_renumber(self):
        c=content(self.root);c['pages'].reverse();write(self.root/CONTENT,c);self.assertEqual(sync(self.root)['pages'][0]['page_key'],'omega')
    def test_old_projects_rejected_explicitly(self):
        m=manifest(self.root);m['version']='4.0';write(self.root/PROJECT/'page_manifest.json',m)
        with self.assertRaisesRegex(ValueError,'older workflow'):manifest(self.root)
    def test_metadata_not_required_for_editable_svg(self):
        r=validate_file(self.root/SVG/'alpha.svg');self.assertFalse(any('METADATA' in x['code'] or 'LAYOUT' in x['code'] for x in r['issues']))
    def test_export_without_review_reminds_instead_of_blocking(self):
        # 导出不再要求"整套人工审阅已批准"（references/workflow/07_visual_review.md）。
        # 导出时跑检查画面（与转换 PPT 同一套几何算法），没审过就提醒一次。
        out=export(self.root)
        self.assertFalse(out['reviewed']);self.assertIn('review_reminder',out)
        self.assertTrue((self.root/'final_deck.pptx').is_file())
        self.assertEqual(export(self.root)['pptx_sha256'],out['pptx_sha256'])
    def test_human_approval_bound_to_actual_version(self):
        p=self.payload();self.submit(p);self.assertTrue(approved(self.root));self.svg('alpha','Changed');self.assertFalse(approved(self.root))
    def test_stale_submission_does_not_count_and_is_reported(self):
        """陈旧提交的归宿变了，判据没变。

        以前是 **review_server 在写盘之前**拒绝（409）；现在写盘的是宿主、它不解释内容，
        所以拒绝落在两处：① **页面提交前**拿当前快照比 review_id，对不上就不写
        （人在页面上看到「这一页已更新，先复核」，见浏览器冒烟）；② **Skill 收件时**
        认出它绑的是上一版，**不算批准**、也不按当前页集追究，并在 `next` 里说出来。
        人写的字不删——它仍是模型要继续处理的 items。
        """
        p=self.payload();self.svg('alpha','Changed');self.seal();make_review(self.root)
        intake=self.submit(p)
        self.assertTrue(intake['stale'])
        self.assertFalse(approved(self.root))
        self.assertTrue(next_action(self.root)['review_intake']['stale'])
        self.assertEqual(read(self.root/REVIEW/'feedback.json')['pages']['omega']['decision'],'approved')
    def test_template_review_must_have_seen_the_current_version(self):
        """模板审阅此前只有一个写死在 HTML 里的摘要，旧标签页能批准新版本。

        这条判据随接缝搬家：以前在 `review_server.template_review_stale_error`，现在是
        `template_feedback.stale_reason`（收件层）——**断言一条没少**。
        """
        from template_feedback import stale_reason as template_review_stale_error
        page=self.root/'00_template_review.html';page.write_text('<html>r1</html>',encoding='utf-8')
        write(self.root/PROJECT/TEMPLATE_REVIEW_SNAPSHOT,
              {'review_id':'r1','template_version':template_version(self.root),'html_sha256':sha(page),'layouts':['content_base']})
        self.assertEqual(template_review_stale_error(self.root,{'review_id':'r1'}),'')
        self.assertIn('stale',template_review_stale_error(self.root,{'review_id':'r0'}))
        page.write_text('<html>r2</html>',encoding='utf-8')
        self.assertIn('stale',template_review_stale_error(self.root,{'review_id':'r1'}))
        (self.root/PROJECT/TEMPLATE_REVIEW_SNAPSHOT).unlink()
        self.assertIn('stale',template_review_stale_error(self.root,{'review_id':'r1'}))
    def test_unchanged_page_retains_approval(self):
        self.submit(self.payload());self.svg('alpha','Changed');self.seal();self.assertEqual(set(approvals(self.root)),{'omega'})
    def test_png_tamper_invalidates_approval(self):
        self.submit(self.payload());Image.new('RGB',(192,108),'red').save(self.root/PNG/'alpha.png');self.assertFalse(approved(self.root))
    def test_source_change_invalidates_review(self):
        self.submit(self.payload());(self.root/PROJECT/'source/source.md').write_text('New facts');self.assertFalse(approved(self.root))
    def test_html_change_invalidates_approval(self):
        self.submit(self.payload());p=self.root/'02_visual_review.html';p.write_text(p.read_text()+'<!-- changed -->');self.assertFalse(approved(self.root))
    def test_feedback_overrides_approved(self):
        p=self.payload();p['pages']['alpha']['feedback']='Rearrange the whole page';self.submit(p);f=read(self.root/REVIEW/'feedback.json');self.assertEqual(f['pages']['alpha']['decision'],'revise');self.assertEqual(next_action(self.root)['state'],'CREATE')
    def test_feedback_needs_actual_change_to_resolve(self):
        p=self.payload();p['pages']['alpha']['feedback']='Change';self.submit(p);fid=read(self.root/REVIEW/'feedback.json')['items'][0]['id']
        with self.assertRaisesRegex(ValueError,'changed artifact'):resolve(self.root,fid,'Done')
        self.svg('alpha','Changed');resolve(self.root,fid,'Changed headline');self.seal();make_review(self.root)
    def test_feedback_all_items_block_review(self):
        p=self.payload();p['pages']['alpha']['feedback']='Change';p['pages']['omega']['feedback']='Change';self.submit(p)
        with self.assertRaisesRegex(ValueError,'every submitted'):make_review(self.root)
    def test_region_bounds_validated(self):
        p=self.payload();p['pages']['alpha']['annotations']=[{'x':.9,'y':0,'w':.5,'h':.2,'text':'Fix'}]
        with self.assertRaisesRegex(ValueError,'inside'):self.submit(p)
    def test_upload_path_traversal_blocked(self):
        p=self.payload();p['pages']['alpha']['assets']=[{'asset_key':'new','operation':'add','path':'../source.md','fit':'contain','ratio':'original','anchor':'center'}]
        with self.assertRaisesRegex(ValueError,'outside'):self.submit(p)
    def test_new_image_reaches_creation_feedback(self):
        p=self.payload();image=self.root/REVIEW/'uploads/alpha/test.png';image.parent.mkdir(parents=True);Image.new('RGB',(20,20),'blue').save(image)
        p['pages']['alpha']['assets']=[{'asset_key':'new','operation':'add','path':image.relative_to(self.root).as_posix(),'fit':'cover','ratio':'5:4','anchor':'top'}]
        self.submit(p);f=read(self.root/REVIEW/'feedback.json');self.assertEqual(f['items'][0]['assets'][0]['ratio'],'5:4')
    def test_source_assets_must_be_accounted_for(self):
        write(self.root/PROJECT/'source/source_assets.json',{'assets':[{'asset_id':'asset_001'}]})
        with self.assertRaisesRegex(ValueError,'not accounted'):content(self.root)
    def test_image_alignment_covers_the_whole_nine_grid(self):
        """对齐的九个格子都要能提交。

        控件是九宫格（CSS `object-position` 本来就是二维的），旧判据只收五个（正上下左右＋居中）：
        四个角在页面上点得到、提交却被退。这一条把"控件上的格子"和"服务端收的值"钉在一起。
        """
        assets=[]
        for anchor in ['center','top','bottom','left','right',
                       'top-left','top-right','bottom-left','bottom-right']:
            path=self.root/REVIEW/f'uploads/alpha/{anchor}.png'
            path.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(20,20),'blue').save(path)
            assets.append({'asset_key':anchor,'operation':'add','path':path.relative_to(self.root).as_posix(),
                           'fit':'cover','ratio':'1:1','anchor':anchor})
        p=self.payload();p['pages']['alpha']['assets']=assets
        self.submit(p)
        saved=read(self.root/REVIEW/'feedback.json')['pages']['alpha']['assets']
        self.assertEqual(sorted(a['anchor'] for a in saved),
                         ['bottom','bottom-left','bottom-right','center','left','right','top','top-left','top-right'])
    def test_unknown_image_alignment_is_rejected(self):
        """九宫格之外的值仍然要挡住（保住上一条的边界）。"""
        path=self.root/REVIEW/'uploads/alpha/one.png';path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(20,20),'blue').save(path)
        p=self.payload()
        p['pages']['alpha']['assets']=[{'asset_key':'new','operation':'add','path':path.relative_to(self.root).as_posix(),
                                        'fit':'cover','ratio':'1:1','anchor':'middle'}]
        with self.assertRaisesRegex(ValueError,'Invalid anchor'):self.submit(p)
    def test_review_page_is_regenerated_when_the_review_template_changes(self):
        """审阅页模板升级之后，已经生成过的页面要重出。

        `review_current` 只比"磁盘上的页面 vs 快照"，而这两样是一起写下的 —— 模板换了以后照样
        互相印证，只看它就会把一版按旧模板生成的页面当成最新的（2026-10-06 真人报的右栏问题就是
        这样卡住的：模板改了，项目里的页面还是旧的）。所以快照里记模板与令牌表的指纹。
        """
        from generate_review_html import template_fingerprint
        first=make_review(self.root)
        self.assertEqual(review_snapshot(self.root)['template_sha256'],template_fingerprint())
        self.assertEqual(make_review(self.root)['review_id'],first['review_id'],'模板没变就不重出（幂等）')
        snapshot=read(self.root/REVIEW/'snapshot.json');snapshot.pop('template_sha256')
        write(self.root/REVIEW/'snapshot.json',snapshot)         # ＝"这份页面不是按当前模板生成的"
        self.assertNotEqual(make_review(self.root)['review_id'],first['review_id'],'模板换了就必须重出')
        self.assertEqual(review_snapshot(self.root)['template_sha256'],template_fingerprint())
    def test_missing_image_and_stretch_rejected(self):
        svg=self.root/SVG/'alpha.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="missing.png"/></svg>')
        with self.assertRaisesRegex(ValueError,'Missing image'):images(self.root,svg)
    def test_page_content_may_be_empty_for_a_text_free_screen(self):
        """一屏可以只有画面：`content` 允许为空，页面的名字（title）仍然必填。"""
        write(self.root/CONTENT,{'project':'Test','pages':[
            {'page_key':'alpha','title':'纯画面页','content':'','source_assets':[]},
            {'page_key':'omega','title':'有字页','content':'42% with qualification','source_assets':[]}]})
        self.assertEqual(content(self.root)['pages'][0]['content'],'')
        self.assertEqual([p['page_key'] for p in sync(self.root)['pages']],['alpha','omega'])
        broken=read(self.root/CONTENT);broken['pages'][0]['title']='   ';write(self.root/CONTENT,broken)
        with self.assertRaisesRegex(ValueError,'title required'):content(self.root)
    def test_empty_page_defect_is_neither_text_nor_image(self):
        """空页判据是「既无文字也无图」，不是元素计数。

        元素计数（旧 `visible < 3`）把「一整屏就是一张图」和「只有标题的一页」都误报成空页；
        真正空白的页面仍然被标出，且仍然是告警、不阻断。
        """
        head=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" '
              f'viewBox="{FRAME_VIEWBOX}">')
        def report(body):
            (self.root/SVG/'probe.svg').write_text(head+body+'</svg>',encoding='utf-8')
            return validate_file(self.root/SVG/'probe.svg')
        def codes(r):return [i['code'] for i in r['issues']]
        blank=report('')
        self.assertIn('EMPTY_SLIDE',codes(blank))
        self.assertEqual([i['severity'] for i in blank['issues'] if i['code']=='EMPTY_SLIDE'],['warning'])
        self.assertEqual(blank['summary']['errors'],0)
        Image.new('RGB',(40,20),'white').save(self.root/SVG/'pic.png')
        picture=report('<image href="pic.png" x="0" y="0" width="1920" height="1080" preserveAspectRatio="xMidYMid slice"/>')
        self.assertNotIn('EMPTY_SLIDE',codes(picture))
        title=report('<text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">Title</text>')
        self.assertNotIn('EMPTY_SLIDE',codes(title))
    def test_check_cache_evidence_token_changes_on_new_version(self):
        old=read(self.root/VALIDATION/'alpha.json');self.svg('alpha','New');self.seal();self.assertNotEqual(digest(old),digest(read(self.root/VALIDATION/'alpha.json')))
    def test_regenerated_review_carries_the_note_of_a_reworked_page(self):
        """被重出的那一页：上一轮的意见必须随新页面带回来。

        页面每次提交写的是整份状态（宿主原样覆盖 feedback.json），所以旧意见唯一的留存方式
        是在重出审阅页时带回页面。没有这一条，「人写了意见 → 模型改完 → 人再打开审阅页」
        这条路上那个人的字就没了。
        """
        p=self.payload();p['pages']['alpha']['feedback']='把标题下移，别压到图'
        p['pages']['alpha']['annotations']=[{'x':.1,'y':.1,'w':.2,'h':.2,'text':'这块要留白'}]
        self.submit(p)
        self.svg('alpha','Reworked');self.seal()
        resolve(self.root,read(self.root/REVIEW/'feedback.json')['items'][0]['id'],'标题下移 40px，右侧留白')
        make_review(self.root)
        alpha=self.page_data('alpha')
        self.assertEqual(alpha['previousFeedback'],'把标题下移，别压到图')
        self.assertEqual(alpha['previousDecision'],'revise')
        self.assertEqual([a['text'] for a in alpha['previousAnnotations']],['这块要留白'])
        self.assertEqual(alpha['decision'],'pending')   # 待复核：不是「已批准」
        # 未变的页面不该带上一轮的意见（它的批准由 approvals() 原样保留）。
        omega=self.page_data('omega')
        self.assertNotIn('previousFeedback',omega)
        self.assertEqual(omega['decision'],'approved')
    def test_next_reports_the_intake_without_clobbering_the_unresolved_items(self):
        """收件信息与「待处理条目」不能同名。

        `_next_action` 的 CREATE 分支用 `feedback` 装还没处理完的条目；收件状态如果也叫
        `feedback`，就会把那串条目盖掉——模型于是看不到自己还要改什么。
        """
        p=self.payload();p['pages']['alpha']['feedback']='标题太靠上'
        # 页面写（宿主原样落盘），模型这一侧**只**跑 `next` —— 收件发生在这一步
        write(self.root/REVIEW/'feedback.json',{**p,'provenance':{'source':'review_page','transport':'http',
            'submitted_at':'2026-09-26T00:00:00.000Z'}})
        result=next_action(self.root)
        self.assertEqual(result['state'],'CREATE')
        self.assertEqual([item['pages'] for item in result['feedback']],[['alpha']],'待处理条目必须还在')
        self.assertFalse(result['review_intake']['stale'])
        self.assertTrue(result['review_intake']['archived'].endswith('round-01.json'))

    def test_a_resolved_item_never_comes_back_and_a_new_wording_still_does(self):
        """意见的生命周期：`resolve` 之后那条意见结束，同一页的同一句话**永远不再成为待办**。

        两层都钉：① 页面不再预填上一轮的东西（所以正常路径根本不会重发那句话）；
        ② 万一同一页同一句话又提交上来（旧页面、人手粘贴、历史遗留），Skill 侧按内容身份收下，
        **不生成条目**；但**换了说法**就是新意见，仍要生成条目（不许过度抑制）。
        """
        p=self.payload();p['pages']['alpha']['feedback']='底部没对齐'
        first=self.submit(p)
        self.assertEqual([i['pages'] for i in first['document']['items']],[['alpha']])
        resolved_id=first['document']['items'][0]['id']
        self.svg('alpha','Reworked');self.seal()
        resolve(self.root,resolved_id,'把底部对齐了')
        self.assertEqual(unresolved(self.root),[])
        # ① 同一页、同一句话再来一次 → 不生成条目，且说出来（不是静默丢掉）
        again=self.submit({**self.payload(),'pages':{**{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in versions(self.root)},
                                                      'alpha':{'decision':'revise','feedback':'底部没对齐','annotations':[],'assets':[]}}})
        self.assertEqual(again['document']['items'],[],'同一句话不该第二次成为待办')
        self.assertEqual([s['page'] for s in again['suppressed']],['alpha'])
        self.assertTrue(again['document']['pages']['alpha']['already_resolved'])
        self.assertEqual(unresolved(self.root),[])
        # ② 换了说法 → 仍然是新意见，必须生成条目（不许过度抑制）
        third=self.submit({**self.payload(),'pages':{**{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in versions(self.root)},
                                                      'alpha':{'decision':'revise','feedback':'底部还是差 6 像素','annotations':[],'assets':[]}}})
        self.assertEqual([i['pages'] for i in third['document']['items']],[['alpha']],'换一种说法仍是新意见')
        self.assertEqual([i['pages'] for i in unresolved(self.root)],[['alpha']])

    def test_a_whole_deck_approval_leaves_no_items_and_next_can_export(self):
        """整套批准之后状态里不存在未决条目，`next` 应当报可以导出。"""
        p=self.payload();p['pages']['alpha']['feedback']='换个说法的新意见'
        self.submit(p)
        item=read(self.root/REVIEW/'feedback.json')['items'][0]
        self.svg('alpha','Reworked');self.seal()
        resolve(self.root,item['id'],'改完了')
        self.submit({**self.payload(),'pages':{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in versions(self.root)}})
        written=read(self.root/REVIEW/'feedback.json')
        self.assertEqual(written['items'],[],'整套批准后不该还有条目')
        self.assertEqual(unresolved(self.root),[])
        self.assertTrue(approved(self.root))
        self.assertEqual(next_action(self.root)['state'],'EXPORT','整套批准之后 next 报可以导出')

    def test_a_resolved_round_does_not_come_back_as_a_new_todo(self):
        """同一句话不该第二次成为待办。

        上一轮的意见在新审阅页上只是**只读上下文**，不进 `feedback/annotations/assets`；
        所以「整份状态里那一页是空的」（人一次点击就批准）不会再生出一条与上一轮相同的 item。
        这里把「上一轮那条已经 resolve 过」也钉住：resolve 之后 unresolved 必须干净，
        下一轮的空提交也仍然干净。
        """
        p=self.payload();p['pages']['alpha']['feedback']='标题太靠上'
        first=self.submit(p)
        self.assertEqual([i['pages'] for i in first['document']['items']],[['alpha']])
        resolved_id=first['document']['items'][0]['id']
        self.svg('alpha','Reworked');self.seal()
        resolve(self.root,resolved_id,'已下移 40px')
        self.assertEqual(unresolved(self.root),[])
        # 下一轮：页面不预填上一轮的东西 → 整份状态里那页是空的（等价于"一次点击就批准"）
        second=self.submit({**self.payload(),'pages':{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in versions(self.root)}})
        self.assertEqual(second['document']['items'],[],'不再产生重复条目')
        self.assertEqual(unresolved(self.root),[])
        self.assertEqual(read(self.root/REVIEW/'feedback.json')['pages']['alpha']['decision'],'approved')

    def test_every_consumed_round_is_archived(self):
        """每一轮被模型读到的反馈都留档：宿主是整份覆盖写同一个文件的，Skill 只有收件这一个时机。"""
        first=self.payload();first['pages']['alpha']['feedback']='标题太靠上'
        intake=self.submit(first)
        history=self.root/REVIEW/'history'
        self.assertTrue(intake['archived'].endswith('history/round-01.json'))
        archived=json.loads((history/'round-01.json').read_text(encoding='utf-8'))
        self.assertEqual(archived['pages']['alpha']['feedback'],'标题太靠上')
        self.assertEqual(archived['review_id'],first['review_id'])
        # 同一轮被再收一次（模型多跑几次 next）：不重复留档，也不换条目的 id。
        again=consume(self.root)
        self.assertEqual(again['archived'],'')
        self.assertEqual([i['id'] for i in again['document']['items']],
                         [i['id'] for i in intake['document']['items']])
        self.assertEqual(sorted(p.name for p in history.glob('round-*.json')),['round-01.json'])
        # 页面按意见重出这一页，人再提交 → 第二轮（round-02），两轮都在。
        self.svg('alpha','Reworked');self.seal()
        resolve(self.root,read(self.root/REVIEW/'feedback.json')['items'][0]['id'],'已下移')
        make_review(self.root)
        second=self.submit({**self.payload(),'pages':{k:{'decision':'approved','feedback':'','annotations':[],'assets':[]} for k in versions(self.root)}})
        self.assertTrue(second['archived'].endswith('history/round-02.json'))
        self.assertEqual(sorted(p.name for p in history.glob('round-*.json')),['round-01.json','round-02.json'])
    def test_archive_does_not_write_the_same_round_twice(self):
        first=self.submit(self.payload())
        self.assertEqual(archive_consumed(self.root,first['document']),None,'同一提交时刻不重复留档')
        self.assertEqual(sorted(p.name for p in (self.root/REVIEW/'history').glob('round-*.json')),['round-01.json'])
        self.assertIsNotNone(archive_consumed(self.root,{**first['document'],'provenance':{**first['document']['provenance'],'submitted_at':'later'}}))

    def test_asset_records_carry_a_short_version_for_cache_busting(self):
        """页内素材是原地替换的，src 必须带内容版本，否则浏览器给的是旧图。"""
        picture=self.root/SVG/'photo.png';Image.new('RGB',(40,20),'green').save(picture)
        (self.root/SVG/'alpha.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" viewBox="{FRAME_VIEWBOX}"><rect width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#FFFFFF"/><image href="photo.png" x="0" y="0" width="200" height="100" preserveAspectRatio="xMidYMid meet"/></svg>')
        self.seal();make_review(self.root)
        asset=self.page_data('alpha')['assets'][0]
        self.assertEqual(asset['version'],sha(picture)[:12])
        self.assertEqual(asset['version'],str(asset['sha256'])[:12])
        Image.new('RGB',(40,20),'blue').save(picture)      # 同名原地替换
        self.seal();make_review(self.root)
        self.assertEqual(self.page_data('alpha')['assets'][0]['version'],sha(picture)[:12])
        self.assertNotEqual(asset['version'],self.page_data('alpha')['assets'][0]['version'])

if __name__=='__main__':unittest.main()
