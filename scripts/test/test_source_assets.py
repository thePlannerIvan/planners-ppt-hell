#!/usr/bin/env python3
"""Regression tests for Markdown/DOCX image intake and handoff."""

import json
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
import sys

# 这条测试以前写 `from scripts.prepare_source_material import ...`，隐含要求 CWD = Skill 根。
# 现在自己把 Skill 根放进 sys.path，从任何目录跑都成立。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.prepare_source_material import prepare_source_material  # noqa: E402


def png_bytes(width=40, height=20):
    raw = b"".join(b"\x00" + b"\x33\x77\xaa" * width for _ in range(height))

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class SourceAssetTests(unittest.TestCase):
    def test_bypage_handoff_keeps_content_and_assets_without_proposal(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'slides'
            root.mkdir()
            package = Path(raw) / 'deliverable'
            assets = package / 'assets' / 'original'
            assets.mkdir(parents=True)
            image = png_bytes()
            (assets / 'evidence.png').write_bytes(image)
            source = package / 'by-page.md'
            source.write_text(
                '---\npage_number: 1\npage_title: "Evidence"\n---\n\n'
                '## Page Content\n\nObserved result: 42% in the pilot sample.\n\n'
                '![Evidence](assets/original/evidence.png)\n\n'
                '## Speaker Notes\n\nThe pilot does not establish causality.\n\n'
                '## Production Notes\n\nUse the original evidence image.\n\n'
                '## Sources\n\n- study.md, Results\n', encoding='utf-8')
            manifest = prepare_source_material(root, source)
            normalized = (root / manifest['normalized_source']).read_text(encoding='utf-8')
            self.assertIn('42% in the pilot sample', normalized)
            self.assertIn('The pilot does not establish causality', normalized)
            self.assertIn('study.md, Results', normalized)
            self.assertIn('![Evidence](assets/asset_001.png)', normalized)
            self.assertEqual((root / manifest['assets'][0]['normalized_path']).read_bytes(), image)
            self.assertFalse((Path(raw) / '.proposal-work').exists())

    def test_markdown_images_are_copied_and_rewritten(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "project"
            root.mkdir()
            source_dir = Path(raw) / "source"
            source_dir.mkdir()
            (source_dir / "hero.png").write_bytes(png_bytes())
            source = source_dir / "brief.md"
            source.write_text("# Brief\n\n![产品主图](hero.png)\n", encoding="utf-8")
            manifest = prepare_source_material(root, source)
            self.assertTrue(manifest["has_images"])
            self.assertEqual(manifest["image_count"], 1)
            asset = manifest["assets"][0]
            self.assertEqual(asset["width_px"], 40)
            self.assertEqual(asset["height_px"], 20)
            self.assertTrue((root / asset["normalized_path"]).is_file())
            normalized = (root / manifest["normalized_source"]).read_text(encoding="utf-8")
            self.assertIn("![产品主图](assets/asset_001.png)", normalized)

    def test_docx_embedded_image_is_extracted_in_reading_order(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "project"
            root.mkdir()
            source = Path(raw) / "brief.docx"
            document = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
              xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
              <w:body><w:p><w:r><w:t>产品证据</w:t></w:r><w:r><w:drawing><wp:inline>
              <wp:docPr id="1" name="产品图" descr="真实产品图"/><a:graphic><a:graphicData>
              <a:blip r:embed="rId5"/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p></w:body>
              </w:document>"""
            rels = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId5" Target="media/image1.png" Type="image"/></Relationships>"""
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", document)
                archive.writestr("word/_rels/document.xml.rels", rels)
                archive.writestr("word/media/image1.png", png_bytes())
            manifest = prepare_source_material(root, source)
            self.assertEqual(manifest["source_type"], "docx")
            self.assertEqual(manifest["image_count"], 1)
            normalized = (root / manifest["normalized_source"]).read_text(encoding="utf-8")
            self.assertIn("产品证据", normalized)
            self.assertIn("![真实产品图](assets/asset_001.png)", normalized)

    @unittest.skipUnless(shutil.which("pandoc") and shutil.which("soffice"), "pandoc and soffice are required")
    def test_legacy_doc_is_converted_and_keeps_embedded_image(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            root = temp / "project"
            root.mkdir()
            image = temp / "hero.png"
            image.write_bytes(png_bytes())
            markdown = temp / "brief.md"
            markdown.write_text("# 旧版 Word\n\n![产品图](hero.png)\n", encoding="utf-8")
            docx = temp / "brief.docx"
            subprocess.run([shutil.which("pandoc"), str(markdown), "-o", str(docx)], check=True, cwd=temp)
            subprocess.run(
                [shutil.which("soffice"), "--headless", "--convert-to", "doc", "--outdir", str(temp), str(docx)],
                check=True,
                capture_output=True,
            )
            legacy = temp / "brief.doc"
            self.assertTrue(legacy.is_file())
            manifest = prepare_source_material(root, legacy)
            self.assertEqual(manifest["source_type"], "doc")
            self.assertGreaterEqual(manifest["image_count"], 1)


if __name__ == "__main__":
    unittest.main()
