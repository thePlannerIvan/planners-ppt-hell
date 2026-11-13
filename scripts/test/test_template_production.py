"""模板生产链：目录 → 脚手架 → 版式选择 → 收窄 → 最终审阅。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / 'template'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_layout_selection import apply_selection  # noqa: E402
from generate_template_review_html import generate_pack_review  # noqa: E402
from generate_template_select_html import generate as generate_select  # noqa: E402
from layout_catalog import catalog_from_pptx, write_catalog  # noqa: E402
from review_surface import surface_document  # noqa: E402
from scaffold_template_pack import scaffold  # noqa: E402
from template_library import build_manifest, validate_pack_dir  # noqa: E402
from test_scaffold_template_pack import make_deck, make_facts, make_visuals  # noqa: E402


def html_data(path):
    text = Path(path).read_text()
    return json.loads(text.split('const data=', 1)[1].split(';\nlet pageOrder', 1)[0])


class TemplateProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.pack = self.root / '_internal' / '00_project' / 'template_pack'
        self.pack.mkdir(parents=True)
        self.source = Path(self.temp.name) / 'deck.pptx'
        make_deck(self.source)
        self.visuals = self.root / '_internal' / '00_project' / 'template_visuals'
        make_visuals(self.visuals)
        write_catalog(self.root, catalog_from_pptx(self.source))
        (self.pack / 'extraction_facts.json').write_text(
            json.dumps(make_facts(self.source, self.visuals), ensure_ascii=False), encoding='utf-8')
        scaffold(self.root)
        document = json.loads((self.pack / 'layouts.json').read_text())
        (self.pack / 'primitives').mkdir(exist_ok=True)
        for layout in document['layouts']:
            (self.pack / layout['primitive']).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
                '<rect width="1920" height="1080" fill="var(--canvas-bg)"/></svg>', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_select_page_lists_used_families_and_slot_svgs(self):
        out = generate_select(self.root)
        data = html_data(out)
        self.assertEqual(data['route'], 'template-select')
        self.assertEqual(len(data['pages']), len(json.loads((self.pack / 'layouts.json').read_text())['layouts']))
        self.assertTrue(all(page['selected'] for page in data['pages']))
        self.assertIn('<rect', data['pages'][0]['svgMarkup'])
        face = surface_document(self.root, 'select')
        self.assertEqual(face['id'], 'planners-ppt-hell/template-select')
        self.assertEqual(face['entry'], '00_template_select.html')
        self.assertEqual(face['feedback'], 'layout_selection.json')

    def test_apply_selection_filters_layouts_and_snapshot_tracks_it(self):
        generate_select(self.root)
        snapshot = json.loads((self.root / '_internal' / '00_project' / 'template_select_snapshot.json').read_text())
        families = snapshot['families']
        chosen = families[1:]
        selection = {
            'review_id': snapshot['review_id'],
            'selected': chosen,
            'families': {key: {'selected': key in chosen} for key in families},
            'submitted_at': '2026-01-01T00:00:00Z',
        }
        (self.root / '_internal' / '00_project' / 'layout_selection.json').write_text(json.dumps(selection))
        before = json.loads((self.pack / 'layouts.json').read_text())
        dropped = [item for item in before['layouts'] if item['layout_id'] not in chosen]
        result = apply_selection(self.root)
        self.assertEqual(result['layouts'], len(chosen))
        document = json.loads((self.pack / 'layouts.json').read_text())
        self.assertEqual([item['layout_id'] for item in document['layouts']], chosen)
        self.assertEqual(document['selection']['review_id'], snapshot['review_id'])
        for item in dropped:
            if item.get('preview'):
                self.assertFalse((self.pack / item['preview']).exists(), item['preview'])
        out = generate_pack_review(self.root)
        data = html_data(out)
        self.assertEqual(data['route'], 'template')
        self.assertEqual([page['key'] for page in data['pages']], chosen)
        self.assertEqual(data['pages'][0]['title'], document['layouts'][0]['name'])
        reviewed = json.loads((self.root / '_internal' / '00_project' / 'template_review_snapshot.json').read_text())
        self.assertEqual(reviewed['layouts'], chosen)
        self.assertEqual(reviewed['package_format'], 'four_piece_layouts')

    def test_stale_selection_is_refused_and_missing_primitive_blocks_review(self):
        generate_select(self.root)
        snapshot = json.loads((self.root / '_internal' / '00_project' / 'template_select_snapshot.json').read_text())
        (self.root / '_internal' / '00_project' / 'layout_selection.json').write_text(json.dumps({
            'review_id': 'stale',
            'selected': snapshot['families'],
            'families': {key: {'selected': True} for key in snapshot['families']},
        }))
        with self.assertRaisesRegex(ValueError, 'stale'):
            apply_selection(self.root)
        document = json.loads((self.pack / 'layouts.json').read_text())
        (self.pack / document['layouts'][0]['primitive']).unlink()
        with self.assertRaisesRegex(ValueError, 'authored primitive'):
            generate_pack_review(self.root)

    def test_manifest_records_layouts_and_strict_validation_passes(self):
        manifest = build_manifest(self.pack, template_id='fixture-pack', name='Fixture Pack')
        self.assertIn('layouts_json', manifest['four_piece_contract'])
        self.assertGreater(manifest['four_piece_contract']['layout_count'], 0)
        self.assertTrue(validate_pack_dir(self.pack, check_manifest_hashes=True, strict=True)['valid'])


if __name__ == '__main__':
    unittest.main()
