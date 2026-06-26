"""
Estimate whether planned slide copy can fit approved wireframe regions.

This is a lightweight planning aid, not an auto-layout engine. It reads
page_content.json and layout_plan.json, estimates text load against each
wireframe region, and writes layout_capacity_report.json for layout review.

Usage:
  python estimate_layout_capacity.py <project_dir> [--output <path>]
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

CANVAS_W = 1920
CANVAS_H = 1080
DEFAULT_LINE_HEIGHT = 1.38


def load_json(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Missing file: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {p}: {exc}") from exc


def visual_chars(text):
    total = 0.0
    for ch in str(text or ""):
        if ch.isspace():
            total += 0.25
        elif ord(ch) < 128:
            total += 0.55
        else:
            total += 1.0
    return total


def block_text(block):
    if not isinstance(block, dict):
        return str(block)
    btype = block.get("type", "")
    if btype in {"bullet_list", "numbered_list"}:
        return "\n".join(str(x) for x in block.get("items", []))
    if btype == "kpi_set":
        items = block.get("items", [])
        if isinstance(items, list):
            return "\n".join(str(x) for x in items)
    return str(block.get("text", ""))


def table_text(tables):
    chunks = []
    for table in tables or []:
        if not isinstance(table, dict):
            continue
        chunks.extend(str(h) for h in table.get("headers", []) or [])
        for row in table.get("rows", []) or []:
            chunks.extend(str(c) for c in row)
    return "\n".join(chunks)


def content_segments(page):
    body = "\n".join(block_text(b) for b in page.get("body_blocks", []) or [])
    return {
        "action_title": str(page.get("action_title", "")),
        "core_message": str(page.get("core_message", "")),
        "body_blocks": body,
        "tables": table_text(page.get("tables", []) or []),
    }


def kept_segments(layout_page, content_page):
    segments = content_segments(content_page)
    kept = []
    ch = layout_page.get("copy_handling", {}) if isinstance(layout_page, dict) else {}
    final_copy = ch.get("final_on_slide", {}) if isinstance(ch, dict) else {}
    if isinstance(final_copy, dict):
        title = str(final_copy.get("title", "") or segments.get("action_title", ""))
        subtitle = str(final_copy.get("subtitle", "") or "")
        body_value = final_copy.get("body", [])
        if isinstance(body_value, list):
            body = "\n".join(str(x) for x in body_value)
        else:
            body = str(body_value or "")
        footer = str(final_copy.get("footer_takeaway", "") or "")
        final_segments = []
        if title.strip():
            final_segments.append(("action_title", title))
        if subtitle.strip():
            final_segments.append(("core_message", subtitle))
        main_text = "\n".join(x for x in [body, footer] if x.strip())
        if main_text.strip():
            final_segments.append(("body_blocks", main_text))
        if final_segments:
            return final_segments

    kept_names = ch.get("kept_on_slide", []) if isinstance(ch, dict) else []
    if not kept_names:
        kept_names = ["action_title", "core_message", "body_blocks"]

    joined = " ".join(str(x).lower() for x in kept_names)
    for key, text in segments.items():
        if not text.strip():
            continue
        if key in joined or any(part in joined for part in key.split("_")):
            kept.append((key, text))

    if not kept:
        for key in ("action_title", "core_message", "body_blocks"):
            text = segments.get(key, "")
            if text.strip():
                kept.append((key, text))
    return kept


def font_size_for_zone(zone, label, page_density):
    z = (zone or "").lower()
    l = (label or "").lower()
    if "header" in z or "title" in l or "标题" in label:
        return 46
    if "footer" in z or "source" in l or "页脚" in label:
        return 18
    if page_density == "dense":
        return 24
    if page_density == "airy":
        return 32
    return 28


def chars_per_line(width, font_size):
    usable_w = max(1.0, float(width) - 48.0)
    avg_char_w = font_size * 0.78
    return max(1, math.floor(usable_w / avg_char_w))


def max_lines(height, font_size):
    usable_h = max(1.0, float(height) - 40.0)
    return max(1, math.floor(usable_h / (font_size * DEFAULT_LINE_HEIGHT)))


def classify(utilization, estimated_chars, zone):
    if estimated_chars <= 0:
        return "too_empty" if zone not in {"footer"} else "ok"
    if utilization > 1.18:
        return "overfull"
    if utilization > 0.88:
        return "tight"
    if utilization < 0.18:
        return "too_empty"
    return "ok"


def assign_text_to_regions(layout_page, content_page):
    regions = layout_page.get("wireframe", []) or []
    segments = kept_segments(layout_page, content_page)
    if not regions:
        return []

    title = dict(segments).get("action_title", "")
    core = dict(segments).get("core_message", "")
    body = "\n".join(text for key, text in segments if key not in {"action_title", "core_message"})

    assigned = []
    main_regions = []
    for region in regions:
        zone = str(region.get("zone", ""))
        label = str(region.get("label", ""))
        zl = zone.lower()
        ll = label.lower()
        if "header" in zl or "title" in ll or "标题" in label:
            text = title
        elif "footer" in zl or "页脚" in label or "source" in ll:
            text = ""
        else:
            main_regions.append(region)
            text = ""
        assigned.append((region, text))

    main_text = "\n".join(x for x in [core, body] if x.strip())
    if main_regions and main_text.strip():
        per_region = split_text_load(main_text, len(main_regions))
        next_main = 0
        rebuilt = []
        for region, text in assigned:
            if region in main_regions:
                text = per_region[next_main]
                next_main += 1
            rebuilt.append((region, text))
        assigned = rebuilt
    return assigned


def split_text_load(text, parts):
    if parts <= 1:
        return [text]
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return [""] * parts
    buckets = [""] * parts
    for idx, line in enumerate(lines):
        bucket = idx % parts
        buckets[bucket] = (buckets[bucket] + "\n" + line).strip()
    return buckets


def page_capacity(layout_page, content_page):
    page_density = layout_page.get("visual_density", "balanced")
    regions_out = []
    status_rank = {"ok": 0, "too_empty": 1, "tight": 2, "overfull": 3}
    worst = "ok"

    for region, text in assign_text_to_regions(layout_page, content_page):
        zone = str(region.get("zone", ""))
        label = str(region.get("label", ""))
        font_size = font_size_for_zone(zone, label, page_density)
        est_chars = visual_chars(text)
        cpl = chars_per_line(region.get("w", 0), font_size)
        lines = int(math.ceil(est_chars / max(cpl, 1))) if est_chars else 0
        max_l = max_lines(region.get("h", 0), font_size)
        utilization = lines / max(max_l, 1)
        status = classify(utilization, est_chars, zone)
        if status_rank[status] > status_rank[worst]:
            worst = status

        regions_out.append({
            "zone": zone,
            "label": label,
            "box": {
                "x": region.get("x", 0),
                "y": region.get("y", 0),
                "w": region.get("w", 0),
                "h": region.get("h", 0),
            },
            "estimated_chars": round(est_chars, 1),
            "font_size": font_size,
            "estimated_lines": lines,
            "max_lines": max_l,
            "utilization": round(utilization, 2),
            "status": status,
        })

    recommendations = []
    if worst == "overfull":
        recommendations.append("Primary copy likely exceeds its planned region. Change layout, move explanatory copy to notes, or split the page before SVG generation.")
    elif worst == "tight":
        recommendations.append("Copy may fit but needs deliberate line breaks and spacing. Avoid solving this by shrinking body text below readability limits.")
    elif worst == "too_empty":
        recommendations.append("One or more planned regions look underused. Confirm this is intentional whitespace or add a clearer visual role.")

    return {
        "status": worst,
        "summary": summarize_status(worst),
        "regions": regions_out,
        "recommendations": recommendations,
    }


def summarize_status(status):
    return {
        "ok": "Planned copy is likely to fit.",
        "tight": "Planned copy may fit but needs careful line breaks or a larger zone.",
        "overfull": "Planned copy likely cannot fit without layout or copy-handling changes.",
        "too_empty": "Some planned regions may be underused unless whitespace is intentional.",
    }.get(status, status)


def main():
    parser = argparse.ArgumentParser(description="Estimate layout copy capacity.")
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--output", default="", help="Output JSON path")
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"
    content = load_json(internal / "01_content" / "page_content.json")
    layout = load_json(internal / "01_layout_plan" / "layout_plan.json")

    content_by_key = {
        p.get("page_key"): p
        for p in content.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }

    pages = {}
    for lp in layout.get("pages", []):
        if not isinstance(lp, dict):
            continue
        pk = lp.get("page_key")
        if not pk:
            continue
        pages[pk] = page_capacity(lp, content_by_key.get(pk, {}))

    report = {
        "project": layout.get("project") or content.get("project") or root.name,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "canvas": {"w": CANVAS_W, "h": CANVAS_H},
        "pages": pages,
    }

    output_path = Path(args.output) if args.output else internal / "01_layout_plan" / "layout_capacity_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {output_path} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
