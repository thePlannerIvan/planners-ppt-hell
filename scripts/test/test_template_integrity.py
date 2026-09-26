#!/usr/bin/env python3
"""库里的内置模板必须自洽：声明、画出来的元素、锁层与代数都要对得上。

起因（三个静默缺陷）：`data-template-lock` 缺失时 hash 比的是空字符串；写进 canvas 的
`data-template-canvas-version` 没有任何东西读；`footer_bar` 声明成矩形而实际是一条线。
三条都是「声明与实物不一致」这一类，所以这里拿实物逐条对照声明。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "template"))
import xml.etree.ElementTree as ET  # noqa: E402

from layout_canvas import (TEMPLATE_CANVAS_VERSION, build_layout_canvas,  # noqa: E402
                           component_markup, locked_sha256, registry_canvases_ready)
from template_library import (LIBRARY_ROOT, package_hashes, package_sha256,  # noqa: E402
                              validate_component_references)
from validate_svg_layout import fidelity_component_node_errors  # noqa: E402

DEFAULT = LIBRARY_ROOT / "planner-simple-default"
FIDELITY = DEFAULT / "fidelity_template"


def registry():
    return json.loads((FIDELITY / "template_registry.json").read_text(encoding="utf-8"))


class LockedLayerTests(unittest.TestCase):
    def test_locked_layer_hash_refuses_a_file_without_one(self):
        """没有锁层就报错，不再返回空串的 hash。

        空串会让两个都没锁层的文件「hash 相同」，把「锁层丢了」降级成「一致」。
        """
        with self.assertRaisesRegex(ValueError, "no data-template-lock layer"):
            locked_sha256('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')

    def test_a_locked_file_still_hashes(self):
        canvas = FIDELITY / "layout_canvases" / "content_base.svg"
        self.assertRegex(locked_sha256(canvas), r"^[0-9a-f]{64}$")


class CanvasVersionTests(unittest.TestCase):
    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_every_canvas_declares_the_version_this_code_reads(self):
        for layout_id, layout in registry()["layouts"].items():
            canvas = FIDELITY / layout["canvas_file"]
            declared = ET.parse(canvas).getroot().attrib.get("data-template-canvas-version")
            self.assertEqual(declared, TEMPLATE_CANVAS_VERSION, layout_id)

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_registry_canvases_are_ready(self):
        self.assertTrue(registry_canvases_ready(registry(), FIDELITY))

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_a_canvas_from_another_generation_is_not_accepted(self):
        """代数不对的 canvas 不算「可以用了」。

        探针写在临时目录里：不动库里那份包，也就没有「测试中途挂掉污染库」这回事。
        """
        reg = registry()
        canvas = (FIDELITY / reg["layouts"]["content_base"]["canvas_file"]).read_text(encoding="utf-8")
        stale = canvas.replace(f'data-template-canvas-version="{TEMPLATE_CANVAS_VERSION}"',
                               'data-template-canvas-version="0"', 1)
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / "layout_canvases"
            probe.mkdir(parents=True)
            (probe / "probe_stale.svg").write_text(stale, encoding="utf-8")
            stale_registry = {"layouts": {"probe_stale": {
                "canvas_file": "layout_canvases/probe_stale.svg",
                "locked_sha256": locked_sha256(stale),
                "required_components": ["bg_light"]}}}
            self.assertFalse(registry_canvases_ready(stale_registry, Path(tmp)))
            # 同一份 canvas 换回当前代数就成立：说明否掉它的就是版本号这一项。
            fresh = stale.replace('data-template-canvas-version="0"',
                                  f'data-template-canvas-version="{TEMPLATE_CANVAS_VERSION}"', 1)
            (probe / "probe_fresh.svg").write_text(fresh, encoding="utf-8")
            fresh_registry = {"layouts": {"probe_fresh": {
                "canvas_file": "layout_canvases/probe_fresh.svg",
                "locked_sha256": locked_sha256(fresh),
                "required_components": ["bg_light"]}}}
            self.assertTrue(registry_canvases_ready(fresh_registry, Path(tmp)))


class DeclarationMatchesArtifactTests(unittest.TestCase):
    """声明与画出来的元素必须一致——`footer_bar` 那个缺陷就是这里漏掉的。"""

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_every_canvas_component_matches_its_declaration(self):
        reg = registry()
        components = {item["component_id"]: item for item in reg["components"]}
        for layout_id, layout in reg["layouts"].items():
            canvas = FIDELITY / layout["canvas_file"]
            for node in ET.parse(canvas).getroot().iter():
                component_id = node.attrib.get("data-template-component")
                if not component_id:
                    continue
                component = components[component_id]
                self.assertEqual(fidelity_component_node_errors(component, node), [],
                                 f"{layout_id}: {component_id}")

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_a_rule_is_declared_as_a_line_not_a_rectangle(self):
        """页脚是一条 1740×2 的规则线：它的角色是 footer_rule，声明就该是 line。

        声明成 rect 而实际画出一条线，是同一件事有两种说法；两边的消费者
        （canvas 生成与检查画面）会各按自己那份理解去比。
        """
        bar = next(item for item in registry()["components"] if item["component_id"] == "footer_bar")
        self.assertEqual(bar["role"], "footer_rule")
        self.assertEqual(bar["shape"]["preset"], "line")
        self.assertEqual(bar["geometry"]["height"], 0)
        markup = component_markup(bar)
        self.assertTrue(markup.startswith("<line "), markup)
        self.assertIn('fill="none"', markup)
        self.assertIn('stroke="#CBD3DC"', markup)

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_the_canvas_draws_a_line_for_the_footer_rule(self):
        canvas = (FIDELITY / "layout_canvases" / "content_base.svg").read_text(encoding="utf-8")
        self.assertIn('<line data-template-component="footer_bar"', canvas)
        self.assertNotIn('<rect data-template-component="footer_bar"', canvas)

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_canvases_are_reproducible_from_the_registry(self):
        """canvas 是 registry 的函数：手改了一边，重放就对不上。"""
        reg = registry()
        components = {item["component_id"]: item for item in reg["components"]}
        for layout_id, layout in reg["layouts"].items():
            expected = build_layout_canvas(layout_id, layout, components)
            actual = (FIDELITY / layout["canvas_file"]).read_text(encoding="utf-8").rstrip("\n")
            self.assertEqual(actual, expected, layout_id)
            self.assertEqual(locked_sha256(expected), layout["locked_sha256"], layout_id)


class LibraryPackageTests(unittest.TestCase):
    @unittest.skipUnless(DEFAULT.is_dir(), "内置模板不在库里")
    def test_package_hashes_match_the_manifest(self):
        """`template_library.py apply` 的第一道检查就是这个：包与 manifest 要一致。"""
        manifest = json.loads((DEFAULT / "manifest.json").read_text(encoding="utf-8"))
        actual = package_hashes(DEFAULT)
        self.assertEqual(actual, manifest["files"])
        self.assertEqual(manifest["package_sha256"], package_sha256(actual))

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_component_references_are_closed(self):
        validate_component_references(registry())

    @unittest.skipUnless(FIDELITY.is_dir(), "内置模板不在库里")
    def test_components_svg_matches_the_registry(self):
        reg = registry()
        expected = ("<svg xmlns=\"http://www.w3.org/2000/svg\">"
                    + "".join(f'<g id="{item["component_id"]}">'
                              f'{component_markup(item).replace("../../template_media/", "../template_media/")}'
                              f'</g>' for item in reg["components"])
                    + "</svg>")
        actual = (FIDELITY / "components.svg").read_text(encoding="utf-8").rstrip("\n")
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
