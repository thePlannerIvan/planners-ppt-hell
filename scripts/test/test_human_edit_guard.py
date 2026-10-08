"""User edits survive model saves; no legacy hash acknowledgement can waive protection."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_workbench_pipeline as fixtures
import workbench_store as store

class HumanEditGuardTests(unittest.TestCase):
    setUp=fixtures.WorkbenchPipelineTests.setUp
    tearDown=fixtures.WorkbenchPipelineTests.tearDown
    command=fixtures.WorkbenchPipelineTests.command
    save=fixtures.WorkbenchPipelineTests.save

    def title_identity(self):
        tree=ET.fromstring(store.get_page(self.root,'alpha')['svg'])
        return next(node.get(store.ID_ATTR) for node in tree.iter() if node.tag.endswith('text'))

    def human(self,edits=None,notes=None):
        current=store.get_page(self.root,'alpha')
        cmd=self.command(op='save',page_key='alpha',base_revision=current['revision'])
        if edits is not None: cmd['edits']=edits
        if notes is not None: cmd['notes']=notes
        result=store.commit(self.root,cmd,browser=True)
        self.assertTrue(result['ok'],result)
        return result

    def candidate(self,replace=None,task_id=None):
        checked=store.commit(self.root,self.command(op='checkout',page_key='alpha'))
        path=Path(checked['candidate'])
        if replace: path.write_text(replace(path.read_text()),encoding='utf-8')
        command=self.command(op='save',author='model',page_key='alpha',candidate=str(path),
                             base_revision=checked['base_revision'])
        if task_id: command['task_id']=task_id
        return store.commit(self.root,command)

    def test_human_text_is_saved_and_protected_with_revision(self):
        identity=self.title_identity()
        result=self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        current=store.get_page(self.root,'alpha')
        self.assertEqual(current['revision'],result['revision'])
        self.assertIn('Human title',current['svg'])
        self.assertEqual(current['protected'][identity]['text'],'Human title')
        self.assertTrue(Path(current['svg_path']).is_file())

    def test_latest_baseline_still_rejects_dropped_human_text(self):
        identity=self.title_identity()
        self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        current=store.get_page(self.root,'alpha')['revision']
        result=self.candidate(lambda text:text.replace('Human title','Model title'))
        self.assertFalse(result['ok']);self.assertEqual(result['code'],'human_edits_lost')
        self.assertEqual(store.get_page(self.root,'alpha')['revision'],current)
        self.assertTrue(Path(result['recovery']).is_file())

    def test_preserved_human_text_accepts_candidate_and_other_page_unaffected(self):
        identity=self.title_identity();other=store.get_page(self.root,'omega')['revision']
        self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        result=self.candidate()
        self.assertTrue(result['ok'],result)
        self.assertIn('Human title',store.get_page(self.root,'alpha')['svg'])
        self.assertEqual(store.get_page(self.root,'omega')['revision'],other)

    def test_human_position_attributes_cannot_be_dropped(self):
        identity=self.title_identity()
        self.human([{'kind':'attributes','element_id':identity,'attributes':{'x':'180','font-size':'52'}}])
        result=self.candidate(lambda text:text.replace('x="180"','x="120"'))
        self.assertEqual(result['code'],'human_edits_lost')

    def test_human_deleted_element_cannot_be_reintroduced(self):
        checked=store.commit(self.root,self.command(op='checkout',page_key='alpha'))
        old=Path(checked['candidate']).read_text()
        identity=self.title_identity()
        self.human([{'kind':'delete','element_id':identity}])
        result=self.candidate(lambda _text:old)
        self.assertEqual(result['code'],'human_edits_lost')

    def test_browser_explicit_rewrite_scope_allows_only_the_target(self):
        identity=self.title_identity()
        self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        revision=store.get_page(self.root,'alpha')['revision']
        task=store.commit(self.root,self.command(op='feedback',scope='page',
                pages={'alpha':{'revision':revision,'feedback':'Rewrite title','rewrite_elements':[identity]}}),browser=True)
        result=self.candidate(lambda text:text.replace('Human title','Requested title'),task_id=task['task_id'])
        self.assertTrue(result['ok'],result)
        self.assertIn('Requested title',store.get_page(self.root,'alpha')['svg'])

    def test_model_cannot_forge_browser_rewrite_authorization(self):
        identity=self.title_identity()
        self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        result=store.commit(self.root,self.command(op='feedback',scope='page',pages={'alpha':{
            'revision':store.get_page(self.root,'alpha')['revision'],'rewrite_elements':[identity]}}))
        self.assertFalse(result['ok']);self.assertEqual(result['code'],'human_action_required')

    def test_notes_save_does_not_falsely_drop_svg_edits(self):
        identity=self.title_identity()
        self.human([{'kind':'text','element_id':identity,'value':'Human title'}])
        self.human(notes='Updated speaker notes')
        result=self.candidate()
        self.assertTrue(result['ok'],result)
        self.assertEqual(store.get_page(self.root,'alpha')['notes'],'Updated speaker notes')

if __name__=='__main__':unittest.main()
