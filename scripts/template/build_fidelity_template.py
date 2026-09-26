#!/usr/bin/env python3
"""Build Planner's reusable fidelity template package from a reviewed decision.

The extractor records facts. A visual Template Worker writes
``template_worker_result.json`` to choose only safe reusable candidates. This
script materializes that choice as a compact component/layout contract consumed
by the SVG stage. It never guesses missing source components.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canvas_frame import FRAME_H, FRAME_W  # noqa: E402

from layout_canvas import component_markup, ensure_layout_canvases


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_canvas(value, default=(1280.0, 720.0)):
    if isinstance(value, dict) and value.get("width") and value.get("height"):
        return float(value["width"]), float(value["height"])
    if isinstance(value, str) and "x" in value.lower():
        try:
            width, height = value.lower().split("x", 1)
            return float(width), float(height)
        except ValueError:
            pass
    return default


def validate_override(source, approval, source_canvas):
    geometry = dict(source.get("geometry") or source.get("display_geometry") or {})
    override = approval.get("geometry_override", {})
    if override:
        if not str(approval.get("override_reason", "")).strip():
            raise ValueError(f"geometry_override requires override_reason: {approval.get('component_id')}")
        canvas_w, canvas_h = source_canvas
        for key, value in override.items():
            if key not in geometry or key not in {"x", "y", "width", "height"}:
                raise ValueError(f"unsupported geometry override {key!r}: {approval.get('component_id')}")
            base = float(geometry[key])
            delta = abs(float(value) - base)
            limit = max((canvas_w if key in {"x", "width"} else canvas_h) * 0.03,
                        abs(base) * (0.20 if key in {"width", "height"} else 0.10))
            if delta > limit:
                raise ValueError(f"geometry_override is too large for fidelity component {approval.get('component_id')}: {key}")
        geometry.update(override)
    style = dict(source.get("style", {}))
    style_override = approval.get("style_override", {})
    for key, value in style_override.items():
        if key not in {"fill", "stroke", "stroke_width"}:
            raise ValueError(f"unsupported style override {key!r}: {approval.get('component_id')}")
        if key in {"fill", "stroke"} and value and not style.get(key) and not approval.get("evidence_pages"):
            raise ValueError(f"missing source {key} requires visual evidence_pages: {approval.get('component_id')}")
    style.update(style_override)
    if source.get("contains_text") and approval.get("text_handling") != "strip":
        raise ValueError(f"text-bearing component requires text_handling=strip: {approval.get('component_id')}")
    return geometry, style


def scale_geometry(geometry, source_canvas, target_canvas):
    sx = target_canvas[0] / max(source_canvas[0], 1)
    sy = target_canvas[1] / max(source_canvas[1], 1)
    return {"x": round(float(geometry["x"]) * sx, 2), "y": round(float(geometry["y"]) * sy, 2),
            "width": round(float(geometry["width"]) * sx, 2), "height": round(float(geometry["height"]) * sy, 2)}


def main():
    parser = argparse.ArgumentParser(description="Materialize a reviewed fidelity template package")
    parser.add_argument("--project", required=True)
    parser.add_argument("--decision", default="")
    args = parser.parse_args()
    root = Path(args.project).resolve()
    project = root / "_internal" / "00_project"
    profile = read_json(project / "template_profile.json")
    decision_path = Path(args.decision) if args.decision else project / "template_worker_result.json"
    decision = read_json(decision_path)
    if decision.get("status") != "completed" or decision.get("mode") != "fidelity":
        raise ValueError("template worker result must be completed with mode=fidelity")

    facts = profile.get("structural_extraction", {})
    candidates = {item.get("candidate_id"): item for item in facts.get("native_shapes", [])}
    assets = {item.get("asset_id"): item for item in facts.get("assets", [])}
    components = []
    used_source_ids = set()
    default_source_canvas = parse_canvas(facts.get("canvas"))
    target_canvas = (FRAME_W, FRAME_H)
    for approval in decision.get("approved_components", []):
        source_id = approval.get("source_id")
        source = candidates.get(source_id) or assets.get(source_id)
        if not source:
            raise ValueError(f"approved component source is unknown: {source_id}")
        component_id = approval.get("component_id")
        if not component_id:
            raise ValueError("approved component is missing component_id")
        if source_id in used_source_ids:
            raise ValueError(f"one source candidate cannot define multiple fidelity components: {source_id}")
        used_source_ids.add(source_id)
        source_kind = "asset" if source_id in assets else "native_shape"
        source_canvas = parse_canvas(source.get("source_canvas"), default_source_canvas)
        source_geometry, style = validate_override(source, approval, source_canvas)
        if source_kind == "native_shape" and not (style.get("fill") or style.get("stroke")):
            raise ValueError(f"native fidelity component has no visible fill/stroke evidence: {component_id}")
        geometry = scale_geometry(source_geometry, source_canvas, target_canvas)
        placement = approval.get("placement", "background")
        geometry_policy = approval.get("geometry_policy") or (
            "adaptable" if placement in {"content_surface", "content_label"} else "fixed"
        )
        if geometry_policy not in {"fixed", "adaptable"}:
            raise ValueError(f"invalid geometry_policy for {component_id}: {geometry_policy}")
        components.append({
            "component_id": component_id,
            "role": approval.get("role", "decoration"),
            "required_by_default": bool(approval.get("required_by_default", False)),
            "placement": placement,
            "geometry_policy": geometry_policy,
            "origin": source_kind,
            "source_id": source_id,
            "source_kind": source_kind,
            "source_page": source.get("source_page") or (source.get("source_pages") or [None])[0],
            "source_pages": source.get("source_pages") or [source.get("source_page")],
            "source_geometry": source_geometry,
            "geometry": geometry,
            "style": style,
            "shape": source.get("shape", {}),
            "file": source.get("file"),
        })
    layout_map = {}
    known_components = {item["component_id"] for item in components}
    for layout in decision.get("layouts", []):
        layout_id = layout.get("layout_id")
        required = layout.get("required_components", [])
        optional = layout.get("optional_components", [])
        unknown = sorted(set(required + optional) - known_components)
        if not required:
            raise ValueError(f"invalid fidelity layout {layout_id or '<missing>'}; required_components cannot be empty")
        if not layout_id or unknown:
            raise ValueError(f"invalid layout {layout_id or '<missing>'}; unknown components: {unknown}")
        layout_map[layout_id] = {"required_components": required, "optional_components": optional}
    if not layout_map:
        raise ValueError("fidelity template requires at least one layout")
    if "content_base" not in layout_map:
        raise ValueError("fidelity template requires a content_base layout")
    referenced = {
        component_id for layout in layout_map.values()
        for component_id in layout["required_components"] + layout["optional_components"]
    }
    unreferenced = sorted(known_components - referenced)
    if unreferenced:
        raise ValueError(f"approved components must be referenced by at least one layout: {unreferenced}")

    output = project / "fidelity_template"
    output.mkdir(parents=True, exist_ok=True)
    registry = {
        "schema": "planner.fidelity-template.v2",
        "mode": "fidelity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": profile.get("source_files", []),
        "source_canvas": {"width": default_source_canvas[0], "height": default_source_canvas[1]},
        "target_canvas": {"width": target_canvas[0], "height": target_canvas[1]},
        "components": components,
        "layouts": layout_map,
    }
    ensure_layout_canvases(registry, output)
    write_json(output / "template_registry.json", registry)
    symbols = []
    for component in components:
        # The symbol is an inspectable reusable source. Final SVGs inline it so
        # SVG-to-PPT conversion remains self-contained and editable.
        markup = component_markup(component).replace('../../template_media/', '../template_media/')
        symbols.append(f'<g id="{component["component_id"]}">{markup}</g>')
    (output / "components.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">' + "".join(symbols) + '</svg>\n', encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
