import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

SVG_NS = {"svg": "http://www.w3.org/2000/svg"}

FILL_RE = re.compile(r'fill="([^"]+)"', re.I)
STROKE_RE = re.compile(r'stroke="([^"]+)"', re.I)
RX_RE = re.compile(r'rx="([^"]+)"', re.I)

# Zone thresholds for 1920x1080 canvas
HEADER_Y_MAX = 200
MAIN_Y_MAX = 960
FOOTER_Y_MIN = 960
SIDEBAR_X_START = 1200  # columns 9-12 approx


def parse_float(value, default=0.0):
    if value is None:
        return default
    cleaned = re.sub(r"[^\d.\-]", "", value)
    return float(cleaned) if cleaned else default


def get_bounds(el, attr_x, attr_y, attr_w, attr_h):
    return (
        parse_float(el.get(attr_x)),
        parse_float(el.get(attr_y)),
        parse_float(el.get(attr_w)),
        parse_float(el.get(attr_h)),
    )


def infer_grid_hint(rects):
    """Guess the grid strategy from rect layout."""
    if not rects or len(rects) < 2:
        return "full-width"

    # Sort rects by x position
    sorted_rects = sorted(rects, key=lambda r: r[0])

    # Check for equal-width columns
    widths = [r[2] for r in sorted_rects if r[2] > 100]
    if not widths:
        return "unknown"

    # Group rects by approximate x-start
    x_groups = {}
    for r in sorted_rects:
        x = round(r[0] / 20) * 20  # bucket by 20px
        if x not in x_groups:
            x_groups[x] = []
        x_groups[x].append(r)

    col_starts = sorted(x_groups.keys())
    n_cols = len(col_starts)

    if n_cols == 1:
        return "full-width"
    elif n_cols == 2:
        # Check proportions
        w1 = max(r[2] for r in x_groups[col_starts[0]])
        w2 = max(r[2] for r in x_groups[col_starts[1]]) if len(col_starts) > 1 else 0
        total = w1 + w2
        if total > 0:
            ratio = w1 / total
            if 0.4 <= ratio <= 0.45:
                return "5-7"
            elif 0.55 <= ratio <= 0.62:
                return "8-4"
            elif 0.45 <= ratio <= 0.55:
                return "6-6"
        return "2-column"
    elif n_cols == 3:
        return "4-4-4"
    elif n_cols == 4:
        return "3-3-3-3"
    return f"{n_cols}-column"


def infer_zones(rects, texts, images):
    """Infer which elements fall in header/main/sidebar/footer zones."""
    zones = {"header": 0, "main": 0, "sidebar": 0, "footer": 0}

    for r in rects:
        x, y, w, h = r
        if w <= 0 or h <= 0:
            continue
        if y + h <= HEADER_Y_MAX:
            zones["header"] += 1
        elif y >= FOOTER_Y_MIN:
            zones["footer"] += 1
        elif x >= SIDEBAR_X_START:
            zones["sidebar"] += 1
        else:
            zones["main"] += 1

    # Text-based zone refinement
    for t in texts:
        x, y, w, h = t
        if w <= 0:
            continue
        if y + h <= HEADER_Y_MAX:
            zones["header"] += 1
        elif y >= FOOTER_Y_MIN:
            zones["footer"] += 1
        elif x >= SIDEBAR_X_START:
            zones["sidebar"] += 1
        else:
            zones["main"] += 1

    return zones


def analyze(path):
    content = path.read_text(encoding="utf-8-sig")
    root = ET.fromstring(content)

    # Canvas size
    viewbox = root.get("viewBox", "0 0 1920 1080").split()
    canvas_w = parse_float(viewbox[2], 1920.0) if len(viewbox) >= 4 else 1920.0
    canvas_h = parse_float(viewbox[3], 1080.0) if len(viewbox) >= 4 else 1080.0

    # Rects
    rect_nodes = root.findall(".//{http://www.w3.org/2000/svg}rect")
    if not rect_nodes:
        rect_nodes = root.findall(".//rect")
    rects = []
    for el in rect_nodes:
        b = get_bounds(el, "x", "y", "width", "height")
        if b[2] > 0 and b[3] > 0:
            rects.append(b)

    # Sort rects by area descending for "major rects"
    major_rects = sorted(rects, key=lambda r: r[2] * r[3], reverse=True)[:8]

    # Texts
    text_nodes = root.findall(".//{http://www.w3.org/2000/svg}text")
    if not text_nodes:
        text_nodes = root.findall(".//text")
    texts = []
    for el in text_nodes:
        x = parse_float(el.get("x"))
        y = parse_float(el.get("y"))
        fs = parse_float(el.get("font-size"), 24.0)
        content_text = "".join(el.itertext()).strip()
        w = 0.0
        for ch in content_text:
            w += fs * (0.56 if ord(ch) < 128 else 0.92)
        texts.append((x, y - fs, w, fs * 1.18))

    # Images
    image_nodes = root.findall(".//{http://www.w3.org/2000/svg}image")
    if not image_nodes:
        image_nodes = root.findall(".//image")
    images = []
    for el in image_nodes:
        b = get_bounds(el, "x", "y", "width", "height")
        if b[2] > 0 and b[3] > 0:
            slot = el.get("data-slot", "")
            images.append({"bounds": list(b), "slot": slot})

    # Color extraction (lightweight token extraction kept)
    fills = Counter(FILL_RE.findall(content))
    strokes = Counter(STROKE_RE.findall(content))
    radii = Counter(RX_RE.findall(content))

    # Zone inference
    zones = infer_zones(rects, texts, images)

    # Grid hint
    grid_hint = infer_grid_hint(rects)

    return {
        "file": str(path),
        "canvas": {"width": canvas_w, "height": canvas_h},
        "rect_count": len(rects),
        "major_rects": [{"x": r[0], "y": r[1], "w": r[2], "h": r[3]} for r in major_rects],
        "text_count": len(texts),
        "text_distribution": {
            "header": sum(1 for t in texts if t[1] + t[3] <= HEADER_Y_MAX),
            "main": sum(1 for t in texts if HEADER_Y_MAX < t[1] + t[3] <= FOOTER_Y_MIN),
            "footer": sum(1 for t in texts if t[1] >= FOOTER_Y_MIN),
        },
        "image_count": len(images),
        "images": images,
        "top_fills": fills.most_common(8),
        "top_strokes": strokes.most_common(8),
        "top_corner_radii": radii.most_common(8),
        "zones": zones,
        "grid_hint": grid_hint,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract structural data from reference SVG slides for layout planning."
    )
    parser.add_argument("svg_dir", help="Directory (or single SVG file) containing reference SVGs")
    parser.add_argument("--output", default="", help="Output JSON path (default: <svg_dir>/reference_layout_tokens.json)")
    args = parser.parse_args()

    svg_path = Path(args.svg_dir)
    if svg_path.is_dir():
        svg_files = sorted(svg_path.glob("*.svg"))
    elif svg_path.is_file() and svg_path.suffix.lower() == ".svg":
        svg_files = [svg_path]
    else:
        svg_files = []

    if not svg_files:
        print(json.dumps({"error": "No SVG files found"}, ensure_ascii=False, indent=2))
        return

    data = [analyze(f) for f in svg_files]

    output_path = Path(args.output) if args.output else (svg_path if svg_path.is_dir() else svg_path.parent) / "reference_layout_tokens.json"
    output_path.write_text(json.dumps({"slides": data}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Analyzed {len(data)} reference SVG(s) → {output_path}")


if __name__ == "__main__":
    main()
