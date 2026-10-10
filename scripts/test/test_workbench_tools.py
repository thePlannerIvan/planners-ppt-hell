"""Browser boundaries for in-place refresh, feedback receipts and text tools.

Run with PPT_WORKBENCH_BROWSER_TESTS=1 using the existing skills Python env.
The loader selects only this file's tests, not the inherited harness tests.
"""
import re
import unittest
import xml.etree.ElementTree as ET

if __package__:
    from . import test_workbench_ui as harness
else:
    import test_workbench_ui as harness


class WorkbenchToolsTests(harness.WorkbenchBrowserTests):
    def setUp(self):
        # The shared harness predates cleanup on partial browser initialization.
        for name, method in (('tmp', 'cleanup'), ('playwright', 'stop'),
                             ('browser', 'close'), ('context', 'close')):
            self.addCleanup(self.cleanup_resource, name, method)
        try:
            super().setUp()
        except Exception:
            if getattr(self, 'errors', None):
                self.fail('Workbench did not boot: ' + '; '.join(self.errors))
            raise
        self.page.set_default_timeout(5000)
        try:
            self.page.wait_for_function("document.documentElement.dataset.workbenchReady==='true'")
        except Exception:
            if self.errors:
                self.fail('Workbench did not boot: ' + '; '.join(self.errors))
            raise
        self.page.evaluate('() => onHostChanged()')
        self.calls.clear()
        self.wakes.clear()

    def cleanup_resource(self, name, method):
        resource = getattr(self, name, None)
        if resource is not None:
            getattr(resource, method)()

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def require_tools(self):
        self.assertTrue(self.page.evaluate("""() =>
          typeof updateFindMatches==='function'&&typeof goFindMatch==='function'
          &&typeof replaceMatches==='function'&&typeof undoReplaceBatch==='function'
          &&['findPanel','findQuery','replaceValue','findScope','findCount','findNext',
             'findPrev','replaceOne','replaceAll','replaceDialog','confirmReplaceAll']
            .every(id=>document.getElementById(id))"""), 'Find/replace interface is not implemented')

    def configure_find(self, query, replacement='', scope='page'):
        self.require_tools()
        self.page.evaluate("""async ({query,replacement,scope}) => {
          if(typeof toggleFind==='function')toggleFind(true);
          else document.querySelector('#findPanel').hidden=false;
          for(const [id,value] of [['findQuery',query],['replaceValue',replacement],['findScope',scope]]){
            const el=document.getElementById(id);el.value=value;
            el.dispatchEvent(new Event(id==='findScope'?'change':'input',{bubbles:true}));
          }
          await updateFindMatches();
        }""", {'query': query, 'replacement': replacement, 'scope': scope})

    def assert_find_count(self, expected):
        label = self.page.locator('#findCount').inner_text()
        counts = re.findall(r'\d+', label)
        self.assertTrue(counts, label)
        self.assertEqual(int(counts[-1]), expected, label)

    def set_heading(self, key, text):
        current = harness.get_page(self.root, key)
        result = harness.commit(self.root, {
            'op': 'save', 'operation_id': f'fixture_{key}_{len(self.calls)}',
            'page_key': key, 'base_revision': current['revision'], 'author': 'human',
            'edits': [{'element_id': 'heading', 'kind': 'text', 'value': text}],
        }, browser=True)
        self.assertTrue(result['ok'], result)
        self.page.evaluate('() => onHostChanged()')

    def feedback_draft(self, feedback='First feedback'):
        self.page.evaluate("""feedback => {
          const s=state[page().key];s.feedback=feedback;
          s.annotations=[{id:'first-box',x:.1,y:.1,w:.2,h:.2,text:'First annotation',targets:[]}];
          s.assets=[{asset_key:'photo',operation:'replace',fit:'contain',ratio:'original'}];
          s.rewrite_elements=['heading'];
          document.querySelector('#feedback').value=s.feedback;drawRegions();status();
        }""", feedback)

    def feedback_calls(self):
        return [body for body in self.calls if body.get('op') == 'feedback']

    def history_text(self):
        self.page.evaluate("() => document.querySelector('#historySection').open=true")
        return self.page.locator('#feedbackHistory').inner_text()

    def confirm_replace_all(self):
        self.page.locator('#replaceAll').click()
        self.assertTrue(self.page.locator('#replaceDialog').is_visible())
        self.page.locator('#confirmReplaceAll').click()
        self.page.wait_for_function("!document.querySelector('#replaceDialog').open")
        return self.flush()

    def test_refresh_saves_then_syncs_without_navigation_or_wake(self):
        self.page.evaluate('() => go(1)')
        self.page.wait_for_function("page().key==='omega'&&document.querySelector('#title').textContent.includes('omega')")
        self.edit('Unsaved omega text')
        self.page.locator('#feedback').fill('Keep new omega feedback')
        self.page.evaluate("() => {clearTimeout(saveTimer);window.__documentToken='same-document'}")
        self.calls.clear()
        self.page.evaluate('() => askReload()')
        self.assertEqual(self.page.evaluate('() => window.__documentToken'), 'same-document')
        self.assertEqual(self.page.evaluate('() => page().key'), 'omega')
        self.assertEqual(self.text('omega'), 'Unsaved omega text')
        self.assertEqual(self.page.locator('#feedback').input_value(), 'Keep new omega feedback')
        operations = [body['op'] for body in self.calls]
        self.assertIn('save', operations)
        self.assertIn('state', operations)
        self.assertLess(operations.index('save'), operations.index('state'))
        self.assertEqual(self.wakes, [])

    def test_refresh_merges_remote_page_without_erasing_new_feedback(self):
        self.page.locator('#feedback').fill('New local feedback')
        current = harness.get_page(self.root, 'alpha')
        result = harness.commit(self.root, {
            'op': 'save', 'operation_id': 'remote_refresh', 'page_key': 'alpha',
            'base_revision': current['revision'], 'author': 'human',
            'edits': [{'element_id': 'heading', 'kind': 'text', 'value': 'Remote current text'}],
        }, browser=True)
        self.assertTrue(result['ok'])
        self.page.evaluate("() => {window.__documentToken='same-document'}")
        self.page.evaluate('() => askReload()')
        self.assertEqual(self.page.evaluate('() => window.__documentToken'), 'same-document')
        self.assertEqual(self.page.locator('#svgStageWrap text').first.text_content(), 'Remote current text')
        self.assertEqual(self.page.locator('#feedback').input_value(), 'New local feedback')
        self.assertEqual(self.wakes, [])

    def test_refresh_lost_save_receipt_keeps_input_and_recovery(self):
        self.edit('Unconfirmed refresh edit')
        self.page.locator('#feedback').fill('Unsaved feedback stays')
        self.page.evaluate("() => {clearTimeout(saveTimer);window.__documentToken='same-document'}")
        self.fail_next = 'save'
        self.page.evaluate('() => askReload()')
        self.assertEqual(self.page.evaluate('() => window.__documentToken'), 'same-document')
        self.assertEqual(self.page.locator('#feedback').input_value(), 'Unsaved feedback stays')
        self.assertIn('Unconfirmed refresh edit', self.page.locator('#svgStageWrap').inner_text())
        self.assertIsNotNone(self.page.evaluate('() => state.alpha.pending_save'))
        self.assertNotEqual(self.page.evaluate('() => state.alpha.save_status'), 'clean')
        self.assertEqual(self.wakes, [])

    def test_history_preview_is_read_only_and_cancelled_restore_keeps_current_svg(self):
        historical = harness.get_page(self.root, 'alpha')['revision']
        self.edit('Current durable version')
        self.assertTrue(self.flush())
        current = harness.get_page(self.root, 'alpha')['revision']
        self.page.locator('#feedback').fill('Keep feedback while viewing history')
        head_before = harness.ensure(self.root)
        svg_path = self.root / harness.SVG / 'alpha.svg'
        svg_before = svg_path.read_bytes()
        self.calls.clear()
        self.wakes.clear()

        self.page.locator('#versionMenu summary').click()
        self.page.locator('#historyRevision').select_option(historical)
        self.page.wait_for_function("previous&&document.querySelector('#svgStageWrap text').textContent==='Original'")
        self.assertTrue(any(body.get('op') == 'get' and body.get('page_key') == 'alpha'
                            and body.get('revision') == historical for body in self.calls))
        self.assertEqual(self.page.evaluate('() => page().revision'), current)
        self.page.locator('#svgStageWrap text').first.dblclick()
        self.assertFalse(self.page.locator('#inlineCanvasEditor').is_visible())
        self.assertTrue(self.page.locator('#inlineTextInput').is_disabled())
        self.page.locator('#restoreRevision').click()
        self.assertTrue(self.page.locator('#restoreDialog').is_visible())
        self.assertFalse(any(body.get('op') == 'restore' for body in self.calls))
        self.page.locator('#restoreDialog').get_by_text('取消', exact=True).click()

        self.page.locator('#historyRevision').select_option(current)
        self.page.wait_for_function("!previous&&document.querySelector('#svgStageWrap text').textContent==='Current durable version'")
        self.assertTrue(self.page.locator('#restoreRevision').is_disabled())
        self.assertEqual(self.page.locator('#feedback').input_value(), 'Keep feedback while viewing history')
        self.assertEqual(harness.ensure(self.root), head_before)
        self.assertEqual(svg_path.read_bytes(), svg_before)
        self.assertEqual(self.text(), 'Current durable version')
        self.assertTrue(all(body.get('op') in ('get', 'state') for body in self.calls), self.calls)
        self.assertEqual(self.wakes, [])

    def test_page_feedback_moves_to_tasks_and_next_dispatch_contains_only_new_input(self):
        self.feedback_draft()
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('page')"))
        self.assertEqual(self.page.evaluate("""() => {
          const s=state.alpha;return [s.feedback,s.annotations,s.assets,s.rewrite_elements]
        }"""), ['', [], [], []])
        self.assertEqual(self.page.locator('#feedback').input_value(), '')
        self.assertIn('First feedback', self.page.locator('#pendingTasks').inner_text())
        self.assertNotIn('First feedback', self.page.locator('#feedbackHistory').inner_text())
        self.assertEqual(self.page.locator('.canvas-region-box').count(), 0)
        self.page.locator('#feedback').fill('Second feedback only')
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('page')"))
        submitted = self.feedback_calls()[-1]['pages']['alpha']
        self.assertEqual(submitted['feedback'], 'Second feedback only')
        for key in ('annotations', 'assets', 'rewrite_elements'):
            self.assertEqual(submitted[key], [])
        self.assertEqual(len(harness.ensure(self.root)['tasks']), 2)

    def test_deck_feedback_clears_only_submitted_drafts(self):
        self.feedback_draft('Alpha deck feedback')
        self.page.evaluate("""() => {
          state.omega.feedback='Omega deck feedback';
          document.querySelector('#overall').value='Overall deck feedback';
        }""")
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('deck')"))
        submitted = self.feedback_calls()[-1]
        self.assertEqual(set(submitted['pages']), {'alpha', 'omega'})
        self.assertEqual(submitted['overall_feedback'], 'Overall deck feedback')
        self.assertEqual(self.page.evaluate('() => [state.alpha.feedback,state.omega.feedback]'), ['', ''])
        self.assertEqual(self.page.locator('#overall').input_value(), '')
        self.page.locator('#feedback').fill('Next deck feedback')
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('deck')"))
        next_command = self.feedback_calls()[-1]
        self.assertEqual(next_command['pages']['alpha']['feedback'], 'Next deck feedback')
        self.assertFalse(any(item['feedback'] == 'Omega deck feedback' for item in next_command['pages'].values()))
        self.assertEqual(next_command['overall_feedback'], '')

    def test_feedback_added_while_receipt_is_pending_survives(self):
        self.feedback_draft()
        self.page.evaluate("""() => {
          const original=review.command;
          review.command=async command=>{
            if(command.op==='feedback'){
              window.__submittedCommand=structuredClone(command);
              await new Promise(resolve=>window.__releaseFeedback=resolve);
            }
            return original(command);
          };
          window.__dispatchPromise=dispatchFeedback('page');
        }""")
        self.page.wait_for_function("typeof window.__releaseFeedback==='function'")
        self.page.evaluate(r"""() => {
          const s=state.alpha;
          s.feedback+='\nAdded during submit';
          s.annotations.push({id:'second-box',x:.4,y:.4,w:.1,h:.1,text:'New annotation',targets:[]});
          s.assets.push({asset_key:'new-photo',operation:'add',fit:'contain',ratio:'original'});
          s.rewrite_elements.push('another-text');
          document.querySelector('#feedback').value=s.feedback;
          window.__releaseFeedback();
        }""")
        self.assertTrue(self.page.evaluate('() => window.__dispatchPromise'))
        draft = self.page.evaluate('() => state.alpha')
        self.assertIn('Added during submit', draft['feedback'])
        self.assertNotIn('First feedback', draft['feedback'])
        self.assertEqual([item['id'] for item in draft['annotations']], ['second-box'])
        self.assertEqual([item['asset_key'] for item in draft['assets']], ['new-photo'])
        self.assertEqual(draft['rewrite_elements'], ['another-text'])
        self.assertNotIn('Added during submit', self.feedback_calls()[-1]['pages']['alpha']['feedback'])

    def test_feedback_failure_keeps_draft_and_retry_identity(self):
        self.feedback_draft()
        self.fail_next = 'feedback'
        self.assertFalse(self.page.evaluate("() => dispatchFeedback('page')"))
        # An in-flight snapshot may live in the retry queue instead of the new-input slot.
        draft = self.page.evaluate('() => pendingDispatch?.pages.alpha||state.alpha')
        self.assertEqual(draft['feedback'], 'First feedback')
        self.assertEqual(len(draft['annotations']), 1)
        self.assertEqual(len(draft['assets']), 1)
        self.assertEqual(draft['rewrite_elements'], ['heading'])
        self.assertIn('First feedback', self.page.locator('#pendingTasks').inner_text())
        self.assertEqual(self.server_draft['pending_dispatch']['pages']['alpha']['feedback'], 'First feedback')
        self.assertEqual(self.wakes, [])
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('page')"))
        commands = self.feedback_calls()
        self.assertEqual(commands[0]['operation_id'], commands[1]['operation_id'])
        self.assertEqual(len(harness.ensure(self.root)['tasks']), 1)

    def test_deck_feedback_added_during_submission_preserves_overall_and_other_page(self):
        self.page.locator('#feedback').fill('Initial deck feedback')
        self.page.evaluate("""() => {
          state.omega.feedback='Initial omega feedback';
          document.querySelector('#overall').value='Initial overall';
          const original=review.command;
          review.command=async command=>{
            if(command.op==='feedback')await new Promise(resolve=>window.__releaseFeedback=resolve);
            return original(command);
          };
          window.__dispatchPromise=dispatchFeedback('deck');
        }""")
        self.page.wait_for_function("typeof window.__releaseFeedback==='function'")
        self.page.evaluate(r"""() => {
          state.omega.feedback+='\nNew omega feedback';
          document.querySelector('#overall').value+='\nNew overall feedback';
          window.__releaseFeedback();
        }""")
        self.assertTrue(self.page.evaluate('() => window.__dispatchPromise'))
        self.assertIn('New omega feedback', self.page.evaluate('() => state.omega.feedback'))
        self.assertNotIn('Initial omega feedback', self.page.evaluate('() => state.omega.feedback'))
        self.assertIn('New overall feedback', self.page.locator('#overall').input_value())
        self.assertNotIn('Initial overall', self.page.locator('#overall').input_value())
        self.assertEqual(self.feedback_calls()[-1]['overall_feedback'], 'Initial overall')

    def test_pending_task_surface_hydrates_from_store_without_local_dispatch(self):
        result = harness.commit(self.root, {
            'op': 'feedback', 'operation_id': 'external_task', 'scope': 'page',
            'pages': {'alpha': {'revision': harness.get_page(self.root, 'alpha')['revision'],
                                'feedback': 'External persisted feedback', 'annotations': [],
                                'assets': [], 'rewrite_elements': []}},
        }, browser=True)
        self.assertTrue(result['ok'], result)
        self.page.evaluate('() => onHostChanged()')
        self.assertIn('External persisted feedback', self.page.locator('#pendingTasks').inner_text())
        self.assertEqual(self.page.evaluate('() => state.alpha.feedback'), '')
        self.assertEqual(self.wakes, [])

    def test_resolved_store_task_is_history_only_without_old_regions(self):
        self.feedback_draft()
        self.assertTrue(self.page.evaluate("() => dispatchFeedback('page')"))
        task = next(iter(harness.ensure(self.root)['tasks'].values()))
        result = harness.commit(self.root, {
            'op': 'resolve', 'operation_id': 'resolve_fixture', 'task_id': task['task_id'],
            'note': 'Completed task', 'results': {'alpha': harness.get_page(self.root, 'alpha')['revision']},
        })
        self.assertTrue(result['ok'], result)
        self.page.evaluate('() => onHostChanged()')
        self.assertNotIn('First feedback', self.page.locator('#pendingTasks').inner_text())
        self.assertIn('First feedback', self.history_text())
        self.assertEqual(self.page.locator('.canvas-region-box').count(), 0)
        self.page.reload()
        self.page.wait_for_function("document.documentElement.dataset.workbenchReady==='true'")
        self.page.evaluate('() => onHostChanged()')
        self.assertIn('First feedback', self.history_text())
        self.assertEqual(self.page.locator('#feedback').input_value(), '')
        self.assertEqual(self.page.locator('.canvas-region-box').count(), 0)

    def test_find_page_deck_navigation_empty_query_and_literal_matching(self):
        self.page.evaluate("""() => {
          page().title='Original';state.alpha.notes='Original';state.alpha.feedback='Original';
        }""")
        self.configure_find('Original')
        self.assert_find_count(1)
        self.configure_find('Original', scope='deck')
        self.assert_find_count(2)
        self.page.locator('#findNext').click()
        first = self.page.evaluate('() => page().key')
        self.page.evaluate('() => goFindMatch(1)')
        second = self.page.evaluate('() => page().key')
        self.assertNotEqual(first, second)
        self.page.locator('#findPrev').click()
        self.assertEqual(self.page.evaluate('() => page().key'), first)
        self.configure_find('')
        self.assert_find_count(0)
        self.page.evaluate('() => goFindMatch(1)')
        self.page.evaluate('() => replaceMatches(false)')
        self.assertTrue(self.flush())
        self.assertEqual(self.text(), 'Original')
        self.assertEqual(self.text('omega'), 'Original')
        self.set_heading('alpha', 'Literal [x].* token')
        self.set_heading('omega', 'Literal xxxx token')
        self.configure_find('[x].*', scope='deck')
        self.assert_find_count(1)
        self.assertEqual(self.wakes, [])

    def test_replace_one_is_literal_and_page_scoped_without_wake(self):
        self.set_heading('alpha', 'Original Original')
        self.configure_find('Original', '$&')
        self.assert_find_count(2)
        self.page.evaluate('() => replaceMatches(false)')
        self.assertTrue(self.flush())
        self.assertEqual(self.text(), '$& Original')
        self.assertEqual(self.text('omega'), 'Original')
        self.assertEqual(self.wakes, [])

    def test_replace_all_requires_confirmation_and_supports_cross_page_undo(self):
        self.configure_find('Original', 'Batch replacement', scope='deck')
        self.page.locator('#replaceAll').click()
        self.assertTrue(self.page.locator('#replaceDialog').is_visible())
        self.assertEqual(self.text(), 'Original')
        self.assertEqual(self.text('omega'), 'Original')
        self.page.locator('#confirmReplaceAll').click()
        self.page.wait_for_function("!document.querySelector('#replaceDialog').open")
        self.assertTrue(self.flush())
        self.assertEqual(self.text(), 'Batch replacement')
        self.assertEqual(self.text('omega'), 'Batch replacement')
        self.page.evaluate('() => undoReplaceBatch()')
        self.assertTrue(self.flush())
        self.assertEqual(self.text(), 'Original')
        self.assertEqual(self.text('omega'), 'Original')
        self.assertEqual(self.wakes, [])

    def test_replace_multiline_keeps_tspan_identity_style_and_animation(self):
        before = ET.fromstring(harness.get_page(self.root, 'alpha')['svg'])
        spans_before = [dict(node.attrib) for node in before.iter() if node.tag.endswith('tspan')]
        multiline_before = next(node for node in before.iter() if node.tag.endswith('text') and list(node))
        heading_before = next(node for node in before.iter() if node.get('id') == 'heading')
        self.configure_find('Line', 'Row')
        self.assertTrue(self.confirm_replace_all())
        after = ET.fromstring(harness.get_page(self.root, 'alpha')['svg'])
        spans_after = [node for node in after.iter() if node.tag.endswith('tspan')]
        self.assertEqual([node.text for node in spans_after], ['Row one', 'Row two'])
        self.assertEqual([dict(node.attrib) for node in spans_after], spans_before)
        multiline_after = next(node for node in after.iter() if node.tag.endswith('text') and list(node))
        self.assertEqual(multiline_after.attrib, multiline_before.attrib)
        heading_after = next(node for node in after.iter() if node.get('id') == 'heading')
        self.assertEqual(heading_after.attrib, heading_before.attrib)
        self.assertEqual(heading_after.text, heading_before.text)
        self.assertEqual(self.wakes, [])

    def test_replace_failed_save_keeps_query_replacement_and_recovery(self):
        self.configure_find('Original', 'Recoverable replacement')
        self.fail_next = 'save'
        self.page.evaluate('() => replaceMatches(false)')
        self.page.evaluate('() => clearTimeout(saveTimer)')
        # Replacement may save immediately or defer to the existing autosave path.
        if self.fail_next:
            self.assertFalse(self.flush())
        self.assertEqual(self.page.locator('#findQuery').input_value(), 'Original')
        self.assertEqual(self.page.locator('#replaceValue').input_value(), 'Recoverable replacement')
        self.assertIsNotNone(self.page.evaluate('() => state.alpha.pending_save'))
        self.assertIn('Recoverable replacement', str(self.page.evaluate('() => state.alpha.svg_edits')))
        self.assertEqual(self.wakes, [])

    def test_collapse_panel_expands_canvas_and_restores_without_overlap(self):
        self.assertEqual(self.page.locator('#togglePanel').count(), 1, 'Panel toggle is not implemented')
        self.assertTrue(self.page.locator('#reviewPanel').is_visible())
        before = self.page.locator('#preview').bounding_box()
        self.page.locator('#togglePanel').click()
        self.page.wait_for_function("document.querySelector('#reviewPanel').hidden||getComputedStyle(document.querySelector('#reviewPanel')).display==='none'")
        after = self.page.locator('#preview').bounding_box()
        self.assertGreater(after['width'], before['width'])
        self.assertLessEqual(after['x'] + after['width'], 1440)
        self.page.locator('#togglePanel').click()
        self.assertTrue(self.page.locator('#reviewPanel').is_visible())
        self.assertEqual(self.wakes, [])
        self.assertEqual(self.errors, [])


def load_tests(loader, tests, pattern):
    names = [name for name in WorkbenchToolsTests.__dict__ if name.startswith('test_')]
    return unittest.TestSuite(WorkbenchToolsTests(name) for name in sorted(names))


if __name__ == '__main__':
    unittest.main()
