import concurrent.futures
import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workbench_store as store


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write('_internal/01_content/page_content.json', json.dumps({'pages': [
            {'page_key': 'p1', 'title': 'First', 'notes': 'original'},
            {'page_key': 'p2', 'title': 'Second', 'notes': ''}]}))
        self.write('_internal/00_project/page_manifest.json', json.dumps({'version': '5.0', 'route': 'slides'}))
        for key in ('p1', 'p2'):
            self.write(f'{store.VIEW}/{key}.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                       '<text id="title" x="10" y="20">Original</text><rect id="box" width="10" height="10"/></svg>')
        store.ensure(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def save(self, edits=None, key='p1', **extra):
        current = store.get_page(self.root, key)
        command = {'op': 'save', 'operation_id': 'op_' + store.uuid.uuid4().hex,
                   'page_key': key, 'base_revision': current['revision'], 'author': 'human',
                   'edits': edits or [], **extra}
        return store.commit(self.root, command, browser=True)

    def candidate(self, text=None, key='p1', **extra):
        current = store.get_page(self.root, key)
        svg = current['svg'] if text is None else text
        path = self.write('candidate.svg', svg)
        # Frozen hrefs must be resolved at their original base, not a moved candidate.
        command = {'op': 'save', 'operation_id': 'model_' + store.uuid.uuid4().hex,
                   'page_key': key, 'base_revision': current['revision'], 'author': 'model',
                   'candidate': str(path), **extra}
        return store.commit(self.root, command)

    def add_page(self, key='p2', before=None):
        candidate = self.write('new-page.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text id="new-title" x="10" y="20">New page</text></svg>')
        current = store.ensure(self.root)
        command = {'op': 'add_page', 'operation_id': 'add_' + store.uuid.uuid4().hex,
                   'candidate': str(candidate), 'base_order': list(current['order']),
                   'page': {'page_key': key, 'title': 'New page', 'content': 'New page', 'mode': '读'}}
        if before: command['before_page_key'] = before
        return store.commit(self.root, command)

    def test_model_can_add_page_with_candidate_and_order(self):
        result = self.add_page('new', 'p2')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['order'], ['p1', 'new', 'p2'])
        state = store.commit(self.root, {'op': 'state'})
        self.assertEqual(state['order'], ['p1', 'new', 'p2'])
        self.assertEqual(store.get_page(self.root, 'new')['revision'], result['revision'])

    def test_model_can_delete_page_but_not_last_page(self):
        self.add_page('new')
        result = store.commit(self.root, {'op': 'delete_page', 'operation_id': 'delete_' + store.uuid.uuid4().hex,
                                          'page_key': 'new', 'base_revision': store.get_page(self.root, 'new')['revision'], 'base_order': ['p1', 'p2', 'new']})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['order'], ['p1', 'p2'])
        result = store.commit(self.root, {'op': 'delete_page', 'operation_id': 'delete_last_' + store.uuid.uuid4().hex,
                                          'page_key': 'p2', 'base_revision': store.get_page(self.root, 'p2')['revision'], 'base_order': ['p1', 'p2']})
        self.assertTrue(result['ok'], result)
        result = store.commit(self.root, {'op': 'delete_page', 'operation_id': 'delete_only_' + store.uuid.uuid4().hex,
                                          'page_key': 'p1', 'base_revision': store.get_page(self.root, 'p1')['revision'], 'base_order': ['p1']})
        self.assertEqual(result['code'], 'last_page')

    def test_page_collection_operations_require_current_order(self):
        result = self.add_page('new')
        self.assertTrue(result['ok'])
        candidate = self.write('new2.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text id="new-title" x="10" y="20">New page</text></svg>')
        result = store.commit(self.root, {'op': 'add_page', 'operation_id': 'add_conflict', 'candidate': str(candidate),
             'base_order': ['p2','p1'], 'page': {'page_key':'new2','title':'New2'}})
        self.assertEqual(result['code'], 'conflict')

    def test_human_save_survives_restart_without_feedback(self):
        old = store.get_page(self.root, 'p1')
        result = self.save([{'element_id': 'title', 'kind': 'text', 'value': '用户改字'}])
        self.assertTrue(result['saved'])
        self.assertIn('用户改字', store.get_page(self.root, 'p1')['svg'])
        self.assertIn('Original', (store.revision_dir(self.root, old['revision']) / 'page.svg').read_text())
        self.assertEqual(store.ensure(self.root)['tasks'], {})

    def test_text_nodes_preserve_nested_spans_and_tails(self):
        current = store.get_page(self.root, 'p1')
        self.assertTrue(self.candidate(current['svg'].replace('Original',
            'Before <tspan id="accent" fill="red">word<tspan id="nested" font-weight="700">bold</tspan> tail</tspan> after'))['ok'])
        result = self.save([{'element_id': 'title', 'kind': 'text_nodes', 'nodes': [
            {'element_id': 'title', 'slot': 'text', 'value': 'Changed '},
            {'element_id': 'accent', 'slot': 'text', 'value': 'term'},
            {'element_id': 'nested', 'slot': 'tail', 'value': ' kept tail'}]}])
        self.assertTrue(result['ok'], result)
        tree = ET.fromstring(store.get_page(self.root, 'p1')['svg'])
        accent = next(node for node in tree.iter() if node.get('id') == 'accent')
        self.assertEqual(accent.get('fill'), 'red')
        self.assertEqual(accent.text, 'term')
        nested = list(accent)[0]
        self.assertEqual(nested.get('font-weight'), '700')
        self.assertEqual(nested.tail, ' kept tail')
        self.assertEqual(accent.tail, ' after')
        saved = store.get_page(self.root, 'p1')
        self.assertEqual(self.candidate(saved['svg'].replace('term', 'lost'))['code'], 'human_edits_lost')
        self.assertTrue(self.save([{'element_id': 'nested', 'kind': 'text', 'value': 'Human later'}])['ok'])
        self.assertTrue(self.candidate()['ok'])

    def test_text_nodes_cannot_change_outside_the_target_text(self):
        result = self.save([{'element_id': 'title', 'kind': 'text_nodes', 'nodes': [
            {'element_id': 'box', 'slot': 'text', 'value': 'wrong'}]}])
        self.assertEqual(result['code'], 'invalid_edit')
        self.assertIn('Original', store.get_page(self.root, 'p1')['svg'])

    def test_old_model_candidate_cannot_overwrite(self):
        old = store.get_page(self.root, 'p1')
        path = self.write('candidate.svg', old['svg'])
        new = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Human'}])
        result = store.commit(self.root, {'op': 'save', 'operation_id': 'm_old', 'page_key': 'p1',
                                         'base_revision': old['revision'], 'author': 'model', 'candidate': str(path)})
        self.assertEqual(result['code'], 'conflict')
        self.assertEqual(store.get_page(self.root, 'p1')['revision'], new['revision'])
        self.assertTrue(Path(result['recovery']).is_file())

    def test_latest_candidate_still_cannot_drop_human_text(self):
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Human'}])
        current = store.get_page(self.root, 'p1')
        result = self.candidate(current['svg'].replace('Human', 'Dropped'))
        self.assertEqual(result['code'], 'human_edits_lost')
        self.assertEqual(result['elements'], ['title'])

    def test_explicit_human_rewrite_scope_authorizes_only_target(self):
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Human'},
                   {'element_id': 'box', 'kind': 'attributes', 'attributes': {'fill': 'red'}}])
        current = store.get_page(self.root, 'p1')
        task = store.commit(self.root, {'op': 'feedback', 'operation_id': 'f_rewrite', 'scope': 'page',
            'pages': {'p1': {'revision': current['revision'], 'feedback': 'Rewrite this title',
                             'rewrite_elements': ['title']}}}, browser=True)
        self.assertTrue(self.candidate(current['svg'].replace('Human', 'New'), task_id=task['task_id'])['ok'])
        current = store.get_page(self.root, 'p1')
        self.assertEqual(self.candidate(current['svg'].replace('fill="red"', 'fill="blue"'))['code'], 'human_edits_lost')

    def test_deleted_element_cannot_return(self):
        old = store.get_page(self.root, 'p1')['svg']
        self.save([{'element_id': 'box', 'kind': 'delete'}])
        self.assertEqual(self.candidate(old)['code'], 'human_edits_lost')

    def test_notes_do_not_claim_svg_edit_loss(self):
        self.save(notes='Human note')
        self.assertTrue(self.candidate()['ok'])
        self.assertEqual(store.get_page(self.root, 'p1')['notes'], 'Human note')

    def test_retry_is_same_revision_and_identity_reuse_rejected(self):
        current = store.get_page(self.root, 'p1')
        command = {'op': 'save', 'operation_id': 'retry_1', 'page_key': 'p1',
                   'base_revision': current['revision'], 'notes': 'note'}
        first = store.commit(self.root, command, True)
        self.assertEqual(first, store.commit(self.root, command, True))
        with self.assertRaises(store.StoreError):
            store.commit(self.root, {**command, 'notes': 'different'}, True)

    def test_concurrent_tabs_only_one_wins(self):
        revision = store.get_page(self.root, 'p1')['revision']
        def edit(index):
            return store.commit(self.root, {'op': 'save', 'operation_id': 'tab_' + str(index),
                'page_key': 'p1', 'base_revision': revision, 'notes': str(index)}, True)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = list(pool.map(edit, range(8)))
        self.assertEqual(sum(r['ok'] for r in results), 1)
        self.assertTrue(all(r['ok'] or r['code'] == 'conflict' for r in results))

    def test_other_page_is_independent(self):
        original = store.get_page(self.root, 'p2')['revision']
        self.save(notes='note')
        self.assertEqual(store.get_page(self.root, 'p2')['revision'], original)

    def test_same_feedback_new_operation_is_new_task(self):
        revision = store.get_page(self.root, 'p1')['revision']
        command = {'op': 'feedback', 'operation_id': 'feedback_1', 'scope': 'page',
                   'pages': {'p1': {'revision': revision, 'feedback': 'Again'}}}
        first = store.commit(self.root, command, True)
        self.assertEqual(first, store.commit(self.root, command, True))
        second = store.commit(self.root, {**command, 'operation_id': 'feedback_2'}, True)
        self.assertNotEqual(first['task_id'], second['task_id'])

    def test_model_reads_only_pending_tasks_not_resolved_history(self):
        revision = store.get_page(self.root, 'p1')['revision']
        task = store.commit(self.root, {'op': 'feedback', 'operation_id': 'feedback_history', 'scope': 'page',
            'pages': {'p1': {'revision': revision, 'feedback': 'Past opinion'}}}, True)
        resolved = store.commit(self.root, {'op': 'resolve', 'operation_id': 'resolve_history',
            'task_id': task['task_id'], 'results': {'p1': revision}, 'note': 'Handled'})
        self.assertTrue(resolved['ok'])
        self.assertNotIn(task['task_id'], store.commit(self.root, {'op': 'state'})['tasks'])
        self.assertIn(task['task_id'], store.commit(self.root, {'op': 'state'}, True)['tasks'])
        with self.assertRaisesRegex(store.StoreError, 'Only a pending task'):
            store.commit(self.root, {'op': 'task', 'task_id': task['task_id']})
        next_task = store.commit(self.root, {'op': 'feedback', 'operation_id': 'feedback_new', 'scope': 'page',
            'pages': {'p1': {'revision': revision, 'feedback': 'New opinion'}}}, True)
        active = store.commit(self.root, {'op': 'task', 'task_id': next_task['task_id']})['task']
        self.assertEqual(active['pages']['p1']['feedback'], 'New opinion')

    def test_task_carries_template_and_page_layout_reference(self):
        revision = store.get_page(self.root, 'p1')['revision']
        task = store.commit(self.root, {'op': 'feedback', 'operation_id': 'feedback_layout',
            'scope': 'deck', 'template_id': 'fixture-pack',
            'pages': {'p1': {'revision': revision, 'layout_id': 'p02_content'}}}, True)
        stored = store.commit(self.root, {'op': 'task', 'task_id': task['task_id']})['task']
        self.assertEqual(stored['template_id'], 'fixture-pack')
        self.assertEqual(stored['pages']['p1']['layout_id'], 'p02_content')

    def test_whole_template_request_may_have_no_pages(self):
        task = store.commit(self.root, {'op': 'feedback', 'operation_id': 'feedback_template_only',
            'scope': 'deck', 'template_id': 'fixture-pack', 'pages': {}}, True)
        self.assertTrue(task['ok'])
        self.assertEqual(store.commit(self.root, {'op': 'task', 'task_id': task['task_id']})['task']['pages'], {})
        resolved = store.commit(self.root, {'op': 'resolve', 'operation_id': 'resolve_template_only',
            'task_id': task['task_id'], 'results': {}, 'note': 'Applied the whole template; no page reworked'})
        self.assertTrue(resolved['ok'])
        empty = store.commit(self.root, {'op': 'feedback', 'operation_id': 'feedback_empty',
            'scope': 'deck', 'pages': {}}, True)
        self.assertFalse(empty['ok'])
        self.assertEqual(empty['code'], 'invalid_feedback')

    def test_model_save_records_layout_reference_and_human_cannot(self):
        result = self.candidate(layout_id='p02_content')
        self.assertTrue(result['ok'])
        self.assertEqual(store.get_page(self.root, 'p1')['layout_id'], 'p02_content')
        refused = self.save(layout_id='p02_content')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['code'], 'invalid_layout')
        invalid = self.candidate(layout_id='bad layout id')
        self.assertFalse(invalid['ok'])
        self.assertEqual(invalid['code'], 'invalid_layout')

    def test_restore_creates_new_revision(self):
        old = store.get_page(self.root, 'p1')['revision']
        new = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'New'}])
        restored = store.commit(self.root, {'op': 'restore', 'operation_id': 'restore_1',
            'page_key': 'p1', 'base_revision': new['revision'], 'revision': old}, True)
        self.assertTrue(restored['ok'])
        self.assertNotEqual(restored['revision'], old)
        self.assertIn('Original', store.get_page(self.root, 'p1')['svg'])

    def test_missing_view_rebuilt_and_external_write_preserved(self):
        path = self.root / store.VIEW / 'p1.svg'
        path.unlink()
        store.ensure(self.root)
        self.assertTrue(path.is_file())
        path.write_text('user external edit')
        with self.assertRaises(store.StoreError) as caught:
            store.ensure(self.root)
        self.assertEqual(caught.exception.code, 'external_write')
        self.assertEqual(path.read_text(), 'user external edit')

    def test_snapshot_stays_immutable_while_editing(self):
        snap = store.snapshot(self.root)
        path = Path(snap['root']) / snap['pages'][0]['svg']
        before = path.read_bytes()
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'New'}])
        self.assertEqual(path.read_bytes(), before)
        next_snap = store.snapshot(self.root)
        self.assertEqual(next_snap['content_binding'], 'changed_needs_check')
        self.assertEqual(next_snap['pages'][0]['content_delta'][0]['after'], 'New')

    def test_selected_snapshot_is_independent_of_live_pages(self):
        saved = store.snapshot(self.root)
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Later edit'}])
        loaded = store.load_snapshot(self.root, saved['path'])
        self.assertEqual(loaded['snapshot_id'], saved['snapshot_id'])
        self.assertNotIn('Later edit', (Path(loaded['root']) / loaded['pages'][0]['svg']).read_text())

    def test_selected_snapshot_mutation_is_rejected(self):
        saved = store.snapshot(self.root)
        path = Path(saved['root']) / saved['pages'][0]['svg']
        path.write_text('mutated')
        with self.assertRaises(store.StoreError) as caught:
            store.load_snapshot(self.root, saved['path'])
        self.assertEqual(caught.exception.code, 'damaged_snapshot')

    def test_late_render_cannot_replace_new_preview(self):
        old = store.get_page(self.root, 'p1')['revision']
        new = self.save(notes='new')['revision']
        first = self.write('new.png', 'new png')
        store.record_render(self.root, 'p1', new, first, 'test/1')
        old_png = self.write('old.png', 'old png')
        store.record_render(self.root, 'p1', old, old_png, 'test/1')
        self.assertEqual((self.root / '_internal/03_png_preview/pages/p1.png').read_text(), 'new png')

    def test_assets_are_pinned_across_same_name_replacement(self):
        self.write('pic.png', 'first bytes')
        current = store.get_page(self.root, 'p1')
        svg = current['svg'].replace('</svg>', '<image href="pic.png" width="10" height="10"/></svg>')
        added = self.candidate(svg)
        self.assertTrue(added['ok'])
        saved = store.get_page(self.root, 'p1')
        self.write('pic.png', 'changed bytes')
        snap = store.snapshot(self.root)
        asset = snap['pages'][0]['assets'][0]
        self.assertEqual((Path(snap['root']) / asset['path']).read_text(), 'first bytes')
        self.assertEqual(store.get_page(self.root, 'p1')['revision'], saved['revision'])

    def test_browser_cannot_supply_model_candidate(self):
        current = store.get_page(self.root, 'p1')
        result = store.commit(self.root, {'op': 'save', 'operation_id': 'malicious', 'page_key': 'p1',
            'base_revision': current['revision'], 'author': 'model', 'candidate': 'x.svg'}, True)
        self.assertEqual(result['code'], 'invalid_author')

    def test_checkout_keeps_assets_resolvable(self):
        self.write('pic.png', 'image bytes')
        current = store.get_page(self.root, 'p1')
        self.assertTrue(self.candidate(current['svg'].replace('</svg>', '<image href="pic.png"/></svg>'))['ok'])
        checkout = store.commit(self.root, {'op': 'checkout', 'operation_id': 'checkout_1', 'page_key': 'p1'})
        result = store.commit(self.root, {'op': 'save', 'operation_id': 'submit_1', 'page_key': 'p1',
            'base_revision': checkout['base_revision'], 'candidate': checkout['candidate'], 'author': 'model'})
        self.assertTrue(result['ok'])

    def test_crash_after_head_switch_rebuilds_view(self):
        current = store.get_page(self.root, 'p1')
        old_bytes = (self.root / store.VIEW / 'p1.svg').read_bytes()
        self.save(notes='new')
        (self.root / store.VIEW / 'p1.svg').write_bytes(old_bytes)
        store.ensure(self.root)
        self.assertNotEqual(store.get_page(self.root, 'p1')['revision'], current['revision'])

    def bind_video(self):
        script = self.write('upstream/script.md', 'Recorded script')
        plan = self.write('upstream/visual-plan.json', json.dumps({'contract_version': '5.0',
            'title': 'Video', 'script_hash': store.digest(script.read_bytes()),
            'screens': [{'screen_id': 'p1', 'beat_id': 'beat_1'}, {'screen_id': 'p2', 'beat_id': 'beat_2'}]}))
        self.write('_internal/00_project/page_manifest.json', json.dumps({'version': '5.0', 'route': 'video',
            'visual_plan': {'path': str(plan), 'sha256': store.digest(plan.read_bytes()),
                            'script_hash': store.digest(script.read_bytes()), 'contract_version': '5.0'}}))
        head = json.loads((self.root / store.STORE / 'head.json').read_text())
        head['route'] = 'video'
        store.atomic(self.root / store.STORE / 'head.json', store.encoded(head))
        return script, plan

    def test_video_snapshots_preserve_declared_script_binding(self):
        script, plan = self.bind_video()
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Different on-screen text'}])
        snap = store.snapshot(self.root, 'video')
        original = json.loads(plan.read_text())
        copied = json.loads((Path(snap['root']) / 'upstream/visual-plan.json').read_text())
        self.assertEqual(original, copied)
        self.assertEqual(snap['content_binding'], 'changed_needs_check')
        self.assertEqual((Path(snap['root']) / 'upstream/script.md').read_bytes(), script.read_bytes())

    def test_video_collection_delta_preserves_original_plan(self):
        _, plan = self.bind_video()
        original = plan.read_bytes()
        self.assertTrue(self.add_page('new')['ok'])
        snap = store.snapshot(self.root, 'video')
        self.assertEqual(snap['collection_delta'], {'added': ['new'], 'removed': []})
        self.assertEqual(snap['content_binding'], 'changed_needs_check')
        self.assertEqual((Path(snap['root']) / 'upstream/visual-plan.json').read_bytes(), original)

    def test_delete_conflicts_with_new_human_revision(self):
        old = store.get_page(self.root, 'p1')['revision']
        self.save([{'element_id':'title','kind':'text','value':'Keep human edit'}])
        result = store.commit(self.root, {'op':'delete_page','operation_id':'stale_delete',
            'page_key':'p1','base_revision':old,'base_order':['p1','p2']})
        self.assertFalse(result['ok'])
        self.assertIn('p1', store.ensure(self.root)['order'])

    def test_changed_upstream_script_blocks_false_binding(self):
        script, _ = self.bind_video()
        script.write_text('New script after intake')
        with self.assertRaises(store.StoreError) as caught:
            store.snapshot(self.root, 'video')
        self.assertEqual(caught.exception.code, 'script_changed')

    def test_failed_save_does_not_claim_success(self):
        old = store.get_page(self.root, 'p1')['revision']
        result = self.save([{'element_id': 'missing', 'kind': 'text', 'value': 'Lost'}])
        self.assertFalse(result['ok'])
        self.assertEqual(store.get_page(self.root, 'p1')['revision'], old)

    def test_saved_assets_are_detected_if_mutated(self):
        self.write('pic.png', 'original')
        current = store.get_page(self.root, 'p1')
        saved = self.candidate(current['svg'].replace('</svg>', '<image href="pic.png"/></svg>'))
        record = store.get_page(self.root, 'p1')
        (store.revision_dir(self.root, saved['revision']) / record['assets'][0]['path']).write_text('tampered')
        with self.assertRaises(store.StoreError) as caught:
            store.snapshot(self.root)
        self.assertEqual(caught.exception.code, 'damaged_revision')

    def test_nested_svg_asset_dependencies_are_pinned(self):
        self.write('nested/pic.png', 'first nested image')
        self.write('nested/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg"><image href="pic.png"/></svg>')
        current = store.get_page(self.root, 'p1')
        result = self.candidate(current['svg'].replace('</svg>', '<image href="nested/icon.svg"/></svg>'))
        self.assertTrue(result['ok'])
        self.write('nested/pic.png', 'second nested image')
        snap = store.snapshot(self.root)
        outer = snap['pages'][0]['assets'][0]
        self.assertEqual(len(outer['dependencies']), 1)
        parent = Path(snap['root']) / outer['path']
        image = next(n for n in ET.fromstring(parent.read_text()).iter() if n.tag.split('}')[-1] == 'image')
        self.assertEqual((parent.parent / image.get('href')).read_text(), 'first nested image')

    def test_nested_svg_image_cycles_are_rejected(self):
        self.write('loop.svg', '<svg xmlns="http://www.w3.org/2000/svg"><image href="loop.svg"/></svg>')
        current = store.get_page(self.root, 'p1')
        result = self.candidate(current['svg'].replace('</svg>', '<image href="loop.svg"/></svg>'))
        self.assertEqual(result['code'], 'cyclic_asset')


    # ── 2026-11-11：人改过的字，位置也归人 ──────────────────────────────

    def test_human_text_edit_pins_the_element_position(self):
        """人改过字之后，模型不能悄悄把它挪走（此前只锁文字，位置是自由的）。"""
        first = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Human copy'}])
        guard = store.revision_record(self.root, first['revision'])['protected']['title']
        self.assertEqual(guard['attributes'].get('x'), '10')
        self.assertEqual(guard['attributes'].get('y'), '20')
        current = store.get_page(self.root, 'p1')
        moved = current['svg'].replace('x="10" y="20"', 'x="80" y="60"')
        result = self.candidate(moved)
        self.assertEqual(result['code'], 'human_edits_lost', result)
        self.assertIn('title', result['elements'])
        self.assertEqual(result['guards']['title']['attributes']['x'], '10')

    def test_position_is_still_pinned_when_guard_predates_geometry(self):
        """老修订只记了文字、没记位置：按它现在的位置补上，不留「位置自由」的缺口。"""
        saved = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Legacy guard'}])
        record_path = store.revision_dir(self.root, saved['revision']) / 'revision.json'
        record = json.loads(record_path.read_text())
        record['protected']['title'].pop('attributes', None)
        record_path.write_text(json.dumps(record))
        current = store.get_page(self.root, 'p1')
        result = self.candidate(current['svg'].replace('x="10" y="20"', 'x="80" y="60"'))
        self.assertEqual(result['code'], 'human_edits_lost', result)
        self.assertIn('title', result['elements'])

    def test_human_edit_updates_the_copy_baseline(self):
        """人改的文案要进基线：轨道标题和 copy audit 不能继续挂着旧句子。"""
        self.write('_internal/01_content/page_content.json', json.dumps({'pages': [
            {'page_key': 'p1', 'title': 'First Original', 'content': 'Original'},
            {'page_key': 'p2', 'title': 'Second', 'content': ''}]}))
        result = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'Human copy'}])
        self.assertTrue(result['ok'])
        content = json.loads((self.root / '_internal/01_content/page_content.json').read_text())
        entry = next(page for page in content['pages'] if page['page_key'] == 'p1')
        self.assertEqual(entry['title'], 'First Human copy')
        self.assertIn('Human copy', entry['content'])
        head = store.commit(self.root, {'op': 'state'})
        self.assertEqual(head['pages']['p1']['title'], 'First Human copy')

    def test_save_queues_a_render_only_when_asked(self):
        calls = []
        original = store._queue_render
        store._queue_render = lambda root, key, revision: calls.append((key, revision)) or True
        try:
            quiet = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'no render'}])
            self.assertFalse(quiet['rendered'])
            loud = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'render please'}], render=True)
            self.assertEqual(loud['rendered'], 'queued')
        finally:
            store._queue_render = original
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'p1')

    def test_stale_revision_render_is_skipped_instead_of_overwriting(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import render_revision
        old = self.save([{'element_id': 'title', 'kind': 'text', 'value': 'first'}])['revision']
        self.save([{'element_id': 'title', 'kind': 'text', 'value': 'second'}])
        self.assertEqual(render_revision.current_revision(self.root, 'p1') != old, True)
        out = render_revision.main(['render_revision.py', str(self.root), 'p1', old])
        self.assertEqual(out, 0)


if __name__ == '__main__':
    unittest.main()
