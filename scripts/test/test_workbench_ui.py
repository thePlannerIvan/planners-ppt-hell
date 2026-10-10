"""Persistent workbench browser contract, using the real store behind a test bridge."""
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from generate_review_html import generate, prepare_inline_svg  # noqa: E402
from project_state import CONTENT, PNG, SVG, write  # noqa: E402
from review_surface import surface_document  # noqa: E402
from workbench_store import commit, ensure, get_page  # noqa: E402


class WorkbenchGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'project'
        write(self.root / CONTENT, {'project': 'Workbench test', 'pages': [
            {'page_key': key, 'title': key, 'content': '', 'source_assets': []}
            for key in ('alpha', 'omega')]})
        (self.root / SVG).mkdir(parents=True)
        Image.new('RGB', (20, 10), 'green').save(self.root / SVG / 'photo.png')
        for key in ('alpha', 'omega'):
            (self.root / SVG / (key + '.svg')).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">'
                '<defs><clipPath id="clip"><rect width="300" height="100"/></clipPath></defs>'
                '<rect width="1920" height="1080" fill="white"/>'
                '<text id="heading" data-step="step-one" data-anim="fade" x="120" y="180" font-size="48">Original</text>'
                '<text x="120" y="260" font-size="32"><tspan x="120">Line one</tspan>'
                '<tspan x="120" dy="40">Line two</tspan></text>'
                '<image href="photo.png" x="120" y="400" width="200" height="100"/></svg>', encoding='utf-8')
        ensure(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generator_ids_and_order_are_store_owned(self):
        page = get_page(self.root, 'alpha')
        svg = ET.fromstring(prepare_inline_svg(self.root, 'alpha'))
        self.assertTrue(all(node.get('data-review-id') == node.get('data-workbench-id') for node in svg.iter()))
        self.assertIn('rvsvg_alpha_heading', prepare_inline_svg(self.root, 'alpha'))
        self.assertFalse(any(re.fullmatch(r'0(?:\.\d+)*', node.get('data-review-id', '')) for node in svg.iter()))
        result = commit(self.root, {'op': 'order', 'operation_id': 'order_test',
                                   'base_order': ['alpha', 'omega'], 'order': ['omega', 'alpha']}, browser=True)
        self.assertTrue(result['ok'])
        snap = generate(self.root)
        self.assertEqual(snap['order'], ['omega', 'alpha'])
        self.assertEqual(snap['revisions']['alpha'], page['revision'])
        html = (self.root / '02_visual_review.html').read_text()
        self.assertIn('"revision":', html)
        self.assertIn('"version":', html)
        self.assertNotIn('本页通过', html)
        self.assertNotIn('批准未处理页', html)

    def test_template_surface_does_not_gain_workbench_commands(self):
        visual = surface_document(self.root)
        template = surface_document(self.root, 'template')
        self.assertEqual(visual['command_backend'], 'svg-workbench/1')
        self.assertIn('command', visual['capabilities'])
        self.assertNotIn('command_backend', template)
        self.assertNotIn('command', template['capabilities'])

    def test_inline_css_rules_are_explicitly_unsupported(self):
        stored = get_page(self.root, 'alpha')
        tree = ET.fromstring(stored['svg'])
        ET.SubElement(tree, '{http://www.w3.org/2000/svg}style').text = '#heading {fill:red}'
        stored['svg'] = ET.tostring(tree, encoding='unicode')
        with self.assertRaisesRegex(ValueError, 'does not support SVG CSS rules'):
            prepare_inline_svg(self.root, 'alpha', stored)

    def test_animation_identity_survives_edit_and_snapshot(self):
        current = get_page(self.root, 'alpha')
        result = commit(self.root, {'op': 'save', 'operation_id': 'anim_save', 'page_key': 'alpha',
                                   'base_revision': current['revision'], 'author': 'human',
                                   'edits': [{'element_id': 'heading', 'kind': 'text', 'value': 'Updated'}]}, browser=True)
        self.assertTrue(result['ok'])
        record = get_page(self.root, 'alpha')
        heading = next(node for node in ET.fromstring(record['svg']).iter() if node.get('id') == 'heading')
        self.assertEqual(heading.get('data-step'), 'step-one')
        self.assertEqual(heading.get('data-anim'), 'fade')
        self.assertEqual(heading.get('data-workbench-id'), 'heading')
        inline = ET.fromstring(prepare_inline_svg(self.root, 'alpha', record))
        isolated = next(node for node in inline.iter() if node.get('data-orig-id') == 'heading')
        self.assertEqual(isolated.get('id'), 'rvsvg_alpha_heading')
        self.assertEqual(isolated.get('data-review-id'), 'heading')
        output = commit(self.root, {'op': 'snapshot', 'operation_id': 'anim_snapshot', 'purpose': 'slides'}, browser=True)
        frozen = ET.parse(Path(output['root']) / output['pages'][0]['svg'])
        target = next(node for node in frozen.iter() if node.get('id') == 'heading')
        self.assertEqual(target.get('data-step'), 'step-one')
        self.assertEqual(target.get('data-anim'), 'fade')


@unittest.skipUnless(os.environ.get('PPT_WORKBENCH_BROWSER_TESTS') == '1',
                     'set PPT_WORKBENCH_BROWSER_TESTS=1 to run Playwright')
class WorkbenchBrowserTests(WorkbenchGeneratorTests):
    def setUp(self):
        super().setUp()
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 950})
        self.calls = []
        self.wakes = []
        self.fail_next = None
        self.server_draft = None
        self.transport = 'postMessage'
        self.errors = []
        self.context.expose_binding('__storeCommand', self.backend)
        self.context.expose_binding('__wake', lambda source, body: self.wakes.append(body) or {'verified': {'state': 'queued'}})
        self.context.expose_binding('__draft', lambda source, body: self.save_server_draft(body))
        self.context.expose_binding('__readDraft', lambda source: json.dumps(self.server_draft or {}))
        self.context.add_init_script("""
          window.__changedCallbacks=[];
          window.ReviewBridge={connect:async()=>({
            transport:window.__transport||'postMessage', capabilities:window.__capabilities||['command','draft','asset-upload'],
            command:body=>window.__storeCommand(body),
            asset:async rel=>'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="192" height="108"><rect width="192" height="108" fill="white"/></svg>'),
            draft:body=>window.__draft(body),
            readText:async rel=>window.__readDraft(),
            wake:body=>window.__wake(body), on:(event,fn)=>window.__changedCallbacks.push(fn)
          })};
        """)
        generate(self.root)
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto((self.root / '02_visual_review.html').as_uri())
        self.page.wait_for_function("typeof canCommand!=='undefined'&&canCommand&&recoveryReady")
        self.page.wait_for_function("document.querySelector('#svgStageWrap svg')!==null")
        self.page.wait_for_function('workbenchReady')

    def backend(self, source, body):
        self.calls.append(body)
        result = commit(self.root, body, browser=True)
        if self.fail_next == body.get('op'):
            self.fail_next = None
            raise RuntimeError('Simulated lost receipt after durable commit')
        return result

    def save_server_draft(self, body):
        self.server_draft = body
        return {'ok': True}

    def tearDown(self):
        self.page.evaluate("""async () => {
          clearTimeout(saveTimer);clearTimeout(draftTimer);
          await Promise.all([...saveQueues.values()]);
          if(draftPromise)await draftPromise;
          if(hostSync)await hostSync;
        }""")
        self.context.close()
        self.browser.close()
        self.playwright.stop()
        super().tearDown()

    def edit(self, value):
        self.page.locator('#svgStageWrap text').first.dblclick()
        self.page.locator('#inlineCanvasEditor').fill(value)

    def flush(self):
        return self.page.evaluate('() => flushWorkbench()')

    def text(self, key='alpha'):
        tree = ET.fromstring(get_page(self.root, key)['svg'])
        return next(node.text for node in tree.iter() if node.get('id') == 'heading')

    def test_autosave_survives_reload_without_model_or_approval(self):
        self.edit('Human durable text')
        self.page.wait_for_function("state.alpha.saved_edits.some(e=>e.text==='Human durable text')")
        self.assertEqual(self.text(), 'Human durable text')
        self.assertEqual(self.wakes, [])
        self.page.reload()
        self.page.wait_for_function("document.querySelector('#svgStageWrap text')?.textContent==='Human durable text'")
        self.assertEqual(self.errors, [])

    def test_ime_flush_is_bound_to_previous_page_on_navigation(self):
        self.page.locator('#svgStageWrap text').first.dblclick()
        self.page.evaluate("""() => {
          const editor=document.querySelector('#inlineCanvasEditor');
          editor.dispatchEvent(new CompositionEvent('compositionstart'));
          editor.value='中文最后一次输入';editor.dispatchEvent(new InputEvent('input',{isComposing:true,bubbles:true}));
          go(1);
        }""")
        self.page.wait_for_function("state.alpha.saved_edits.some(e=>e.text==='中文最后一次输入')")
        self.assertEqual(self.text(), '中文最后一次输入')
        self.assertEqual(self.text('omega'), 'Original')
        self.assertEqual(self.errors, [])

    def test_conflict_and_snapshot_preserve_recovery_inputs(self):
        self.edit('Unsent human text')
        self.page.evaluate('() => clearTimeout(saveTimer)')
        current = get_page(self.root, 'alpha')
        identity = next(node.get('data-workbench-id') for node in ET.fromstring(current['svg']).iter() if node.get('id') == 'heading')
        commit(self.root, {'op': 'save', 'operation_id': 'other_tab', 'page_key': 'alpha',
                          'base_revision': current['revision'], 'author': 'human',
                          'edits': [{'element_id': identity, 'kind': 'text', 'value': 'Other tab text'}]}, browser=True)
        self.page.evaluate("() => {const el=document.querySelector('#feedback');el.value='Retain my feedback';el.dispatchEvent(new Event('input'))}")
        self.page.evaluate('() => clearTimeout(saveTimer)')
        self.page.evaluate('() => onHostChanged()')
        self.assertEqual(self.page.locator('#inlineCanvasEditor').input_value(), 'Unsent human text')
        self.assertEqual(self.page.locator('#feedback').input_value(), 'Retain my feedback')
        self.assertFalse(self.flush())
        self.assertEqual(self.text(), 'Other tab text')
        self.assertEqual(self.page.evaluate('() => state.alpha.save_status'), 'conflict')
        self.page.reload()
        self.page.wait_for_function("state.alpha.save_status==='conflict'")
        self.assertIn('Unsent human text', self.page.locator('#svgStageWrap text').first.text_content())
        self.assertEqual(self.errors, [])

    def test_lost_save_receipt_reuses_operation_id(self):
        self.fail_next = 'save'
        self.edit('Retry text')
        self.page.evaluate('() => clearTimeout(saveTimer)')
        self.assertFalse(self.flush())
        self.assertNotIn('已保存', self.page.locator('#pageStatus').inner_text())
        pending = self.page.evaluate('() => state.alpha.pending_save.command.operation_id')
        self.assertTrue(self.flush())
        saves = [body for body in self.calls if body.get('op') == 'save']
        self.assertEqual(saves[-1]['operation_id'], pending)
        self.assertEqual(saves[-2]['operation_id'], pending)
        self.assertEqual(self.text(), 'Retry text')

    def test_feedback_is_page_scoped_and_rewrite_is_opt_in(self):
        self.edit('Protected copy')
        self.assertTrue(self.flush())
        self.page.locator('#feedback').fill('Redesign this page')
        self.page.locator('#pageDispatch').click()
        self.page.wait_for_function('state.alpha.task!==null')
        first = [body for body in self.calls if body.get('op') == 'feedback'][-1]
        self.assertEqual(list(first['pages']), ['alpha'])
        self.assertEqual(first['pages']['alpha']['rewrite_elements'], [])
        self.page.locator('#svgStageWrap text').first.click()
        identity = self.page.evaluate('() => selectedReviewId')
        self.page.locator('#commentElBtn').click()
        self.page.locator('#regionNote').fill('Rewrite only this title')
        self.page.locator('#allowRewrite').check()
        self.page.get_by_text('添加批注', exact=True).click()
        old_task = self.page.evaluate('() => state.alpha.task.id')
        self.page.locator('#pageDispatch').click()
        self.page.wait_for_function(f"state.alpha.task.id!=='{old_task}'")
        second = [body for body in self.calls if body.get('op') == 'feedback'][-1]
        self.assertEqual(second['pages']['alpha']['rewrite_elements'], [identity])
        self.assertNotEqual(first['operation_id'], second['operation_id'])
        self.assertEqual(self.errors, [])

    def test_undo_saved_delete_and_saved_font_position(self):
        self.page.locator('#svgStageWrap text').first.click()
        self.page.evaluate('() => stepFontSize(2)')
        self.assertTrue(self.flush())
        self.page.evaluate('() => deleteSelectedSvgElement()')
        self.assertTrue(self.flush())
        self.page.evaluate('() => undoLastSvgEdit()')
        self.assertTrue(self.flush())
        self.assertEqual(self.text(), 'Original')
        tree = ET.fromstring(get_page(self.root, 'alpha')['svg'])
        self.assertEqual(next(node.get('font-size') for node in tree.iter() if node.get('id') == 'heading'), '50')

    def test_http_hides_page_dispatch_and_supports_whole_deck(self):
        self.page.evaluate("() => {review.transport='http';document.querySelector('#pageDispatch').hidden=true}")
        self.assertFalse(self.page.locator('#pageDispatch').is_visible())
        self.page.locator('#feedback').fill('Whole deck task')
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('deck')"))
        feedback = [body for body in self.calls if body.get('op') == 'feedback'][-1]
        self.assertEqual(feedback['scope'], 'deck')
        self.assertEqual(set(feedback['pages']), {'alpha'})

    def test_unsupported_commands_never_show_saved(self):
        self.page.evaluate("() => {review.command=async()=>({ok:false,code:'unsupported',error:'Not supported'})}")
        self.edit('Keep this recovery draft')
        self.page.evaluate('() => clearTimeout(saveTimer)')
        self.assertFalse(self.flush())
        self.assertTrue(self.page.locator('#localFallback').is_visible())
        self.assertNotIn('已保存', self.page.locator('#pageStatus').inner_text())
        self.assertEqual(self.text(), 'Original')
        self.page.locator('#localFallback').click()
        self.assertIn(str(self.root), self.page.locator('#fallbackCommand').inner_text())

    def test_current_svg_hydration_keeps_frozen_asset_paths(self):
        self.edit('Fresh saved SVG')
        self.assertTrue(self.flush())
        self.page.reload()
        self.page.wait_for_function("document.querySelector('#svgStageWrap text')?.textContent==='Fresh saved SVG'")
        rel = self.page.locator('#svgStageWrap image').get_attribute('data-project-rel')
        revision = get_page(self.root, 'alpha')['revision']
        self.assertTrue(rel.startswith('_internal/06_workbench/revisions/' + revision + '/'))
        self.assertTrue((self.root / rel).is_file())

    def test_multiline_edits_keep_tspan_ids(self):
        current = get_page(self.root, 'alpha')
        original = [node.get('data-workbench-id') for node in ET.fromstring(current['svg']).iter() if node.tag.endswith('tspan')]
        self.page.locator('#svgStageWrap text').nth(1).locator('tspan').first.dblclick()
        self.page.locator('#inlineCanvasEditor').fill('Updated one\nUpdated two')
        self.assertTrue(self.flush())
        new = ET.fromstring(get_page(self.root, 'alpha')['svg'])
        spans = [node for node in new.iter() if node.tag.endswith('tspan')]
        self.assertEqual([node.get('data-workbench-id') for node in spans], original)
        self.assertEqual([node.text for node in spans], ['Updated one', 'Updated two'])

    def test_history_restore_creates_new_revision(self):
        first = get_page(self.root, 'alpha')['revision']
        self.edit('Saved latest')
        self.assertTrue(self.flush())
        latest = get_page(self.root, 'alpha')['revision']
        self.page.locator('#versionMenu summary').click()
        self.page.locator('#historyRevision').select_option(first)
        self.page.locator('#restoreRevision').click()
        self.page.locator('#restoreDialog').get_by_text('恢复', exact=True).click()
        self.page.wait_for_function("document.querySelector('#message').textContent.includes('已恢复历史版本')")
        restored = get_page(self.root, 'alpha')
        self.assertNotIn(restored['revision'], (first, latest))
        self.assertEqual(self.text(), 'Original')
        history = commit(self.root, {'op': 'get', 'page_key': 'alpha'}, browser=True)['history']
        self.assertIn(latest, [entry['revision'] for entry in history])

    def test_browser_order_is_durable_and_reload_uses_store_order(self):
        self.page.evaluate("() => reorderPages('alpha','omega',false)")
        self.assertTrue(self.flush())
        self.assertEqual(ensure(self.root)['order'], ['omega', 'alpha'])
        self.page.reload()
        self.page.wait_for_function("workbenchReady&&pageOrder[0]==='omega'&&canCommand")
        self.assertEqual(self.page.locator('#rail button').first.get_attribute('data-key'), 'omega')

    def test_export_flushes_ime_without_feedback_or_approval(self):
        self.page.locator('#svgStageWrap text').first.dblclick()
        self.page.evaluate("""() => {
          const el=document.querySelector('#inlineCanvasEditor');
          el.dispatchEvent(new CompositionEvent('compositionstart'));
          el.value='输出前最后的输入';el.dispatchEvent(new InputEvent('input',{isComposing:true}));
        }""")
        self.assertTrue(self.page.evaluate('() => exportWorkbench()'))
        self.assertEqual(self.text(), '输出前最后的输入')
        self.assertEqual(len(ensure(self.root)['tasks']), 0)
        receipt = self.page.evaluate('() => lastOutput')
        self.assertTrue(Path(receipt['path']).is_file())
        self.assertIn('--snapshot', self.wakes[-1]['text'])
        self.assertIn(receipt['path'], self.wakes[-1]['text'])

    def test_lost_snapshot_receipt_retry_uses_same_identity(self):
        self.fail_next = 'snapshot'
        self.assertFalse(self.page.evaluate('() => exportWorkbench()'))
        pending = self.page.evaluate('() => pendingSnapshot.operation_id')
        self.assertTrue(self.page.evaluate('() => exportWorkbench()'))
        snapshots = [body for body in self.calls if body.get('op') == 'snapshot']
        self.assertEqual([body['operation_id'] for body in snapshots], [pending, pending])

    def test_http_export_returns_fixed_snapshot_and_exact_command(self):
        self.page.evaluate("() => {review.transport='http'}")
        self.assertTrue(self.page.evaluate('() => exportWorkbench()'))
        receipt = self.page.evaluate('() => lastOutput')
        self.assertIn(receipt['path'], self.page.locator('#exportCommand').inner_text())
        self.assertIn('--snapshot', self.page.locator('#exportCommand').inner_text())
        self.assertEqual(self.wakes, [])

    def test_real_http_host_saves_and_reloads_without_regenerating(self):
        import review_surface
        import review_host
        with patch.dict(os.environ, {'PLANNERS_REVIEW_PYTHON': sys.executable}):
            host = review_host.start_host(self.root / review_surface.SURFACE_REL)
        try:
            context = self.browser.new_context(viewport={'width': 1440, 'height': 950})
            page = context.new_page()
            page.goto(host['url'])
            page.wait_for_function("typeof canCommand!=='undefined'&&canCommand")
            self.assertFalse(page.locator('#pageDispatch').is_visible())
            page.locator('#svgStageWrap text').first.dblclick()
            page.locator('#inlineCanvasEditor').fill('Real HTTP durable text')
            self.assertTrue(page.evaluate('() => flushWorkbench()'))
            page.reload()
            page.wait_for_function("document.querySelector('#svgStageWrap text')?.textContent==='Real HTTP durable text'")
            self.assertEqual(self.text(), 'Real HTTP durable text')
            self.assertTrue(page.locator('#svgStageWrap image').get_attribute('data-project-rel').startswith('_internal/06_workbench/revisions/'))
            context.close()
        finally:
            review_host.stop_host(host)

    def test_desktop_and_mobile_layout_screenshots(self):
        for width, height in ((1440, 950), (390, 844)):
            self.page.set_viewport_size({'width': width, 'height': height})
            self.page.wait_for_timeout(50)
            bounds = self.page.locator('#preview').bounding_box()
            self.assertGreater(bounds['width'], 100)
            self.assertGreater(bounds['height'], 50)
            self.assertLessEqual(bounds['x'] + bounds['width'], width + 1)
            if os.environ.get('PPT_WORKBENCH_SCREENSHOTS'):
                target = Path(os.environ['PPT_WORKBENCH_SCREENSHOTS'])
                target.mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(target / f'workbench-{width}.png'))
        self.assertEqual(self.errors, [])

    def test_user_surface_hides_internal_ids_and_technical_status(self):
        self.page.evaluate('() => onHostChanged()')
        self.page.evaluate("""() => {
          const p=page();
          p.history=[
            {revision:p.revision,author:'model',created_at:'2026-10-09T10:00:00Z'},
            {revision:'r_old_secret',author:'model',created_at:'2026-10-08T10:00:00Z'}
          ];
          state.alpha.task={id:'task_r_secret',status:'resolved'};
          feedbackTasks={task_r_secret:{task_id:'task_r_secret',pages:{alpha:{feedback:'Earlier'}},status:'resolved'}};
          p.preview_pending=true;
          drawHistory(p);status();drawSaveStatus();
        }""")
        visible = self.page.locator('body').inner_text()
        self.assertNotRegex(visible, r'\br_[A-Za-z0-9_-]+\b')
        self.assertNotIn('model', visible)
        self.assertNotIn('resolved', visible)
        self.assertNotIn('SVG 已保存', visible)
        self.assertEqual('修改已处理', self.page.locator('#taskState').inner_text())
        self.page.locator('#versionMenu summary').click()
        history_labels = self.page.locator('#historyRevision').locator('option').all_inner_texts()
        self.assertEqual(history_labels[0], '当前版本')
        self.assertTrue(history_labels[1].startswith('历史版本 '))
        self.assertFalse(self.page.locator('#microEditBar').is_visible())
        self.assertTrue(self.page.locator('.review-brand-mark').is_visible())
        self.assertFalse(self.page.get_by_text('Logics', exact=True).is_visible())

    def test_inline_editor_has_contrast_safe_text_for_white_svg(self):
        self.page.evaluate("() => document.querySelector('#svgStageWrap text').setAttribute('fill','white')")
        self.edit('Contrast-safe text')
        color, background = self.page.evaluate("""() => {
          const style=getComputedStyle(document.querySelector('#inlineCanvasEditor'));
          return [style.color,style.backgroundColor];
        }""")

        def channels(value):
            return [int(channel) for channel in re.findall(r'\d+', value)[:3]]

        def luminance(rgb):
            values=[channel / 255 for channel in rgb]
            values=[value / 12.92 if value <= .03928 else ((value + .055) / 1.055) ** 2.4 for value in values]
            return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]

        ratio=(max(luminance(channels(color)), luminance(channels(background))) + .05) / (min(luminance(channels(color)), luminance(channels(background))) + .05)
        self.assertGreaterEqual(ratio, 4.5)
        self.assertEqual(channels(background), [255, 255, 255])
        self.assertFalse(self.page.locator('#microEditBar').is_hidden())

    def test_footer_has_one_primary_and_icon_reload(self):
        self.assertEqual(self.page.locator('footer .review-primary-action:visible').count(), 1)
        self.assertEqual(self.page.locator('#saveEdits').count(), 0)
        self.assertTrue(self.page.locator('#exportOutput.review-secondary-action').is_visible())
        self.assertEqual(self.page.locator('#reloadButton [data-review-icon="RefreshCw"]').count(), 1)

    def test_overall_only_feedback_restores_and_dispatches_from_dialog(self):
        self.page.evaluate('() => showSubmit()')
        self.page.locator('#overall').fill('Overall-only deck feedback')
        self.page.wait_for_function('() => lastDraftSaved.includes("Overall-only deck feedback")')
        self.page.reload()
        self.page.wait_for_function("recoveryReady&&document.querySelector('#overall').value==='Overall-only deck feedback'")
        self.page.evaluate('() => showSubmit()')
        self.page.get_by_text('提交整套修改任务', exact=True).click()
        self.page.wait_for_function("!document.querySelector('#submitDialog').open")
        task = list(ensure(self.root)['tasks'].values())[-1]
        self.assertEqual(task['overall_feedback'], 'Overall-only deck feedback')

    def test_opaque_host_draft_restores_without_local_storage(self):
        self.context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('opaque origin','SecurityError')}})")
        self.page.reload()
        self.page.wait_for_function('workbenchReady&&canCommand')
        self.page.locator('#feedback').fill('Opaque draft feedback')
        self.page.evaluate('() => showSubmit()')
        self.page.locator('#overall').fill('Opaque overall')
        self.assertTrue(self.page.evaluate('() => saveDraft()'))
        self.assertEqual(self.server_draft['overall_feedback'], 'Opaque overall')
        self.page.reload()
        self.page.wait_for_function("workbenchReady&&document.querySelector('#overall').value==='Opaque overall'")
        self.assertEqual(self.page.locator('#feedback').input_value(), 'Opaque draft feedback')
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
