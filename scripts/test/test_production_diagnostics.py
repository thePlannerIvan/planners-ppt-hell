"""Real edit failures: unchanged href, poor image fit, stale copy and cached errors."""
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS/'orchestrate'))
import workbench_store as store
import ppt_pipeline as pipeline
import project_state as ps
from image_diagnostics import image_frames
from copy_audit import audit_copy
import test_workbench_store as store_fixtures
import test_workbench_pipeline as pipeline_fixtures


class ReceiptTests(unittest.TestCase):
    setUp = store_fixtures.WorkbenchTests.setUp
    tearDown = store_fixtures.WorkbenchTests.tearDown
    write = store_fixtures.WorkbenchTests.write
    candidate = store_fixtures.WorkbenchTests.candidate
    save = store_fixtures.WorkbenchTests.save

    def image_candidate(self):
        Image.new('RGB', (20, 40), 'red').save(self.root/'portrait.png')
        current = store.get_page(self.root, 'p1')['svg']
        return self.candidate(current.replace('</svg>', '<image id="photo" href="portrait.png" width="20" height="40"/></svg>'))

    def checkout_save(self, change=None, **extra):
        checked = store.commit(self.root, {'op':'checkout','operation_id':'checkout_'+store.uuid.uuid4().hex,'page_key':'p1'})
        path = Path(checked['candidate'])
        if change:
            path.write_text(change(path.read_text(), path))
        command = {'op':'save','operation_id':'save_'+store.uuid.uuid4().hex,'page_key':'p1',
                   'base_revision':checked['base_revision'],'candidate':str(path),**extra}
        return store.commit(self.root, command), command

    def test_failed_filename_replacement_and_path_freezing_report_no_change(self):
        self.assertTrue(self.image_candidate()['ok'])
        result, command = self.checkout_save(lambda text, _: text.replace('not-present.jpg','another.jpg'))
        self.assertEqual(result['warnings'], ['no_change'])
        self.assertEqual(result['changes']['image_elements'], [])
        self.assertEqual(store.commit(self.root, command), result)

    def test_same_bytes_at_new_filename_is_no_change(self):
        self.image_candidate()
        (self.root/'renamed.png').write_bytes((self.root/'portrait.png').read_bytes())
        def edit(text, path):
            import os
            import xml.etree.ElementTree as ET
            tree=ET.fromstring(text)
            next(n for n in tree.iter() if n.get('id')=='photo').set('href',os.path.relpath(self.root/'renamed.png',path.parent))
            return ET.tostring(tree,encoding='unicode')
        result,_=self.checkout_save(edit)
        self.assertTrue(result['changes']['no_change'])

    def test_same_filename_new_bytes_reports_image_change(self):
        self.image_candidate()
        Image.new('RGB',(20,40),'blue').save(self.root/'portrait.png')
        def edit(text,path):
            import os
            import xml.etree.ElementTree as ET
            tree=ET.fromstring(text)
            next(n for n in tree.iter() if n.get('id')=='photo').set('href',os.path.relpath(self.root/'portrait.png',path.parent))
            return ET.tostring(tree,encoding='unicode')
        result,_=self.checkout_save(edit)
        self.assertEqual(result['changes']['image_elements'], ['photo'])
        self.assertFalse(result['changes']['no_change'])

    def test_notes_only_is_not_no_change_or_svg_change(self):
        result,_=self.checkout_save(notes='Updated notes')
        self.assertTrue(result['changes']['notes_changed'])
        self.assertFalse(result['changes']['svg_changed'])
        self.assertFalse(result['changes']['no_change'])

    def test_element_counts_and_text_changes(self):
        result,_=self.checkout_save(lambda s,_: s.replace('Original','Revised').replace('</svg>','<circle id="new" r="4"/></svg>'))
        self.assertIn('new', result['changes']['elements']['added'])
        self.assertEqual(result['changes']['text_elements'], ['title'])
        self.assertIn('title',result['changes']['elements']['modified'])


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.svg=self.root/'page.svg'
        Image.new('RGB',(100,200),'red').save(self.root/'portrait.png')
    def tearDown(self): self.tmp.cleanup()
    def write_svg(self,body):
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>')
    def test_crop_and_fill_share_same_measurement(self):
        for fit,code in [('slice','IMAGE_CROP_RISK'),('meet','IMAGE_LOW_FILL')]:
            self.write_svg(f'<image id="hero" href="portrait.png" width="500" height="200" preserveAspectRatio="xMidYMid {fit}"/>')
            row=image_frames(self.svg)[0]
            self.assertEqual(row['aspect_mismatch'],5)
            self.assertEqual(row['issues'][0]['code'],code)
            self.assertEqual(row['source_visible_fraction'] if fit=='slice' else row['slot_fill_fraction'],.2)
    def test_data_uri_and_defs(self):
        data=base64.b64encode((self.root/'portrait.png').read_bytes()).decode()
        self.write_svg(f'<defs><image href="missing"/></defs><image href="data:image/png;base64,{data}" width="100" height="200"/>')
        rows=image_frames(self.svg)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'measured')
        self.assertEqual(rows[0]['issues'],[])
    def test_unknown_units_and_broken_images_are_explicit(self):
        self.write_svg('<image href="portrait.png" width="100%" height="200"/><image href="missing.png" width="5" height="5"/>')
        self.assertTrue(all(r['status']=='unmeasured' and r['issues'] for r in image_frames(self.svg)))
    def test_nested_svg_dimensions(self):
        (self.root/'vector.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"/>')
        self.write_svg('<image href="vector.svg" width="400" height="200"/>')
        self.assertEqual(image_frames(self.svg)[0]['source'],{'width':400.,'height':200.})
    def audit(self,page,doc=None,route='slides'):
        return audit_copy(self.root,doc or {},{'page_key':'p1',**page},self.svg,route)
    def test_copy_requires_explicit_confirmed_input(self):
        self.write_svg('<text>Original</text>')
        self.assertEqual(self.audit({'content':'Original'})['status'],'unchecked')
    def test_copy_checks_initial_added_badges_but_normalizes_spans(self):
        self.write_svg('<text id="title">原<tspan>始</tspan>\n稿件</text><text id="badge">GATE 01</text><text>01</text><text>→</text>')
        result=self.audit({'copy_confirmed':True,'content':'**原始稿件**'})
        self.assertEqual(result['status'],'warning')
        self.assertEqual([x['text'] for x in result['suspect_text']],['GATE 01'])
        self.assertEqual(len(result['structural_text']),2)
    def test_literal_underscores_survive_markdown_normalization(self):
        self.write_svg('<text>user_id</text>')
        self.assertEqual(self.audit({'copy_confirmed':True,'content':'`user_id`'})['status'],'matched')

    def test_video_scene_title_and_notes_do_not_authorize_copy(self):
        self.write_svg('<text>Internal scene</text><text>Speaker notes</text>')
        result=self.audit({'copy_confirmed':True,'title':'Internal scene','content':'Screen text','notes':'Speaker notes'},route='video')
        self.assertEqual(len(result['suspect_text']),2)
    def test_empty_confirmed_copy_flags_any_prose(self):
        self.write_svg('<text>Unexpected</text>')
        self.assertEqual(self.audit({'copy_confirmed':True,'content':''})['status'],'warning')
    def test_source_changes_invalidate_copy_binding(self):
        self.write_svg('<text>Original</text>')
        (self.root/'source.md').write_text('changed')
        result=self.audit({'copy_confirmed':True,'content':'Original'},{'source_path':'source.md','source_sha256':'stale'})
        self.assertEqual(result['status'],'unchecked')
    def test_existing_visual_plan_binding_is_reused(self):
        self.write_svg('<text>Screen text</text>')
        directory=self.root/'_internal/00_project'
        directory.mkdir(parents=True)
        (directory/'page_manifest.json').write_text(json.dumps({'visual_plan':{'path':'missing-plan.json','sha256':'bound'}}))
        self.assertEqual(self.audit({'copy_confirmed':True,'content':'Screen text'},route='video')['status'],'unchecked')

    def test_authorized_content_update_clears_suspect(self):
        self.write_svg('<text>Authorized</text>')
        self.assertEqual(self.audit({'copy_confirmed':True,'content':'Authorized'})['status'],'matched')


