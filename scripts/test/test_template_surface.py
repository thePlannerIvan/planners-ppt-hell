"""模板审阅面（`layout_id`）的回归网 —— 这个面接缝之前**只有服务器的生命周期测试**。

分两层，别混：
  · 这一份是**机制**（surface 落地 / 页面结构 / 收件矩阵 / 幂等 / 陈旧 / 无插件宿主跑通），
    用的是自造的最小 fidelity **夹具**（明确标注：它不是"真项目"）；
  · **结论**那一层用真项目跑，见 `test_template_review_browser.py`（它拷一份用户项目区的真项目，
    在副本上跑，原项目只读）——夹具证明不了"真项目的模板真能审"。

这个面与页面审阅面**逐条独立判过**（R10）：单位是 `layout_id`、决定词表是 pass/discard/revise、
粒度是整批、不声明 `asset-upload`、`watch` 盯的是快照（重建即整页作废，没有"原地换图"）。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrate'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_state import PROJECT, TEMPLATE_REVIEW_SNAPSHOT, read, sha, write  # noqa: E402
from ppt_pipeline import template_review  # noqa: E402
import review_surface  # noqa: E402
import template_feedback  # noqa: E402
from lib.planners_modules import resolve_module  # noqa: E402
sys.path.insert(0, str(resolve_module('planners-review-core') / 'scripts' / 'lib'))
import review_host  # noqa: E402

CANVAS = ('<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" data-template-canvas-version="v?">'
          '<rect x="0" y="0" width="1920" height="1080" fill="#fff"/>'
          '<text x="120" y="200" font-size="48">{title}</text></svg>')


class TemplateFixture(unittest.TestCase):
    """最小 fidelity 夹具：**造出来的**，只用来测机制（结论用真项目跑）。"""

    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix='template-surface-'))
        self.root = self.temp / 'project'
        project = self.root / PROJECT
        (project / 'fidelity_template' / 'layout_canvases').mkdir(parents=True)
        self.layouts = ['content_base', 'closing_dark']
        registry = {'layouts': {
            layout: {'canvas_file': f'layout_canvases/{layout}.svg',
                     'required_components': ['title'], 'optional_components': []}
            for layout in self.layouts}}
        write(project / 'fidelity_template' / 'template_registry.json', registry)
        for index, layout in enumerate(self.layouts):
            (project / 'fidelity_template' / 'layout_canvases' / f'{layout}.svg').write_text(
                CANVAS.replace('{title}', f'Layout {index + 1}'), encoding='utf-8')
        write(project / 'template_profile.json', {'structural_extraction': {'assets': [], 'native_shapes': []}})
        write(project / 'template_asset_registry.json', {'reviewed_source_ids': []})

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def generate(self):
        return template_review(self.root, surface_only=True)

    def document(self, decisions=None, action='submit_batch', name='', overall='', review_id=None):
        snapshot = read(self.root / PROJECT / TEMPLATE_REVIEW_SNAPSHOT, {})
        picks = decisions or {layout: ('pass', '') for layout in self.layouts}
        return {
            'review_id': review_id if review_id is not None else snapshot.get('review_id'),
            'submission_action': action, 'approved': True, 'all_approved': True,
            'template_name': name, 'overall_feedback': overall,
            'layouts': {layout: {'approved': choice == 'pass', 'decision': choice, 'custom_feedback': note}
                        for layout, (choice, note) in picks.items()},
            'provenance': {'source': 'template_review_page', 'transport': 'postmessage',
                           'submitted_at': '2026-09-26T00:00:00+00:00'},
        }

    def submit(self, document):
        write(template_feedback.feedback_path(self.root), document)
        return template_feedback.consume(self.root)


class TemplateSurfaceTests(TemplateFixture):
    def test_the_surface_passes_the_public_validator_and_keeps_the_two_baselines(self):
        self.generate()
        self.assertTrue(review_surface.validate_surface(self.root, 'template'), '公共件校验器必须认这份 surface')
        document = review_surface.surface_document(self.root, 'template')
        self.assertEqual(document['id'], 'planners-ppt-hell/template')
        self.assertEqual(document['entry'], '00_template_review.html')
        # R2：`feedback` / `watch` 相对 **surface 文件**，`dir` / `entry` 相对"被 serve 的那棵树"
        self.assertEqual(document['feedback'], 'template_feedback.json')
        self.assertEqual(document['watch'], ['template_review_snapshot.json'])
        self.assertEqual(document['dir'], '../..')
        # R10：这个面的两条独立判定（与页面审阅**不同**，理由写在 review_surface.TEMPLATE）
        self.assertEqual(document['capabilities'], [], '模板审阅是只读对照 + 决定 + 命名，没有上传需求')
        self.assertNotIn('{unit}', document['wake']['text'], '粒度是整批，没有逐单位唤醒')
        feedback = review_surface.feedback_path(self.root, 'template')
        self.assertEqual(feedback, self.root / PROJECT / 'template_feedback.json',
                         'feedback 相对 surface 文件，解析回来必须还是老位置（对外语义不变）')
        self.assertEqual(review_surface.surface_path(self.root, 'template').parent, feedback.parent)

    def test_the_entry_leaves_a_bare_injection_point_and_no_host_knowledge(self):
        self.generate()
        page = (self.root / '00_template_review.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('{{REVIEW_BRIDGE}}'), 1, '注入点只能有一个（宿主 replaceAll）')
        self.assertIn('\n{{REVIEW_BRIDGE}}\n', page, 'R3：裸标记必须独占一行')
        self.assertNotIn('src="{{REVIEW_BRIDGE}}"', page, '塞进 src="" 里会被整段替换撑破（G-18）')
        self.assertNotIn('review-bridge.js', page, 'R4：页面不放桥的副本')
        self.assertNotIn('src="/_internal', page, '资产引用不许写绝对路径（那是不透明帧里的宿主 origin）')
        self.assertNotIn('/_internal/00_project/template_visuals/', page.replace('data-asset="', '').replace('src="', ''),
                         '资产一律走 data-asset / 相对地址，由页面经桥取')
        # R11/R13：永久 ⟳ 与"桥不是氧气"的三件套
        self.assertIn('id="reload"', page)
        self.assertIn('BRIDGE_TIMEOUT_MS', page, '握手要有上限')
        self.assertIn('只读', page, '连不上要在页面上说出来')
        self.assertEqual(page.count('localStorage'), 0, '不透明源里顶层读存储会直接抛')
        self.assertNotIn('window.port', page)
        self.assertNotIn('fetch(\'/template-feedback\'', page, '旧的服务器路由不许再出现（那条服务器已退役）')

    def test_every_layout_card_is_server_rendered(self):
        self.generate()
        page = (self.root / '00_template_review.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('<article class="card">'), len(self.layouts), '每个 Layout 一张卡')
        for layout in self.layouts:
            self.assertIn(f'data-decision="{layout}"', page)
            self.assertIn(f'data-feedback="{layout}"', page)
        self.assertEqual(page.count('<svg'), len(self.layouts), 'canvas 是内联进 HTML 的（不靠 JS 才画得出来）')

    def test_the_host_serves_the_page_and_stops_clean(self):
        """无插件独立跑通（不启浏览器）：serve → 注入桥 → 页面内容在 → 停干净。"""
        self.generate()
        state = None
        try:
            state = review_surface.open_review(self.root, open_browser=False, name='template')
            with urllib.request.urlopen(state['url'], timeout=5) as response:
                body = response.read().decode('utf-8')
            self.assertNotIn('{{REVIEW_BRIDGE}}', body, '宿主必须把注入点换掉')
            self.assertIn('/__review/bridge.js', body)
            self.assertEqual(body.count('<article class="card">'), len(self.layouts))
            self.assertEqual(review_host.host_alive(review_surface.surface_path(self.root, 'template'))['pid'], state['pid'])
        finally:
            if state:
                self.assertTrue(review_host.stop_host(state), '报 True 才算收干净')
        served = True
        try:
            urllib.request.urlopen(state['url'], timeout=2).read()
        except (urllib.error.URLError, OSError):
            served = False
        self.assertFalse(served, '停完之后端口不该还在应答')


class TemplatePublishGateTests(TemplateFixture):
    """**夹具层**：把发布闸门"全通过 → 放行"那个分支真的跑到。

    为什么单独一条：这一片的代码刚刚在两处红里被证明最容易藏"只认旧写者／只认旧来源"，
    而那个分支此前**没有任何测试执行过**（磁盘上也没有项目能走到它 —— 闸门要
    `template_visuals/*.png` 非空，唯一的真项目是库模板路径）。所以这里**造一个满足闸门的夹具**
    把它跑到，并标明：**这一条是夹具层的验证**（验证 16：假输入要标明类别）；
    结论那一层仍然只有真项目才算数（`test_template_review_browser.py`）。
    """

    def satisfy_the_gate(self):
        """把闸门要的几样都造齐：锁层 canvas ＋ 完整自审 ＋ 非空 template_visuals ＋ 预览清单。"""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'template'))
        from canvas_frame import FRAME_H_INT, FRAME_W_INT
        from layout_canvas import TEMPLATE_CANVAS_VERSION, locked_sha256
        from PIL import Image
        project = self.root / PROJECT
        fidelity = project / 'fidelity_template'
        registry = read(fidelity / 'template_registry.json', {})
        # canvas：锁层 + 这一代声明（`registry_canvases_ready` 三条都要）
        registry['components'] = [{'component_id': 'title', 'source_pages': [1]}]
        for layout in self.layouts:
            canvas = fidelity / 'layout_canvases' / f'{layout}.svg'
            canvas.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" '
                f'data-template-canvas-version="{TEMPLATE_CANVAS_VERSION}">'
                f'<rect data-template-lock="bg" x="0" y="0" width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#ffffff"/>'
                f'<text x="120" y="200" font-size="48">{layout}</text></svg>', encoding='utf-8')
            registry['layouts'][layout]['locked_sha256'] = locked_sha256(canvas)
        write(fidelity / 'template_registry.json', registry)
        write(project / 'template_worker_result.json', {'approved_components': [{'component_id': 'title'}]})
        write(project / 'page_manifest.json', {'version': '5.0', 'template_intake': {'mode': 'fidelity'}})
        # 源模板渲染页（非空）+ 它的清单
        visuals = project / 'template_visuals'
        visuals.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (1920, 1080), 'white').save(visuals / 'page_001.png')
        write(visuals / 'visual_manifest.json', {'pages': [{'page': 1, 'image': 'page_001.png'}]})
        # canvas 预览（每个 layout 一张 PNG）+ 预览清单
        previews = fidelity / 'canvas_previews' / 'pages'
        previews.mkdir(parents=True, exist_ok=True)
        generated = []
        for layout in self.layouts:
            target = previews / f'{layout}.png'
            Image.new('RGB', (FRAME_W_INT, FRAME_H_INT), 'white').save(target)
            generated.append(str(target.relative_to(fidelity / 'canvas_previews')))
        Image.new('RGB', (FRAME_W_INT, FRAME_H_INT), 'white').save(fidelity / 'canvas_previews' / 'full_deck_contact_sheet.png')
        write(fidelity / 'canvas_previews' / 'png_manifest.json',
              {'png_dir': '.', 'generated_files': generated, 'all_valid_size': True})
        # 完整的看图自审：逐 layout 的证据 + 三份哈希
        import hashlib
        digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        def hashes(paths):
            return {Path(one).name: digest(one) for one in sorted(paths) if Path(one).is_file()}
        write(project / 'template_canvas_self_review.json', {
            'status': 'completed', 'vision_available': True,
            'source_contact_sheet_viewed': True, 'canvas_contact_sheet_viewed': True,
            'inspection_rounds': 1, 'source_pages_reviewed': ['page_001'],
            'layouts': {layout: {'canvas_png_reviewed': True, 'compared_source_pages': ['page_001'],
                                 'usable': True, 'visual_similarity': 'pass', 'must_fix': [],
                                 'retained_features': ['锁层底板']} for layout in self.layouts},
            'evidence': {
                'source_png_sha256': hashes(visuals.glob('*.png')),
                'canvas_png_sha256': hashes((fidelity / 'canvas_previews').rglob('*.png')),
                'canvas_svg_sha256': hashes((fidelity / 'layout_canvases').glob('*.svg')),
            },
        })

    def test_the_all_pass_branch_of_the_publish_gate_runs(self):
        self.satisfy_the_gate()          # 真实顺序：模板先建好、先自审完，再生成审阅页
        self.generate()
        document = self.document(name='夹具模板')
        errors, summary = template_feedback.validate(self.root, document)
        self.assertEqual(errors, [], '三道门都满足时，全部通过必须被放行')
        self.assertTrue(summary['all_pass'])
        self.submit(document)
        import template_library
        feedback = template_library.require_approved_feedback(self.root / PROJECT)
        self.assertEqual(feedback['template_name'], '夹具模板')
        self.assertEqual(sorted(feedback['layouts']), sorted(self.layouts))

    def test_the_whole_publish_path_runs_on_a_fixture(self):
        """连打包一起跑到（**只把库根指到临时目录**，绝不往随 Skill 发布的库里写东西）。"""
        self.satisfy_the_gate()
        self.generate()
        self.submit(self.document(name='夹具模板'))
        import template_library
        with tempfile.TemporaryDirectory() as library:
            original = template_library.LIBRARY_ROOT
            template_library.LIBRARY_ROOT = Path(library)
            try:
                manifest = template_library.publish(self.root)
            finally:
                template_library.LIBRARY_ROOT = original
            self.assertEqual(manifest['status'], 'approved')
            self.assertTrue((Path(library) / manifest['template_id'] / 'manifest.json').is_file())
            self.assertTrue((Path(library) / manifest['template_id'] / 'fidelity_template' / 'template_registry.json').is_file())


class TemplateIntakeTests(TemplateFixture):
    def test_the_skill_recomputes_the_derived_fields(self):
        """页面写什么都不算数：`approved` 由 Skill 按 layouts 重算。"""
        self.generate()
        # 一份**说谎**的提交：layouts 里有一个 discard，却自称 approved
        intake = self.submit(self.document({self.layouts[0]: ('discard', '这个版式不要'), self.layouts[1]: ('pass', '')}))
        written = read(template_feedback.feedback_path(self.root))
        self.assertFalse(written['approved'], '有一个 discard 就不可能 all_pass')
        self.assertFalse(written['all_approved'])
        self.assertEqual(written['discarded_layouts'], [self.layouts[0]])
        self.assertEqual(intake['summary']['revision_layouts'], [])
        self.assertEqual(intake['errors'], [])

    def test_the_intake_matrix_reports_every_rule_verbatim(self):
        self.generate()
        cases = [
            (self.document(action='maybe'), 'submission_action must be submit_batch or approve_all'),
            (self.document({'content_base': ('pass', '')}), 'feedback must cover the exact layout set'),
            (self.document({'content_base': ('revise', ''), 'closing_dark': ('pass', '')}),
             'each revised layout requires per-layout or overall feedback'),
            (self.document(action='approve_all', decisions={'content_base': ('discard', 'x'), 'closing_dark': ('pass', '')}),
             'approve_all requires every layout to pass'),
            (self.document(name=''), 'all-pass requires a template name'),
        ]
        for document, expected in cases:
            with self.subTest(expected=expected):
                errors, _ = template_feedback.validate(self.root, document)
                self.assertTrue([one for one in errors if expected in one],
                                f'要报出这条原文：{expected}；实得 {errors}')
        # fidelity 那两道门：夹具的 canvas 没有锁层 hash / 自审证据 → 全部通过时如实拒绝
        errors, _ = template_feedback.validate(self.root, self.document(name='夹具模板'))
        self.assertTrue([one for one in errors if 'visual gate' in one], f'要报出视觉门未过：{errors}')

    def test_a_submission_is_consumed_once(self):
        self.generate()
        first = self.submit(self.document())
        second = template_feedback.consume(self.root)
        self.assertTrue(first['first_time'])
        self.assertFalse(second['first_time'], '同一份提交只处理一次（幂等）')
        events = [json.loads(line) for line in (self.root / PROJECT / 'flow_events.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e['type'] for e in events].count('template_feedback_consumed'), 1)

    def test_the_binding_evidence_is_stamped_by_the_intake(self):
        """批准绑在"这一版审阅页 + 这一版模板包"上；摘要由 Skill 盖章（页面算不了、宿主不解释）。"""
        self.generate()
        self.submit(self.document())
        written = read(template_feedback.feedback_path(self.root))
        provenance = written['provenance']
        self.assertEqual(provenance['html_sha256'], sha(self.root / '00_template_review.html'))
        self.assertEqual(provenance['png_sha256'], {}, '夹具没有源模板渲染页 → 空（发布闸门会因此拒绝）')
        package = provenance['template_package_sha256']
        self.assertIn(f'{PROJECT}/fidelity_template/template_registry.json', package)
        self.assertEqual(len([k for k in package if k.endswith('.svg')]), len(self.layouts))

    def test_a_stale_approval_is_flagged_and_gets_no_binding(self):
        """陈旧＝绑的是上一版审阅页：不算批准，而且**不盖章**（不留看起来算数的证据）。"""
        self.generate()
        intake = self.submit(self.document(review_id='上一版的 review_id'))
        self.assertTrue(intake['stale'])
        self.assertIn('stale', intake['stale_message'])
        written = read(template_feedback.feedback_path(self.root))
        self.assertNotIn('html_sha256', written['provenance'], '陈旧的那一份不许有绑定证据')
        self.assertTrue(written['consumed']['stale'])
        # 发布闸门：这份东西不可能被当成批准
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'template'))
        import template_library
        with self.assertRaises(ValueError):
            template_library.require_approved_feedback(self.root / PROJECT)

    def test_the_old_manifest_derived_layout_rule_would_reject_a_valid_submission(self):
        """红对照：按 `page_manifest.template_intake.mode` 推 expected_layouts 的**旧规则**会判死合法提交。

        这是这次改掉的那件事（一处事实只有一个来源）：页面按 registry 渲染，收件却按 manifest 推。
        """
        self.generate()
        document = self.document({self.layouts[0]: ('revise', '标题下移 8px'), self.layouts[1]: ('pass', '')})
        errors, summary = template_feedback.validate(self.root, document)
        self.assertEqual(errors, [], '按快照推（与页面同源）= 通过')
        self.assertEqual(summary['expected_layouts'], self.layouts)
        old_errors, _ = template_feedback.validate(self.root, document, expected=['reference_system'])
        self.assertEqual(old_errors, ['feedback must cover the exact layout set with pass/discard/revise decisions'],
                         '旧规则必须红 —— 否则这条对照没有牙')


if __name__ == '__main__':
    unittest.main()
