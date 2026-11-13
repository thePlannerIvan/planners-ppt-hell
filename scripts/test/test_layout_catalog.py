"""PPTX layout catalog：原生版式、占位符几何、页映射与家族归并。"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / 'template'))
from layout_catalog import catalog_from_pdf, catalog_from_pptx, family_of, placeholder_role  # noqa: E402

from PIL import Image  # noqa: E402

try:
    import fitz  # noqa: E402
except ImportError:  # pragma: no cover
    fitz = None

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

    @unittest.skipUnless(fitz is not None, 'PyMuPDF is required for PDF catalog')
    def test_pdf_catalog_reads_text_image_blocks_and_families(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            image = temp / 'image.png'
            Image.new('RGB', (480, 270), 'blue').save(image)
            source = temp / 'deck.pdf'
            doc = fitz.open()
            page = doc.new_page(width=960, height=540)
            page.insert_text((80, 120), 'COVER TITLE', fontsize=40)
            page.insert_text((80, 190), 'A subtitle', fontsize=16)
            page = doc.new_page(width=960, height=540)
            page.insert_text((80, 100), 'Section headline', fontsize=24)
            page.insert_text((80, 180), 'A paragraph of body text.', fontsize=11)
            page = doc.new_page(width=960, height=540)
            page.insert_image(fitz.Rect(0, 0, 960, 540), filename=str(image))
            doc.save(str(source))
            doc.close()
            catalog = catalog_from_pdf(source)
        self.assertEqual(catalog['source_kind'], 'pdf')
        self.assertEqual(catalog['slide_count'], 3)
        self.assertGreaterEqual(len(catalog['families']), 3)
        families = {item['family']: item for item in catalog['families']}
        self.assertIn('cover', families)
        self.assertIn('full_bleed', families)
        self.assertEqual([slot['role'] for slot in families['cover']['slots']], ['title', 'subtitle'])
        self.assertEqual([slot['role'] for slot in families['full_bleed']['slots']], ['image'])
        self.assertEqual(catalog['pages'][1]['title'], 'Section headline')

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