class PipelineDiagnosticsTests(unittest.TestCase):
    setUp=pipeline_fixtures.WorkbenchPipelineTests.setUp
    tearDown=pipeline_fixtures.WorkbenchPipelineTests.tearDown
    fake_render=pipeline_fixtures.WorkbenchPipelineTests.fake_render
    def test_summary_retains_cached_failure_and_codes(self):
        result=pipeline.check_summary({'route':'slides','pages':[{'page':'p1','status':'unchanged','validation_status':'fix',
            'render_token':'t','png':'p.png','issues':{'reports':[{'issues':[{'code':'BAD','severity':'error'}]}]},
            'copy_audit':{'status':'unchecked'}}]})
        row=result['pages'][0]
        self.assertEqual(row['status'],'fix')
        self.assertTrue(row['cached'])
        self.assertEqual(row['issue_codes'],['BAD','COPY_UNCHECKED'])
        self.assertEqual(row['png'],'p.png')
    def test_summary_compacts_blocked_tracebacks(self):
        error='Traceback (most recent call last):\n  File renderer.py\nRuntimeError: browser unavailable\n'+'log '*300
        result=pipeline.check_summary({'route':'slides','pages':[{'page':'alpha','status':'blocked','error':error}]})
        self.assertEqual(result['pages'][0]['error'],'RuntimeError: browser unavailable')

    def test_validator_reports_fit_as_warning_and_frames_uses_same_ids(self):
        Image.new('RGB',(100,200),'red').save(self.root/'portrait.png')
        checked=store.commit(self.root,{'op':'checkout','operation_id':'image_checkout','page_key':'alpha'})
        candidate=Path(checked['candidate'])
        import os
        href=os.path.relpath(self.root/'portrait.png',candidate.parent)
        candidate.write_text(candidate.read_text().replace('</svg>',f'<image id="hero" href="{href}" x="120" y="300" width="500" height="200" preserveAspectRatio="xMidYMid slice"/></svg>'))
        saved=store.commit(self.root,{'op':'save','operation_id':'image_save','page_key':'alpha','candidate':str(candidate),'base_revision':checked['base_revision']})
        self.assertTrue(saved['ok'],saved)
        with patch.object(pipeline,'run',side_effect=self.fake_render):
            result=pipeline.check(self.root,['alpha'])
        summary=pipeline.check_summary(result)['pages'][0]
        self.assertEqual(summary['status'],'pass')
        self.assertIn('IMAGE_CROP_RISK',summary['issue_codes'])
        row=pipeline.frames(self.root,['alpha'])['pages'][0]['images'][0]
        self.assertEqual(row['element_id'],'hero')
        self.assertEqual(row['source_visible_fraction'],.2)

    def test_geometry_change_rechecks_same_page_but_export_only_change_does_not(self):
        import shutil
        scripts = self.root / 'checker-copy'
        shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns('__pycache__', 'test'))
        with patch.object(pipeline, 'SCRIPTS', scripts), patch.object(pipeline, 'run', side_effect=self.fake_render):
            def check_page():
                return pipeline.check(self.root, ['alpha'])['pages'][0]

            self.assertEqual(check_page()['status'], 'pass')
            with (scripts / 'native_svg_to_ppt.py').open('a') as f:
                f.write('\n# Export-only change\n')
            self.assertEqual(check_page()['status'], 'unchanged')
            geometry = scripts / 'lib/svg_geometry.py'
            with geometry.open('a') as f:
                f.write('\ndef compose_axis_aligned(parent, local):\n    return (100000, 100000, 1, 1)\n')
            result = check_page()
            self.assertEqual(result['status'], 'fix', result)
            self.assertTrue(result['issues']['summary']['errors'])

    def test_batch_and_cached_results_include_copy_audit(self):
        document=ps.read(self.root/ps.CONTENT)
        document['pages'][0]['copy_confirmed']=True
        ps.write(self.root/ps.CONTENT,document)
        with patch.object(pipeline,'run',side_effect=self.fake_render):
            first=pipeline.check(self.root,['alpha','omega'])
            second=pipeline.check(self.root,['alpha','omega'])
        self.assertEqual(len(first['pages']),2)
        self.assertEqual([p['status'] for p in second['pages']],['unchanged','unchanged'])
        self.assertEqual(second['pages'][0]['copy_audit']['status'],'matched')
        self.assertEqual(second['pages'][1]['copy_audit']['status'],'unchecked')
        self.assertTrue(all('png' in p for p in second['pages']))
    def test_real_validator_failure_is_rechecked_and_stays_failed(self):
        checked=store.commit(self.root,{'op':'checkout','operation_id':'bad_checkout','page_key':'alpha'})
        path=Path(checked['candidate'])
        path.write_text(path.read_text().replace('font-size="48"','font-size="2"'))
        saved=store.commit(self.root,{'op':'save','operation_id':'bad_save','page_key':'alpha','candidate':str(path),'base_revision':checked['base_revision']})
        self.assertTrue(saved['ok'],saved)
        with patch.object(pipeline,'run',side_effect=self.fake_render):
            first=pipeline.check(self.root,['alpha'])
            second=pipeline.check(self.root,['alpha'])
        self.assertEqual(first['pages'][0]['status'],'fix')
        self.assertEqual(second['pages'][0]['status'],'fix')
        self.assertEqual(pipeline.check_summary(second)['pages'][0]['status'],'fix')

    def test_comma_error_provides_valid_batch_syntax(self):
        with self.assertRaisesRegex(ValueError,'space-separated'):
            pipeline.check(self.root,['alpha,omega'])
    def test_cli_cached_failure_exits_nonzero_even_in_summary(self):
        with patch.object(pipeline,'check',return_value={'route':'slides','pages':[{'page':'alpha','status':'unchanged','validation_status':'fix'}]}), \
             patch.object(sys,'argv',['ppt_pipeline.py',str(self.root),'check','--summary']), patch('builtins.print'):
            with self.assertRaises(SystemExit) as caught:
                pipeline.main()
        self.assertEqual(caught.exception.code,1)

if __name__=='__main__': unittest.main()
