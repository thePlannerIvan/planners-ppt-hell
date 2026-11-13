"""模板版式索引：v2 四件套与 legacy fidelity 都读成同一个「可选版式」形状。"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from template import layout_index  # noqa: E402

LIBRARY = SCRIPTS.parent / 'assets' / 'template_library'


class LayoutIndexTests(unittest.TestCase):
    def test_four_piece_layouts_come_from_primitives_and_named_previews(self):
        pack = LIBRARY / 'agency-social-proposal'
        layouts = layout_index.pack_layouts(pack)
        self.assertEqual(len(layouts), 6)
        first = layouts[0]
        self.assertEqual(first['layout_id'], 'p01_cover')
        self.assertEqual(first['name'], 'Cover')
        self.assertEqual(first['preview'], 'previews/pages/p01_cover.png')
        self.assertEqual(first['primitive'], 'primitives/p01_cover.svg')
        self.assertTrue((pack / first['preview']).is_file())

    def test_dark_titanium_previews_fall_back_to_previews_root(self):
        pack = LIBRARY / 'dark-titanium-cockpit'
        layouts = layout_index.pack_layouts(pack)
        self.assertEqual(len(layouts), 52)
        self.assertEqual(layouts[0]['preview'], 'previews/p01_master_brutalist_cover.png')

    def test_name_is_readable_without_inventing_a_chinese_one(self):
        self.assertEqual(layout_index.layout_name('p02_monumental_16_9_cover'), 'Monumental 16:9 Cover')
        self.assertEqual(layout_index.layout_name('cover_dark'), 'Cover Dark')
        self.assertEqual(layout_index.layout_name('p06_chapter_divider'), 'Chapter Divider')

    def test_fidelity_layouts_come_from_the_registry_and_canvas_previews(self):
        pack = LIBRARY / 'planner-simple-default'
        self.assertEqual(layout_index.pack_format(pack), 'fidelity')
        layouts = layout_index.pack_layouts(pack)
        self.assertEqual([item['layout_id'] for item in layouts],
                         ['cover_dark', 'contents_light', 'section_dark', 'content_base', 'closing_dark'])
        first = layouts[0]
        self.assertEqual(first['preview'], 'fidelity_template/canvas_previews/pages/cover_dark.png')
        self.assertEqual(first['primitive'], 'fidelity_template/layout_canvases/cover_dark.svg')
        self.assertTrue((pack / first['preview']).is_file())

    def test_applied_fidelity_project_paths_are_root_relative(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / '_internal' / '00_project'
            shutil.copytree(LIBRARY / 'planner-simple-default', project)
            layouts = layout_index.pack_layouts(project)
            self.assertEqual(layouts[0]['primitive'], 'fidelity_template/layout_canvases/cover_dark.svg')
            self.assertTrue((project / layouts[0]['preview']).is_file())

    def test_unknown_pack_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(layout_index.pack_format(temp), '')
            self.assertEqual(layout_index.pack_layouts(temp), [])


if __name__ == '__main__':
    unittest.main()
