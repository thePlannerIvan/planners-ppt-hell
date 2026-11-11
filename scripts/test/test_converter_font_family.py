#!/usr/bin/env python3
"""font-family 的通用族不能写进 PPT 的 typeface。

回归的是 2026-11-11 的交付事故：页面用 `system-ui, -apple-system, 'PingFang SC', sans-serif`，
转换器取第一位当字体名写进 PPTX，LibreOffice/PowerPoint 只能自己找替身，
导出 PDF 后整页汉字字形走样，却没有任何一步报错。
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation

SCRIPT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT))

import native_svg_to_ppt as converter  # noqa: E402


def minimal_svg(font_family, text='客户需求'):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
  <rect x="0" y="0" width="1920" height="1080" fill="#0C0D11"/>
  <text x="120" y="240" font-size="64" font-weight="700" fill="#FFFFFF"
        font-family="{font_family}" data-workbench-id="wb_font_probe">{text}</text>
</svg>'''


class FontFamilyTest(unittest.TestCase):
    def setUp(self):
        converter._conversion_errors = []
        converter._conversion_warnings = []

    def test_generic_family_is_rejected_with_element_name(self):
        run = Presentation().slides.add_slide(Presentation().slide_layouts[6]).shapes.add_textbox(0, 0, 100, 100).text_frame.paragraphs[0].add_run()
        converter._set_run_font_family(run, "'system-ui', 'PingFang SC', sans-serif", '（元素 wb_x）')
        self.assertEqual(run.font.name, None, '通用族不能被写成 typeface')
        self.assertEqual(len(converter._conversion_errors), 1)
        message = converter._conversion_errors[0]
        self.assertIn("system-ui", message)
        self.assertIn('wb_x', message, '报错要能定位到元素')

    def test_explicit_family_still_applies(self):
        prs = Presentation()
        run = prs.slides.add_slide(prs.slide_layouts[6]).shapes.add_textbox(0, 0, 100, 100).text_frame.paragraphs[0].add_run()
        converter._set_run_font_family(run, "'Hiragino Sans GB', 'PingFang SC', sans-serif")
        self.assertEqual(run.font.name, 'Hiragino Sans GB')
        self.assertEqual(converter._conversion_errors, [])

    def test_export_fails_instead_of_writing_a_fake_typeface(self):
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / 'p1.svg'
            svg.write_text(minimal_svg('system-ui, -apple-system'), encoding='utf-8')
            out = Path(tmp) / 'out.pptx'
            completed = subprocess.run(
                [sys.executable, str(SCRIPT / 'native_svg_to_ppt.py'), str(svg), '-o', str(out)],
                capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn('CSS 通用族', completed.stderr)
            self.assertFalse(out.exists(), '判失败就不该留下一个字体不可用的 PPTX')


if __name__ == '__main__':
    unittest.main()
