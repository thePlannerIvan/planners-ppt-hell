#!/usr/bin/env python3
"""发布前闸门：模板库里每个包都必须通过哈希体检。

这条测试守的是一个具体事故：`dark-titanium-cockpit` 的原语发布后被改过名，
`manifest.json` 没跟着重算，于是 `template_library.py apply` 在第一个用它的项目上硬失败，
而库里没有任何检查跑过**已发布的包**（之前的测试只校验临时 fixture）。

闸门本身只有一处实现（`template_library.verify_library`），CLI 的 `verify` 也调它。
发布流程跑 `python3 scripts/template/template_library.py verify`，等于跑这条测试。
"""

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "template"))

from template_library import LIBRARY_ROOT, verify_library  # noqa: E402


class TemplateLibraryIntegrityTest(unittest.TestCase):
    def test_failed_replacement_preserves_pack_and_provenance(self):
        import tempfile
        from unittest.mock import patch
        from template_library import apply_template

        for failure in ('copy', 'switch', 'source'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp).resolve() / '_internal/00_project'
                pack = project / 'template_pack'
                pack.mkdir(parents=True)
                (pack / 'old').write_bytes(b'original')
                metadata = project / 'template_library_source.json'
                metadata.write_bytes(b'previous metadata')
                rename = Path.rename

                def fail_switch(src, dst):
                    if src.name == 'new' and dst == pack:
                        raise OSError('switch failed')
                    return rename(src, dst)

                fault = {'copy': patch('shutil.copytree', side_effect=OSError('copy failed')),
                         'switch': patch.object(Path, 'rename', fail_switch),
                         'source': patch.object(Path, 'replace', side_effect=OSError('metadata failed'))}
                with fault[failure], self.assertRaises(OSError):
                    apply_template(tmp, 'dark-titanium-cockpit')
                self.assertEqual((pack / 'old').read_bytes(), b'original')
                self.assertEqual(metadata.read_bytes(), b'previous metadata')
                self.assertEqual(set(project.iterdir()), {pack, metadata})

    def test_every_published_pack_matches_its_manifest(self):
        result = verify_library()
        broken = [p for p in result["packs"] if not p["valid"]]
        self.assertTrue(
            result["valid"],
            "模板包与 manifest 脱同步，apply 会在第一个用它的项目上失败：\n"
            + "\n".join(f"  {p['template_id']}: {p['issues']}" for p in broken),
        )

    def test_gate_covers_the_whole_library(self):
        """包被删掉或路径写错时，闸门不能因为「没有包」而静默判过。"""
        result = verify_library()
        on_disk = {p.name for p in LIBRARY_ROOT.iterdir() if (p / "manifest.json").is_file()}
        self.assertEqual({p["template_id"] for p in result["packs"]}, on_disk)
        self.assertTrue(on_disk, "模板库为空：闸门没有对象可检查")

    def test_repaired_pack_still_applies(self):
        """哈希修好之后，文档里的 `apply` 必须真的能跑通（不只是 validate 通过）。"""
        import tempfile
        from template_library import apply_template

        with tempfile.TemporaryDirectory() as tmp:
            result = apply_template(tmp, "dark-titanium-cockpit")
            self.assertEqual(result["applied_template_id"], "dark-titanium-cockpit")
            self.assertTrue((Path(tmp) / "_internal/00_project/template_pack/manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
