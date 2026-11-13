"""PPTX layout catalog：原生版式、占位符几何、页映射与家族归并。"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / 'template'))
from layout_catalog import catalog_from_pptx, family_of, placeholder_role  # noqa: E402

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


class LayoutCatalogTests(unittest.TestCase):
    def test_default_pptx_has_layouts_slots_pages_and_families(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'deck.pptx'
            make_deck(source)
            catalog = catalog_from_pptx(source)
        self.assertEqual(catalog['schema'], 'planner.template-layout-catalog.v1')
        self.assertEqual(catalog['slide_count'], 5)
        self.assertEqual(catalog['master_count'], 1)
        self.assertGreaterEqual(len(catalog['layouts']), 9)
        self.assertGreaterEqual(len(catalog['families']), 5)
        families = {item['family'] for item in catalog['families']}
        self.assertTrue({'cover', 'one_column', 'two_columns', 'headline_only', 'blank'} <= families)
        title_layout = next(item for item in catalog['layouts'] if 'Title Slide' in item['name'])
        roles = [slot['role'] for slot in title_layout['slots']]
        self.assertIn('title', roles)
        self.assertIn('subtitle', roles)
        self.assertEqual(title_layout['usage'], 1)
        self.assertTrue(title_layout['representative_page'])
        page = catalog['pages'][0]
        self.assertEqual(page['page'], 1)
        self.assertEqual(page['family'], 'cover')
        self.assertEqual(page['title'], 'Title 0')
        body = next(item for item in catalog['families'] if item['family'] == 'one_column')
        self.assertEqual(body['label'], '单栏')
        self.assertTrue(body['slots'])

    def test_family_and_role_mapping(self):
        self.assertEqual(family_of('Title Slide'), ('cover', '封面'))
        self.assertEqual(family_of('Title and Content'), ('one_column', '单栏'))
        self.assertEqual(family_of('Two Content'), ('two_columns', '双栏'))
        self.assertEqual(family_of('Headline/Content side by side'), ('split', '左右分栏'))
        self.assertEqual(family_of('Bold headline + images and text'), ('large_image', '大图 + 文字'))
        self.assertEqual(family_of('Fullblead image'), ('full_bleed', '全幅图'))
        self.assertEqual(family_of('Unknown layout'), ('other', '其他'))
        self.assertEqual(placeholder_role('CENTER_TITLE (3)'), 'title')
        self.assertEqual(placeholder_role('PICTURE (18)'), 'image')
        self.assertEqual(placeholder_role('SLIDE_NUMBER (13)'), 'page_number')


if __name__ == '__main__':
    unittest.main()
