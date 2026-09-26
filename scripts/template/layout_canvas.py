#!/usr/bin/env python3
"""Build and verify reusable SVG layout canvases for template-driven pages."""

import hashlib
import html
import json
import re
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canvas_frame import FRAME_H_INT, FRAME_VIEWBOX, FRAME_W_INT  # noqa: E402

# canvas 形状的这一代编号。它写在 canvas 根上，页面实例化时继承，
# 检查画面拿页面与 canvas 的这一项对照——不写下来，两边代数不同也看不出来。
TEMPLATE_CANVAS_VERSION = "1"


def component_markup(component):
    geometry = component["geometry"]
    kind = component["source_kind"]
    attrs = f'data-template-component="{component["component_id"]}" data-template-origin="{component["origin"]}"'
    if kind == "asset":
        return (f'<image {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
                f'width="{geometry["width"]}" height="{geometry["height"]}" '
                f'href="../../template_media/{component["file"]}" data-slot="template_background"/>')
    style = component.get("style", {})
    fill = style.get("fill") or "none"
    stroke = style.get("stroke") or "none"
    stroke_width = float(style.get("stroke_width") or 0)
    if component.get("shape", {}).get("preset") == "line":
        # 一条线没有填充：着色落在 stroke 上。写 fill="none" 而不是留空，
        # 因为检查画面按「这个元素实际会画的属性」对照声明。
        return (f'<line {attrs} x1="{geometry["x"]}" y1="{geometry["y"]}" '
                f'x2="{geometry["x"] + geometry["width"]}" y2="{geometry["y"] + geometry["height"]}" '
                f'fill="none" stroke="{stroke if stroke != "none" else fill}" '
                f'stroke-width="{max(stroke_width, 1):.2f}"/>')
    if component.get("shape", {}).get("preset") == "roundRect":
        radius = min(geometry["width"], geometry["height"]) * 0.18
        return (f'<rect {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
                f'width="{geometry["width"]}" height="{geometry["height"]}" rx="{radius:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')
    if component.get("shape", {}).get("preset") == "ellipse":
        return (f'<ellipse {attrs} cx="{geometry["x"] + geometry["width"] / 2:.1f}" '
                f'cy="{geometry["y"] + geometry["height"] / 2:.1f}" '
                f'rx="{geometry["width"] / 2:.1f}" ry="{geometry["height"] / 2:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')
    return (f'<rect {attrs} x="{geometry["x"]}" y="{geometry["y"]}" '
            f'width="{geometry["width"]}" height="{geometry["height"]}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.2f}"/>')


def build_layout_canvas(layout_id, layout, component_map):
    ids = list(dict.fromkeys(layout.get("required_components", [])))
    components = [component_map[cid] for cid in ids if cid in component_map]
    backgrounds = [item for item in components if item.get("placement") == "background"]
    foregrounds = [item for item in components if item.get("placement") != "background"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" viewBox="{FRAME_VIEWBOX}" '
            f'data-layout-id="{html.escape(layout_id, quote=True)}" data-template-canvas-version="{TEMPLATE_CANVAS_VERSION}">'
            '<g data-template-lock="background">'
            f'<rect width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#F7F8FA"/>'
            + ''.join(component_markup(item) for item in backgrounds)
            + '</g><g data-template-content-layer="replace">'
            + ''
            + '</g><g data-template-lock="foreground">'
            + ''.join(component_markup(item) for item in foregrounds)
            + '</g></svg>')


def _canonical_node(node):
    attrs = ''.join(f' {key}={json.dumps(value, ensure_ascii=False)}' for key, value in sorted(node.attrib.items()))
    text = (node.text or "").strip()
    children = ''.join(_canonical_node(child) for child in list(node))
    return f'<{node.tag}{attrs}>{text}{children}</{node.tag}>'


def locked_sha256(svg_or_path):
    """锁层内容的 hash。

    没有任何 `data-template-lock` 层时**报错**，不再返回空串的 hash：
    空串会让一个根本没锁层的页面与另一个同样没锁层的页面「hash 相同」，
    把「锁层丢了」降级成「一致」。
    """
    value = Path(svg_or_path).read_text(encoding="utf-8") if isinstance(svg_or_path, Path) else str(svg_or_path)
    root = ET.fromstring(value)
    locked = [node for node in root.iter() if node.get("data-template-lock")]
    if not locked:
        raise ValueError(f"no data-template-lock layer to compare: {svg_or_path}")
    canonical = ''.join(_canonical_node(node) for node in locked)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_layout_filename(layout_id):
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(layout_id)).strip("_")
    return f"{value or 'layout'}.svg"


def ensure_layout_canvases(registry, fidelity_dir):
    """Write the canonical canvases and bind their lock hashes into the registry."""
    fidelity_dir = Path(fidelity_dir)
    canvas_dir = fidelity_dir / "layout_canvases"
    canvas_dir.mkdir(parents=True, exist_ok=True)
    component_map = {item["component_id"]: item for item in registry.get("components", [])}
    expected = set()
    for layout_id, layout in registry.get("layouts", {}).items():
        filename = safe_layout_filename(layout_id)
        expected.add(filename)
        svg = build_layout_canvas(layout_id, layout, component_map)
        path = canvas_dir / filename
        path.write_text(svg + "\n", encoding="utf-8")
        layout["canvas_file"] = f"layout_canvases/{filename}"
        layout["locked_sha256"] = locked_sha256(svg)
    for stale in canvas_dir.glob("*.svg"):
        if stale.name not in expected:
            stale.unlink()
    return registry


def registry_canvases_ready(registry, fidelity_dir):
    """每个 layout 的 canvas 都在、都是这一代、锁层 hash 都对得上。

    canvas 自己声明的代数也要是当前的：换了一代形状却沿用旧 canvas 文件，
    光比锁层 hash 是看不出来的。
    """
    layouts = registry.get("layouts", {}) if isinstance(registry, dict) else {}
    if not layouts:
        return False
    fidelity_dir = Path(fidelity_dir)
    for layout in layouts.values():
        canvas_file = layout.get("canvas_file", "")
        expected = layout.get("locked_sha256", "")
        path = fidelity_dir / canvas_file if canvas_file else None
        if not path or not path.is_file() or not expected:
            return False
        if ET.parse(path).getroot().attrib.get("data-template-canvas-version") != TEMPLATE_CANVAS_VERSION:
            return False
        try:
            if locked_sha256(path) != expected:
                return False
        except ValueError:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate executable SVG layout canvases from a fidelity registry")
    parser.add_argument("registry")
    args = parser.parse_args()
    registry_path = Path(args.registry).resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    ensure_layout_canvases(registry, registry_path.parent)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(registry_path.parent / "layout_canvases")


if __name__ == "__main__":
    main()
