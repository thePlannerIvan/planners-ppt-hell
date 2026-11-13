"""模板脚手架：从原生目录生成 tokens/SPEC/shell/layouts，并接上严格校验。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / 'template'))
from layout_catalog import catalog_from_pptx, write_catalog  # noqa: E402
from layout_index import pack_layouts  # noqa: E402
from scaffold_template_pack import scaffold  # noqa: E402
from template_library import validate_pack_dir  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402


def make_deck(path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    for index in (0, 1, 3, 5, 6):
        slide = prs.slides.add_slide(prs.slide_layouts[index])
        if slide.shapes.title is not None:
            slide.shapes.title.text = f'Title {index}'
        for placeholder in slide.placeholders:
            if placeholder.placeholder_format.idx == 0 or not placeholder.has_text_frame:
                continue
            placeholder.text = 'Body copy'
    prs.save(str(path))


def make_visuals(root, count=5):
    root.mkdir(parents=True, exist_ok=True)
    for index in range(1, count + 1):
        Image.new('RGB', (1920, 1080), 'white').save(root / f'page_{index:03d}.png')


def make_facts(source, visuals):
    return {
        'source_file': str(source),
        'visuals_dir': str(visuals),
        'rendered_page_count': 5,
        'visual_palette_sampling': {
            'dominant_light_surfaces': [
                {'hex': '#FFFFFF', 'pixel_weight': 100},
                {'hex': '#F4F7FA', 'pixel_weight': 10},
            ],
            'dominant_dark_ink_or_surfaces': [{'hex': '#111111', 'pixel_weight': 50}],
            'dominant_saturated_accents': [{'hex': '#0052D9', 'pixel_weight': 40}],
        },
        'pptx_structural_facts': {
            'visible_color_stats': {
                'text_colors': [
                    {'hex': '#111111', 'weight': 100},
                    {'hex': '#555555', 'weight': 50},
                ],
                'accents_bars_and_badges': [{'hex': '#0052D9', 'weight': 10}],
                'stroke_and_line_colors': [{'hex': '#DDDDDD', 'weight': 5}],
            },
            'visible_typography_stats': {
                'font_families_by_char_count': [{'font_family': 'Arial', 'char_count': 100}],
                'font_size_tiers_1080p': [
                    {'px_1080p': 72, 'char_count': 10, 'slide_count': 1},
                    {'px_1080p': 24, 'char_count': 100, 'slide_count': 3},
                ],
            },
        },
    }


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.pack = self.root / '_internal' / '00_project' / 'template_pack'
        self.pack.mkdir(parents=True)
        self.source = Path(self.temp.name) / 'deck.pptx'
        make_deck(self.source)
        self.visuals = self.root / '_internal' / '00_project' / 'template_visuals'
        make_visuals(self.visuals)
        self.catalog = catalog_from_pptx(self.source)
        write_catalog(self.root, self.catalog)
        (self.pack / 'extraction_facts.json').write_text(
            json.dumps(make_facts(self.source, self.visuals), ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def run_scaffold(self, **kwargs):
        return scaffold(self.root, **kwargs)

    def test_scaffold_writes_valid_tokens_spec_shell_and_layouts(self):
        result = self.run_scaffold()
        self.assertTrue(result['ok'])
        self.assertGreaterEqual(result['layouts'], 5)
        for name in ('tokens.css', 'SPEC.md', 'skyline_shell.svg', 'layouts.json'):
            self.assertTrue((self.pack / name).is_file(), name)
        tokens = (self.pack / 'tokens.css').read_text()
        self.assertIn('--accent-1: #0052D9;', tokens)
        self.assertIn('--font-sans: "Arial"', tokens)
        self.assertNotRegex(tokens, r'\d+\s*-\s*\d+')
        spec = (self.pack / 'SPEC.md').read_text()
        self.assertIn('安全边距', spec)
        self.assertIn('单栏', spec)
        document = json.loads((self.pack / 'layouts.json').read_text())
        self.assertEqual(document['schema'], 'planner.template-layouts.v1')
        self.assertGreaterEqual(len(document['layouts']), 5)
        for layout in document['layouts']:
            self.assertTrue(layout['preview'])
            self.assertTrue((self.pack / layout['preview']).is_file())
            self.assertTrue((self.pack / layout['anchor']).is_file())
            self.assertTrue(layout['primitive'].startswith('primitives/'))
        indexed = pack_layouts(self.pack)
        self.assertEqual(len(indexed), len(document['layouts']))
        self.assertTrue(all(item['preview'] for item in indexed))
        self.assertTrue(all(item['primitive'] == '' for item in indexed))

    def test_scaffold_filters_families_and_does_not_overwrite_by_default(self):
        self.run_scaffold(families=['cover'])
        document = json.loads((self.pack / 'layouts.json').read_text())
        self.assertEqual([item['layout_id'] for item in document['layouts']], ['cover'])
        tokens_before = (self.pack / 'tokens.css').read_text()
        (self.pack / 'tokens.css').write_text(tokens_before + '\n/* edited */\n', encoding='utf-8')
        self.run_scaffold(families=['cover'])
        self.assertIn('/* edited */', (self.pack / 'tokens.css').read_text())
        self.run_scaffold(families=['cover'], force=True)
        self.assertNotIn('/* edited */', (self.pack / 'tokens.css').read_text())

    def test_authoring_primitives_then_strict_pack_validation(self):
        self.run_scaffold()
        document = json.loads((self.pack / 'layouts.json').read_text())
        (self.pack / 'primitives').mkdir(exist_ok=True)
        for layout in document['layouts']:
            (self.pack / layout['primitive']).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
                '<rect width="1920" height="1080" fill="var(--canvas-bg)"/></svg>', encoding='utf-8')
        self.assertTrue(validate_pack_dir(self.pack, strict=True)['valid'])

        tokens = (self.pack / 'tokens.css').read_text()
        (self.pack / 'tokens.css').write_text(tokens.replace('--size-body: 24px;', '--size-body: 20px - 24px;'))
        result = validate_pack_dir(self.pack, strict=True)
        self.assertFalse(result['valid'])
        self.assertTrue(any('range' in issue for issue in result['issues']))
        self.assertTrue(validate_pack_dir(self.pack, strict=False)['valid'])

    def test_strict_validation_catches_missing_primitive_and_undefined_token(self):
        self.run_scaffold()
        document = json.loads((self.pack / 'layouts.json').read_text())
        (self.pack / 'primitives').mkdir(exist_ok=True)
        first = document['layouts'][0]
        (self.pack / first['primitive']).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">'
            '<rect width="1920" height="1080" fill="var(--missing-token)"/></svg>', encoding='utf-8')
        result = validate_pack_dir(self.pack, strict=True)
        self.assertFalse(result['valid'])
        self.assertTrue(any('undefined tokens' in issue for issue in result['issues']))
        self.assertTrue(any('missing primitive' in issue for issue in result['issues']))


if __name__ == '__main__':
    unittest.main()
