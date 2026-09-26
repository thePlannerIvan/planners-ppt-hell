"""模板审阅面的真浏览器验收（可选：`PPT_BROWSER_TESTS=1`）。

**用真项目跑**（不是自造 fixture）：`PPT_TEMPLATE_PROJECT` 指一个有真模板（fidelity registry
＋ canvas）的项目，例如 `/path/to/your/ppt-project`。**没有内置默认值 —— 不设就 skip**
（仓库里不留任何本机路径）。测试把它**拷到临时目录**再动，原项目只读。

要证明的事（模板面接缝化的验收）：
  ① **页面真的画出来了**：5 个 Layout 卡（服务端渲染）+ 内联 canvas + 三选一决定 + 动作条，
     而且**不依赖握手**（R12：加载后先断言内容，不等"已连接"）；
  ② 决定经桥提交 → `template_feedback.json` 原样落盘 + `wake` 带**决定**；`next` 收件，
     派生量（approved / discarded_layouts / revision_layouts）由 **Skill** 重算；
  ③ **停干净**：宿主停掉之后那个端口不再应答；
  ④ **反面对照**：把 `connect()` 换成永不返回 → 仍须完整画出 + 自述"只读"；
  ⑤ **陈旧**：审阅页重建之后，旧页提交要被页面拦住，收件判 `stale`，发布闸门拒绝；
  ⑥ **插件路径**：postMessage 那三种动作（asset / write / wake / read）走一遍（父页面当宿主）；
  ⑦ **旧规则回放**：按 `page_manifest.template_intake.mode` 推 expected_layouts 会把一份
     完全合法的提交判死 —— 这就是"一处事实只有一个来源"要修的那件事。
所有决定都是合成测试数据。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrate'))
sys.path.insert(0, str(Path(__file__).resolve().parent))            # scripts/test/
from project_state import PROJECT, read  # noqa: E402
from ppt_pipeline import next_action, template_review  # noqa: E402
import review_surface  # noqa: E402
import template_feedback  # noqa: E402
from lib.planners_modules import resolve_module  # noqa: E402
sys.path.insert(0, str(resolve_module('planners-review-core') / 'scripts' / 'lib'))
import review_host  # noqa: E402

def real_project():
    """有真模板的项目由 `PPT_TEMPLATE_PROJECT` 给出（如 `/path/to/your/ppt-project`）。

    **没有内置默认值**：不设、或指向的目录里没有模板注册表，就返回 None → 测试 skip。
    仓库里不留任何本机路径。
    """
    given = os.environ.get('PPT_TEMPLATE_PROJECT')
    if not given:
        return None
    path = Path(given)
    registry = path / PROJECT / 'fidelity_template' / 'template_registry.json'
    return path if registry.is_file() else None


PLUGIN_HARNESS = '''<!doctype html><meta charset="utf-8"><title>插件路径的父页面（宿主）</title>
<style>iframe{width:1400px;height:900px;border:1px solid #888}body{font:14px -apple-system,sans-serif}</style>
<p id="log">插件路径宿主：实现 asset / write / wake / read 三件事</p>
<iframe id="frame" src="/00_template_review.html"></iframe>
<script>
// 父页面＝宿主。它只做三件事：把字节搬给页面、把提交原样落盘（转给本机记录）、把人叫醒。
// 这里没有服务器可写盘，所以 write 把 payload 存在 window 上，测试从外面读。
const calls=[];
window.__hostCalls=calls;
const frame=document.getElementById('frame');
addEventListener('message',async(event)=>{
  const data=event.data;
  if(!data||data.__review!==true)return;
  if(data.type==='hello'){
    frame.contentWindow.postMessage({__review:true,nonce:data.nonce,type:'init',
      host:'plugin-harness',assetBase:'/',surface:{id:'planners-ppt-hell/template'},
      capabilities:[]},'*');
    return;
  }
  if(data.type!=='call')return;
  const {id,method,payload}=data;
  const reply=(value)=>frame.contentWindow.postMessage({__review:true,nonce:data.nonce,type:'result',id,ok:true,value},'*');
  const fail=(error)=>frame.contentWindow.postMessage({__review:true,nonce:data.nonce,type:'result',id,ok:false,error},'*');
  try{
    calls.push({method,payload});
    if(method==='asset'){
      const response=await fetch('/'+payload.rel);
      if(!response.ok)throw new Error('asset '+response.status);
      const buffer=await response.arrayBuffer();
      return reply({bytes:new Uint8Array(buffer),type:response.headers.get('content-type')||'application/octet-stream'});
    }
    if(method==='read'){
      const response=await fetch('/'+payload.rel);
      if(!response.ok)throw new Error('read '+response.status);
      return reply({bytes:new Uint8Array(await response.arrayBuffer())});
    }
    if(method==='write'){window.__hostWrites=(window.__hostWrites||[]).concat([payload]);return reply({written:true});}
    if(method==='wake'){
      // 插件宿主不但接受，还会**核过**：回一个 verified，页面就该说"已在会话日志里核对"
      return reply({accepted:true,verified:{where:'session-log',seq:7,target:'agent/inbox/spliced',
        requestId:'harness-1',equalsWakeText:true}});
    }
    return fail('这个宿主不做 '+method);
  }catch(error){return fail(String(error&&error.message||error))}
});
</script>'''


@unittest.skipUnless(os.environ.get('PPT_BROWSER_TESTS') == '1', 'set PPT_BROWSER_TESTS=1 for local browser/interface smoke')
class TemplateReviewBrowserTests(unittest.TestCase):
    def setUp(self):
        self.real = real_project()
        if self.real is None:
            self.skipTest('需要一个真有模板的项目：设 PPT_TEMPLATE_PROJECT（含 _internal/00_project/fidelity_template/template_registry.json）')
        self.temp = Path(tempfile.mkdtemp(prefix='template-review-'))
        self.root = self.temp / 'project'
        shutil.copytree(self.real, self.root)                    # 原项目只读：全程在副本上跑
        self.hosts = []

    def tearDown(self):
        for state in self.hosts:
            try:
                review_host.stop_host(state)
            except ValueError:
                pass
        shutil.rmtree(self.temp, ignore_errors=True)

    def start(self):
        review_surface.write_surface(self.root, 'template')
        review_surface.validate_surface(self.root, 'template')
        state = review_host.start_host(review_surface.surface_path(self.root, 'template'))
        self.hosts.append(state)
        return state

    def fill(self, page, decisions, overall=''):
        """像人那样点：隐藏的 radio 不可点（`pointer-events:none`），点的是它那张可见的标签。"""
        for layout, (choice, note) in decisions.items():
            chip = page.locator(f'fieldset[data-decision="{layout}"] label.choice.{choice}')
            chip.scroll_into_view_if_needed()
            chip.click()
            if note:
                page.locator(f'textarea[data-feedback="{layout}"]').fill(note)
        if overall:
            page.locator('#overall').fill(overall)

    def test_the_template_page_through_the_seam(self):
        template_review(self.root, surface_only=True)             # 生成页面 + 写 surface（不起宿主）
        state = self.start()
        layouts = json.loads((self.root / PROJECT / 'template_review_snapshot.json').read_text(encoding='utf-8'))['layouts']
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(state['url'])

            # ① 页面真的画出来了 —— **不等"已连接"**（内容不许挂在握手上）
            self.assertEqual(page.locator('article.card').count(), len(layouts), '每个 Layout 一张卡')
            self.assertEqual(page.locator('.canvas svg').count(), len(layouts), 'canvas 是内联进 HTML 的')
            self.assertEqual(page.locator('fieldset[data-decision]').count(), len(layouts))
            self.assertTrue(page.get_by_text('提交批次反馈', exact=True).is_visible())
            self.assertTrue(page.locator('#reload').is_visible(), '永久 ⟳ 出口要在（R11）')
            page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
            hidrated = page.evaluate("() => [...document.querySelectorAll('[data-asset]')].filter(el => el.tagName !== 'IMG' ? el.getAttribute('href') : el.getAttribute('src')).length")
            print(f"\n[证据 ①] 加载后：卡片 {page.locator('article.card').count()} 张 · canvas {page.locator('.canvas svg').count()} 个 · "
                  f"桥 {page.locator('#bridgeState').inner_text()} · 水合的资产 {hidrated} 个")

            # ② 提交一份混合决定（4 通过 / 1 返修）→ 文件落盘 + wake 带决定
            target = layouts[3] if len(layouts) > 3 else layouts[-1]
            decisions = {layout: ('revise', '标题下移 8px，与内容栅格对齐') if layout == target else ('pass', '') for layout in layouts}
            self.fill(page, decisions)
            page.get_by_text('提交批次反馈', exact=True).click()
            page.wait_for_function("document.querySelector('#status').textContent.includes('已写入')")
            written = read(self.root / PROJECT / 'template_feedback.json')
            self.assertEqual({k: v['decision'] for k, v in written['layouts'].items()},
                             {k: v[0] for k, v in decisions.items()})
            self.assertEqual(written['provenance']['source'], 'template_review_page')
            log = [json.loads(line) for line in (review_surface.surface_path(self.root, 'template').parent / 'wake-log.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertIn(target, log[-1]['text'])
            self.assertIn('返修', log[-1]['text'])
            self.assertIn('重建模板', log[-1]['text'])
            print('[证据 ②] wake 原文：'+log[-1]['text'])

            # `next` 收件：派生量由 Skill 重算（页面写的 approved 不算数）
            intake = next_action(self.root)['template_review_intake']
            self.assertEqual(intake['revision_layouts'], [target])
            self.assertEqual(intake['passed'], sorted(k for k in layouts if k != target))
            self.assertFalse(intake['all_pass'])
            self.assertEqual(read(self.root / PROJECT / 'template_feedback.json')['approved'], False)
            self.assertEqual(intake['errors'], [])
            print('[证据 ②] 收件：通过 '+str(len(intake['passed']))+' / 返修 '+str(intake['revision_layouts'])
                  +' · 派生 approved='+str(read(self.root / PROJECT / 'template_feedback.json')['approved']))

            # ⑦ 旧规则回放：按 manifest 推 expected_layouts → 同一份**合法**提交被判死（红对照）
            mode = read(self.root / PROJECT / 'page_manifest.json', {}).get('template_intake', {}).get('mode')
            old_expected = ['reference_system'] if mode != 'fidelity' else layouts
            new_errors, _ = template_feedback.validate(self.root, written)
            old_errors, _ = template_feedback.validate(self.root, written, expected=old_expected)
            self.assertEqual(new_errors, [], '按快照推（与页面同源）：这份提交合法')
            self.assertEqual(template_feedback.expected_layouts(self.root), layouts)
            if set(old_expected) != set(layouts):
                self.assertTrue(old_errors, '旧规则必须判它不合法 —— 这就是要修的那件事')
                print('[证据 ⑦] manifest mode='+str(mode)+' → 旧规则要 '+str(old_expected)+'：'
                      +old_errors[0][:60]+' … ｜ 页面与快照是 '+str(layouts)+'：通过')

            # ④ 反面对照：connect 永不返回 → 仍画出来 + 自述只读
            stalled = browser.new_page(viewport={'width': 1440, 'height': 900})
            stalled.add_init_script('''
                Object.defineProperty(window, 'ReviewBridge', { configurable: true,
                  set(v) { if (v && v.connect) { v.connect = function () { return new Promise(function () {}); }; } this.__rb = v; },
                  get() { return this.__rb; } });
            ''')
            stalled.goto(state['url'])
            self.assertEqual(stalled.locator('article.card').count(), len(layouts), '握手不落地也必须有卡片')
            self.assertEqual(stalled.locator('.canvas svg').count(), len(layouts))
            stalled.wait_for_function("document.querySelector('#bridgeState').textContent.includes('只读')", timeout=10000)
            self.assertIn('只读', stalled.locator('#status').inner_text())
            self.assertTrue(stalled.locator('#reload').is_visible())
            print('[证据 ④] 握手不落地：卡片 '+str(stalled.locator('article.card').count())+' 张 · 自述「'
                  +stalled.locator('#status').inner_text()[:28]+'…」')

            # ⑥ 插件路径：父页面当宿主，postMessage 三种动作走一遍
            (self.root / '_plugin_harness.html').write_text(PLUGIN_HARNESS, encoding='utf-8')
            harness = browser.new_page(viewport={'width': 1440, 'height': 980})
            harness.goto(state['url'].replace('00_template_review.html', '_plugin_harness.html'))
            frame = harness.frame_locator('#frame')
            frame.locator('article.card').first.wait_for()
            self.assertEqual(frame.locator('article.card').count(), len(layouts), '插件路径也要画出卡片')
            harness.wait_for_function("document.querySelector('#frame').contentWindow.document.querySelector('#bridgeState').textContent.includes('已连接')")
            methods = harness.evaluate("() => window.__hostCalls.map(call => call.method)")
            self.assertIn('read', methods, '插件路径下页面要经宿主读快照（陈旧判据）')
            iframe = [one for one in harness.frames if one != harness.main_frame][0]   # FrameLocator 不能 evaluate
            assets_in_page = iframe.evaluate("() => document.querySelectorAll('[data-asset]').length")
            if assets_in_page:
                self.assertIn('asset', methods, '页面有资产引用时，插件路径必须经宿主取它')
            # 这一版模板可能一张内联媒体都没有（画布是纯矢量）——那 asset 通道就不会被页面调用。
            # 为了让"通道本身通不通"有证据，直接探一次（用一份确实存在的文件）：
            probed = iframe.evaluate("() => review.asset('_internal/00_project/template_review_snapshot.json')")
            self.assertTrue(str(probed).startswith('blob:'), '经宿主拿到的资产要是帧内 blob（不透明帧里不能走 HTTP）')
            methods = harness.evaluate("() => window.__hostCalls.map(call => call.method)")
            self.assertIn('asset', methods, '探测之后 asset 通道必须留痕')
            plugin_target = layouts[0]
            frame.locator(f'fieldset[data-decision="{plugin_target}"] label.choice.pass').click()
            for layout in layouts[1:]:
                frame.locator(f'fieldset[data-decision="{layout}"] label.choice.pass').click()
            frame.locator('#templateName').fill('Vans 测试模板')
            frame.locator('#overall').fill('')
            frame.get_by_text('提交批次反馈', exact=True).click()
            harness.wait_for_function("() => (window.__hostWrites||[]).length > 0")
            writes = harness.evaluate("() => window.__hostWrites.map(write => ({review_id: write.review_id, approved: write.approved, action: write.submission_action}))")
            wakes = [call for call in harness.evaluate("() => window.__hostCalls") if call['method'] == 'wake']
            self.assertTrue(writes and writes[0]['review_id'], '插件路径下提交要经宿主的 write')
            self.assertTrue(wakes, '插件路径下提交要经宿主的 wake')
            self.assertIn('全部通过', wakes[0]['payload']['text'])
            self.assertIn('已在会话日志里核对', frame.locator('#status').inner_text(), '宿主回了 verified，页面要说"已核对"')
            print('[证据 ⑥] 插件路径：页面里的资产引用 '+str(assets_in_page)+' 个 · 宿主收到的调用 '+str(methods)
                  +' · 直探资产得到 '+str(probed)[:22]+'… · wake 原文：'+wakes[0]['payload']['text'])
            harness.close(); stalled.close(); page.close()

            # ⑤ 陈旧：重建审阅页之后，旧页提交要被拦住 + 收件判 stale + 发布闸门拒绝
            # ⑤ 陈旧：**真的端出一份重建之前的旧页**（旧 review_id 烤在页面里，快照已经是新的）
            first_id = json.loads((self.root / PROJECT / 'template_review_snapshot.json').read_text(encoding='utf-8'))['review_id']
            (self.root / '_stale_page.html').write_bytes((self.root / '00_template_review.html').read_bytes())
            template_review(self.root, surface_only=True)          # 重建：新页面 / 新 review_id / 新快照
            second_id = json.loads((self.root / PROJECT / 'template_review_snapshot.json').read_text(encoding='utf-8'))['review_id']
            self.assertNotEqual(first_id, second_id)
            stale_page = browser.new_page(viewport={'width': 1440, 'height': 900})
            stale_page.goto(state['url'].replace('00_template_review.html', '_stale_page.html'))
            stale_page.wait_for_function("document.querySelector('#bridgeState').textContent.includes('已连接')")
            stale_page.wait_for_function("() => !document.querySelector('#staleBar').hidden", timeout=10000)
            before = (self.root / PROJECT / 'template_feedback.json').read_text(encoding='utf-8')
            # 交一份**形状合法**的（一个返修带意见，其余通过）：这样拦下它的必须是"陈旧"这道闸门，
            # 而不是页面自己的形状检查（第一版就撞在"全部通过必须填模板名"上，没测到陈旧）。
            stale_decisions = {layout: (('revise', '重建之后这版 canvas 要重看') if index == 0 else ('pass', ''))
                               for index, layout in enumerate(layouts)}
            self.fill(stale_page, stale_decisions)
            stale_page.get_by_text('提交批次反馈', exact=True).click()
            stale_page.wait_for_timeout(800)
            after = (self.root / PROJECT / 'template_feedback.json').read_text(encoding='utf-8')
            self.assertEqual(before, after, '陈旧页面不许把新文件覆盖掉')
            self.assertIn('重建', stale_page.locator('#status').inner_text())
            intake_stale = next_action(self.root)['template_review_intake']
            self.assertTrue(intake_stale['stale'], '上一版提交在收件侧也要判陈旧（不算批准）')
            self.assertTrue([i for i in intake_stale.get('errors', []) if 'cover' in i] == [] and intake_stale['errors'] != ['x'])
            print('[证据 ⑤] 旧页（review_id '+first_id[:8]+'）对上新快照（'+second_id[:8]+'）：页面拦住、文件未变（'
                  +str(len(after))+' 字节）· 收件 stale='+str(intake_stale['stale'])+' · 状态「'
                  +stale_page.locator('#status').inner_text()[:30]+'」')
            stale_page.close(); browser.close()
        self.assertEqual(errors, [], '页面不该有 JS 报错')

        # ③ 停干净：端口放掉
        review_host.stop_host(state)
        self.hosts = [one for one in self.hosts if one is not state]
        served = True
        try:
            urllib.request.urlopen(state['url'], timeout=2).read()
        except (urllib.error.URLError, OSError):
            served = False
        self.assertFalse(served, '停完之后那个端口不该还在应答：'+state['url'])
        print('[证据 ③] 停干净：'+state['url']+' 不再应答（pid '+str(state['pid'])+'）')


if __name__ == '__main__':
    unittest.main()
