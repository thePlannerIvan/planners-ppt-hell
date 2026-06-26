import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

SVG_NS = {"svg": "http://www.w3.org/2000/svg"}
TEXT_RE = re.compile(r"\s+")
TRANSLATE_RE = re.compile(r"translate\(\s*([\d.eE+-]+)\s*[,\s]\s*([\d.eE+-]+)\s*\)")
SCALE_RE = re.compile(r"scale\(\s*([\d.eE+-]+)(?:\s*[,\s]\s*([\d.eE+-]+))?\s*\)")
COMMENT_RE = re.compile(r"<!--\s*(.*?)\s*-->", re.DOTALL)

# ── Configuration ──────────────────────────────────────────────

CANVAS_W = 1920.0
CANVAS_H = 1080.0
MARGIN = 60.0
FOOTER_Y_START = 960.0
MAX_FONT_SIZE_TIERS = 4
MIN_BODY_FONT = 20.0
MIN_CIRCLE_R = 6
TEXT_TIGHT_HORIZONTAL_PX = 6.0
TEXT_TIGHT_VERTICAL_PX = 10.0
TEXT_MAJOR_HORIZONTAL_PX = 16.0
TEXT_MAJOR_VERTICAL_PX = 24.0
VALID_FONT_WEIGHTS = {"normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"}

# Registered layout IDs from 05_layout_taxonomy.md
REGISTERED_LAYOUTS = {f"L{n:02d}" for n in range(1, 16)}  # L01-L15

# Wesdom palette tokens (hex, uppercase)
WESDOM_TOKENS = {
    "#F5F7FA", "#051C2C", "#E60012", "#333333", "#555555",
    "#999999", "#FFFFFF", "#E0E0E0", "#DCDCDC", "#CCCCCC",
    "#F2F2F2", "#006BA6", "#E3F2FD", "#007A53", "#E8F5E9",
    "#D46A00", "#FFF3E0", "#C62828", "#FFEBEE",
}

APPROVED_RATIOS = {
    (16, 9), (16, 10), (4, 3), (3, 2), (1, 1), (3, 4), (21, 9),
}
RATIO_TOLERANCE = 0.04

# Hard-gate prohibited SVG elements/attributes (P0)
PROHIBITED_ELEMENTS = [
    "foreignObject", "filter", "use", "style", "marker", "mask", "animate",
]
PROHIBITED_ATTRIBUTES = [
    "stroke-dasharray", "textLength", "lengthAdjust",
    "marker-start", "marker-mid", "marker-end",
]
PROHIBITED_TRANSFORMS = [
    "rotate(",
]

# ── Helpers ─────────────────────────────────────────────────────

def parse_float(value, default=0.0):
    if value is None:
        return default
    cleaned = re.sub(r"[^\d.\-]", "", value)
    return float(cleaned) if cleaned else default


def parse_color(value):
    """Normalize a fill/stroke color to uppercase hex for comparison."""
    if not value or value == "none":
        return None
    v = value.strip().upper()
    if v.startswith("#"):
        return v
    if v.startswith("URL("):
        return None  # gradient references not checked
    return v


def parse_transform(transform):
    dx, dy = 0.0, 0.0
    sx, sy = 1.0, 1.0
    m = TRANSLATE_RE.search(transform or "")
    if m:
        dx = float(m.group(1))
        dy = float(m.group(2))
    m = SCALE_RE.search(transform or "")
    if m:
        sx = float(m.group(1))
        sy = float(m.group(2)) if m.group(2) else sx
    return dx, dy, sx, sy


def get_accumulated_transform(node, parent_map):
    """Match native_svg_to_ppt.py's supported transform semantics.

    The converter supports translate() and scale() on ancestor <g> nodes. It
    accumulates raw offsets first, then applies accumulated scale to child
    coordinates. Keep the validator aligned with that behavior, even though it
    is a simplified SVG transform model.
    """
    ancestors = []
    current = node
    while current in parent_map:
        current = parent_map[current]
        ancestors.append(current)
    ancestors.reverse()

    dx, dy = 0.0, 0.0
    sx, sy = 1.0, 1.0
    for ancestor in ancestors:
        tx, ty, tsx, tsy = parse_transform(ancestor.get("transform", ""))
        dx += tx
        dy += ty
        sx *= tsx
        sy *= tsy
    return dx, dy, sx, sy


def build_parent_map(root):
    pm = {}
    for parent in root.iter():
        for child in parent:
            pm[child] = parent
    return pm


def estimate_text_width(content, font_size):
    w = 0.0
    for ch in content:
        w += font_size * (0.56 if ord(ch) < 128 else 0.92)
    return w


def estimate_text_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    x = (parse_float(node.get("x")) + dx) * sx
    y = (parse_float(node.get("y")) + dy) * sy
    font_size = parse_float(node.get("font-size"), 24.0) * min(sx, sy)
    content = "".join(node.itertext())
    content = TEXT_RE.sub(" ", content).strip()
    w = estimate_text_width(content, font_size) if content else 0.0
    h = font_size * 1.18
    return (x, y - font_size, w, h)


def rect_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        (parse_float(node.get("x")) + dx) * sx,
        (parse_float(node.get("y")) + dy) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def image_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        (parse_float(node.get("x")) + dx) * sx,
        (parse_float(node.get("y")) + dy) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and by < ay + ah and by + bh > ay


def outside_safe_margin(box, margin=MARGIN):
    x, y, w, h = box
    # Bottom check is relaxed for footer-zone elements
    if y >= FOOTER_Y_START:
        return x < margin or y < margin or x + w > CANVAS_W - margin
    return x < margin or y < margin or x + w > CANVAS_W - margin or y + h > CANVAS_H - margin


def in_footer_zone(box):
    """True if the element is entirely within or crosses into the footer zone."""
    x, y, w, h = box
    return (y + h) > FOOTER_Y_START


def ratio_near_approved(w, h):
    if w <= 0 or h <= 0:
        return False
    for rw, rh in APPROVED_RATIOS:
        expected = rw / rh
        actual = w / h
        if abs(actual - expected) < RATIO_TOLERANCE:
            return True
    return False


def extract_metadata_comment(svg_text):
    """Parse metadata from the first SVG comment containing data-layout."""
    m = COMMENT_RE.search(svg_text[:3000])
    if not m:
        return {}
    comment = m.group(1)
    meta = {}
    for key in ("page_key", "data-layout", "page_mode", "visual_density", "reason"):
        pattern = rf'{key}\s*=\s*"([^"]*)"'
        km = re.search(pattern, comment)
        if km:
            meta[key] = km.group(1)
    return meta


def box_to_dict(box):
    return {"x": round(box[0], 1), "y": round(box[1], 1), "w": round(box[2], 1), "h": round(box[3], 1)}


def box_area(box):
    return max(0.0, box[2]) * max(0.0, box[3])


def intersection_box(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return (0.0, 0.0, 0.0, 0.0)
    return (x1, y1, x2 - x1, y2 - y1)


def text_content(node):
    return TEXT_RE.sub(" ", "".join(node.itertext())).strip()


def visual_length(text):
    """Approximate visible character count for text-anchor risk checks."""
    score = 0.0
    for ch in text:
        score += 0.5 if ord(ch) < 128 else 1.0
    return score


def is_full_canvas_rect(box):
    x, y, w, h = box
    return x <= 5 and y <= 5 and w >= CANVAS_W * 0.95 and h >= CANVAS_H * 0.95


def rect_contains_point(rect, x, y, padding=0):
    rx, ry, rw, rh = rect
    return (
        x >= rx + padding and x <= rx + rw - padding
        and y >= ry + padding and y <= ry + rh - padding
    )


def choose_text_container(tbox, rect_boxes):
    """Choose the most likely content container for a text box.

    Prefer the smallest non-background rect that contains the text center or
    the text starting point. Very long text often overflows so far that its
    center leaves the source container; checking the origin keeps diagnostics
    attached to the intended card.
    This avoids treating full-canvas backgrounds or decorative bands as the
    container that should constrain overflow.
    """
    tx, ty, tw, th = tbox
    cx = tx + tw / 2
    cy = ty + th / 2
    ox = tx
    oy = ty + th / 2
    candidates = []
    for idx, rbox in rect_boxes:
        if rbox[2] <= 0 or rbox[3] <= 0 or is_full_canvas_rect(rbox):
            continue
        if rect_contains_point(rbox, cx, cy) or rect_contains_point(rbox, ox, oy):
            candidates.append((rbox[2] * rbox[3], idx, rbox))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1], candidates[0][2]


def direction_hint(box, container):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    rx, ry, rw, rh = container
    rcx, rcy = rx + rw / 2, ry + rh / 2
    dx = cx - rcx
    dy = cy - rcy
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "down" if dy >= 0 else "up"


def text_overflow_guidance(tbox, rbox, font_size, text):
    tx, ty, tw, th = tbox
    rx, ry, rw, rh = rbox
    pad_x, pad_y = 24.0, 20.0
    available_w = max(1.0, rw - pad_x * 2)
    available_h = max(1.0, rh - pad_y * 2)
    overflow_left = max(0.0, (rx + pad_x) - tx)
    overflow_right = max(0.0, (tx + tw) - (rx + rw - pad_x))
    overflow_top = max(0.0, (ry + pad_y) - ty)
    overflow_bottom = max(0.0, (ty + th) - (ry + rh - pad_y))
    suggested_lines = max(1, math.ceil(tw / available_w))
    max_lines_by_height = max(1, math.floor(available_h / max(font_size * 1.45, 1)))
    suggested_font_size = max(MIN_BODY_FONT, min(font_size, font_size * available_w / max(tw, 1.0)))
    fits_by_wrap = suggested_lines <= max_lines_by_height
    diagnosis = {
        "text": text[:80],
        "text_box": box_to_dict(tbox),
        "container_box": box_to_dict(rbox),
        "available_width": round(available_w, 1),
        "available_height": round(available_h, 1),
        "estimated_text_width": round(tw, 1),
        "overflow_px": {
            "left": round(overflow_left, 1),
            "right": round(overflow_right, 1),
            "top": round(overflow_top, 1),
            "bottom": round(overflow_bottom, 1),
        },
    }
    recommended_fix = {
        "type": "wrap_or_rebalance_text",
        "action": "先把长文本拆成多行独立 <text>，保持 text-anchor=\"start\"；如果仍放不下，扩大文本区或减少上屏文字。",
        "suggested_lines": suggested_lines,
        "max_lines_in_current_box": max_lines_by_height,
        "suggested_font_size": round(suggested_font_size, 1),
        "minimum_font_size": MIN_BODY_FONT,
        "fits_if_wrapped": fits_by_wrap,
    }
    if not fits_by_wrap:
        recommended_fix["escalation"] = "当前容器高度不足；不要继续压低字号，应改版式、拆页或把解释性文字移到备注。"
    return diagnosis, recommended_fix


def classify_text_fit_issue(diagnosis, font_size):
    """Classify estimated text/container mismatch by delivery risk.

    SVG text bounds are estimated, especially vertically around baselines. Small
    top/bottom drift should help the model inspect the page, not block the gate.
    """
    overflow = diagnosis.get("overflow_px", {})
    left = float(overflow.get("left", 0.0) or 0.0)
    right = float(overflow.get("right", 0.0) or 0.0)
    top = float(overflow.get("top", 0.0) or 0.0)
    bottom = float(overflow.get("bottom", 0.0) or 0.0)
    horizontal = max(left, right)
    vertical = max(top, bottom)
    line_height = max(font_size * 1.18, 1.0)

    major_horizontal = max(TEXT_MAJOR_HORIZONTAL_PX, font_size * 0.35)
    major_vertical = max(TEXT_MAJOR_VERTICAL_PX, line_height * 0.45)

    if horizontal > major_horizontal or vertical > major_vertical:
        return (
            "warning",
            "TEXT_OVERFLOW_MAJOR",
            "Text likely overflows its container enough to affect readability or PPT conversion",
            "major",
        )
    if horizontal > TEXT_TIGHT_HORIZONTAL_PX or vertical > TEXT_TIGHT_VERTICAL_PX:
        return (
            "warning",
            "TEXT_CONTAINER_TIGHT",
            "Text is tight inside its container; review visually and fix if it looks cramped",
            "review",
        )
    return (
        "info",
        "TEXT_BASELINE_ESTIMATE_DRIFT",
        "Minor text-box drift detected; likely baseline estimation, not a hard layout problem",
        "minor",
    )


def safe_margin_guidance(box, margin):
    x, y, w, h = box
    overflow = {
        "left": round(max(0.0, margin - x), 1),
        "top": round(max(0.0, margin - y), 1),
        "right": round(max(0.0, x + w - (CANVAS_W - margin)), 1),
        "bottom": round(max(0.0, y + h - (CANVAS_H - margin)), 1),
    }
    direction = max(overflow, key=overflow.get)
    reverse = {"left": "right", "right": "left", "top": "down", "bottom": "up"}[direction]
    return (
        {"box": box_to_dict(box), "safe_margin": margin, "overflow_px": overflow},
        {
            "type": "move_inside_safe_area",
            "action": f"将元素整体向 {reverse} 移动至少 {overflow[direction]:.0f}px，或缩小相邻模块释放安全边距。",
        },
    )


def overlap_guidance(box_a, box_b, label_a, label_b):
    ibox = intersection_box(box_a, box_b)
    overlap_area = box_area(ibox)
    smaller_area = max(1.0, min(box_area(box_a), box_area(box_b)))
    direction = direction_hint(box_a, box_b)
    move_map = {"left": "left", "right": "right", "up": "up", "down": "down"}
    return (
        {
            "a": {"id": label_a, "box": box_to_dict(box_a)},
            "b": {"id": label_b, "box": box_to_dict(box_b)},
            "overlap_box": box_to_dict(ibox),
            "overlap_area": round(overlap_area, 1),
            "overlap_ratio_of_smaller": round(overlap_area / smaller_area, 3),
        },
        {
            "type": "separate_elements",
            "action": f"优先将 {label_a} 向 {move_map[direction]} 移出重叠区；如果移动后破坏版式，改为缩短文字、增大行距或重新分配模块空间。",
        },
    )


def element_density_guidance(boxes):
    regions = {
        "left": (0.0, 0.0, CANVAS_W / 2, CANVAS_H),
        "right": (CANVAS_W / 2, 0.0, CANVAS_W / 2, CANVAS_H),
        "top": (0.0, 0.0, CANVAS_W, CANVAS_H / 2),
        "bottom": (0.0, CANVAS_H / 2, CANVAS_W, CANVAS_H / 2),
    }
    density = {}
    for name, region in regions.items():
        area = box_area(region)
        occupied = sum(box_area(intersection_box(box, region)) for _, box in boxes)
        density[name] = occupied / area if area else 0.0
    return {k: round(v, 3) for k, v in density.items()}


def box_union(boxes):
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    return (x1, y1, x2 - x1, y2 - y1)


def region_occupancy(boxes, region):
    area = box_area(region)
    if area <= 0:
        return 0.0
    occupied = sum(box_area(intersection_box(box, region)) for box in boxes)
    return min(1.0, occupied / area)


def large_empty_region_guidance(boxes):
    regions = {
        "左上": (MARGIN, 120.0, (CANVAS_W - MARGIN * 2) / 2, 390.0),
        "右上": (CANVAS_W / 2, 120.0, (CANVAS_W - MARGIN * 2) / 2, 390.0),
        "左下": (MARGIN, 520.0, (CANVAS_W - MARGIN * 2) / 2, 420.0),
        "右下": (CANVAS_W / 2, 520.0, (CANVAS_W - MARGIN * 2) / 2, 420.0),
    }
    emptiest = None
    for name, region in regions.items():
        occupancy = region_occupancy(boxes, region)
        if emptiest is None or occupancy < emptiest[1]:
            emptiest = (name, occupancy, region)
    if not emptiest or emptiest[1] >= 0.08:
        return None
    name, occupancy, region = emptiest
    return (
        {
            "region": name,
            "region_box": box_to_dict(region),
            "estimated_occupancy": round(occupancy, 3),
        },
        {
            "type": "rebalance_empty_space",
            "action": (
                f"页面{name}存在大块低利用空白。若这是理性信息页，优先扩大关键模块、"
                "改成洞察卡/时间轴/摘要区，或把相邻模块重新分配到该区域；情绪页可人工接受。"
            ),
        },
    )


def low_module_utilization_guidance(rect_box_value, text_boxes_inside):
    if not text_boxes_inside:
        return None
    rx, ry, rw, rh = rect_box_value
    if rw < CANVAS_W * 0.45 or rh < CANVAS_H * 0.12:
        return None
    if rw < CANVAS_W * 0.65 and len(text_boxes_inside) < 12:
        return None
    union = box_union(text_boxes_inside)
    used_w = union[2] / max(rw, 1.0)
    used_h = union[3] / max(rh, 1.0)
    if used_w >= 0.68 and used_h >= 0.48:
        return None
    return (
        {
            "module_box": box_to_dict(rect_box_value),
            "text_union_box": box_to_dict(union),
            "used_width_ratio": round(used_w, 3),
            "used_height_ratio": round(used_h, 3),
        },
        {
            "type": "improve_module_utilization",
            "action": (
                "这个大模块占位较大但有效内容集中。优先改成更合适的信息结构："
                "洞察卡 + 小表、横向时间轴、heatmap，或扩大正文行高/字号；不要只移动单个坐标。"
            ),
        },
    )


# ── Issue builders ──────────────────────────────────────────────

def issue(severity, code, message, target=None, detail=None, diagnosis=None, recommended_fix=None):
    i = {"severity": severity, "code": code, "message": message}
    if target:
        i["target"] = target
    if detail:
        i["detail"] = detail
    if diagnosis:
        i["diagnosis"] = diagnosis
    if recommended_fix:
        i["recommended_fix"] = recommended_fix
    return i


# ── Single-file validator ───────────────────────────────────────

def validate_file(path, margin=MARGIN, palette_tokens=None):
    if palette_tokens is None:
        palette_tokens = WESDOM_TOKENS

    content = path.read_text(encoding="utf-8-sig")
    root = ET.fromstring(content)
    parent_map = build_parent_map(root)

    errors, warnings, infos = [], [], []
    E = lambda code, msg, target=None, detail=None, diagnosis=None, recommended_fix=None: errors.append(issue("error", code, msg, target, detail, diagnosis, recommended_fix))
    W = lambda code, msg, target=None, detail=None, diagnosis=None, recommended_fix=None: warnings.append(issue("warning", code, msg, target, detail, diagnosis, recommended_fix))
    I = lambda code, msg, target=None, detail=None, diagnosis=None, recommended_fix=None: infos.append(issue("info", code, msg, target, detail, diagnosis, recommended_fix))

    # ── Canvas contract (P0) ──
    if root.get("width") != "1920" or root.get("height") != "1080":
        E("INVALID_CANVAS_SIZE", "SVG root must use width=\"1920\" and height=\"1080\"", target="svg_root")
    if root.get("viewBox") != "0 0 1920 1080":
        E("INVALID_VIEWBOX", "SVG root must use viewBox=\"0 0 1920 1080\"", target="svg_root")

    # ── SVG compatibility (P0) ──
    for el_name in PROHIBITED_ELEMENTS:
        pattern = f"<{el_name}"
        if pattern.lower() in content.lower():
            E(f"PROHIBITED_{el_name.upper()}", f"SVG uses <{el_name}> — unsupported in PPT conversion", target="svg_structure")

    for attr in PROHIBITED_ATTRIBUTES:
        if attr.lower() in content.lower():
            E(f"PROHIBITED_{attr.replace('-','_').upper()}", f"SVG uses {attr} — unsupported in PPT conversion", target="svg_structure")

    for tf in PROHIBITED_TRANSFORMS:
        if tf.lower() in content.lower():
            E(f"PROHIBITED_TRANSFORM", f"SVG uses transform with {tf} — unsupported in PPT conversion", target="svg_structure")

    # tspan line-break (multiple tspans with different dy or x)
    tspan_count = len(re.findall(r"<tspan\b", content, re.I))
    if tspan_count > 0:
        # flag only if tspans look like line-breaks (have dy or varying x)
        tspans = re.findall(r"<tspan\b[^>]*>", content, re.I)
        dy_count = sum(1 for t in tspans if "dy=" in t.lower())
        if dy_count > 0:
            E("TSPAN_LINEBREAK", f"SVG uses <tspan> with dy for line breaks — causes PPT parse errors; use separate <text> elements instead", target="svg_structure")

    # ── Text checks (P0/P1) ──
    text_nodes = root.findall(".//{http://www.w3.org/2000/svg}text")
    if not text_nodes:
        text_nodes = root.findall(".//text")
    rect_nodes_find = root.findall(".//{http://www.w3.org/2000/svg}rect")
    if not rect_nodes_find:
        rect_nodes_find = root.findall(".//rect")
    rect_boxes = [
        (ridx, rect_box(rnode, parent_map))
        for ridx, rnode in enumerate(rect_nodes_find, 1)
    ]

    font_families = []
    font_sizes = []
    for idx, node in enumerate(text_nodes, 1):
        tid = f"text_{idx}"
        has_fill = node.get("fill") is not None
        has_family = node.get("font-family") is not None
        content_text = "".join(node.itertext()).strip()[:40]

        if not has_fill:
            E("MISSING_FILL", f"<text> missing explicit fill: '{content_text}...'", target=tid)

        if not has_family:
            W("MISSING_FONT_FAMILY", f"<text> missing explicit font-family: '{content_text}...'", target=tid)
        else:
            ff = node.get("font-family").strip()
            font_families.append(ff)

        fw = node.get("font-weight", "").strip()
        if fw and fw not in VALID_FONT_WEIGHTS:
            E("INVALID_FONT_WEIGHT", f"font-weight '{fw}' is not a valid value", target=tid)

        fs = parse_float(node.get("font-size"), 0)
        if fs > 0:
            font_sizes.append(fs)

        # Check body text minimum
        if fs > 0 and fs < MIN_BODY_FONT:
            W(
                "FONT_TOO_SMALL",
                f"font-size {fs:.0f}px below {MIN_BODY_FONT:.0f}px minimum (≈10pt PPT)",
                target=tid,
                diagnosis={"font_size": round(fs, 1), "minimum_font_size": MIN_BODY_FONT, "text": content_text},
                recommended_fix={
                    "type": "increase_font_or_reduce_content",
                    "action": "不要继续用小字号硬塞；优先把正文恢复到 20px 以上，再通过拆行、扩大容器或减少上屏文字解决空间问题。",
                },
            )

        anchor = node.get("text-anchor", "")
        full_text = text_content(node)
        if anchor == "middle" and visual_length(full_text) > 12:
            W(
                "TEXT_ANCHOR_MIDDLE_LONG",
                "text-anchor=\"middle\" used on long text; PPT text width estimation may shift horizontally",
                target=tid,
                diagnosis={"visual_length": round(visual_length(full_text), 1), "text": full_text[:80]},
                recommended_fix={
                    "type": "left_align_long_text",
                    "action": "长文本改为 text-anchor=\"start\"，用明确 x 坐标左对齐；只有短标题、短数字适合居中锚点。",
                },
            )

        # Check overflow against container rects
        tbox = estimate_text_box(node, parent_map)
        if tbox[2] > 0:
            container = choose_text_container(tbox, rect_boxes)
            if container:
                ridx, rbox = container
                tx, ty, tw, th = tbox
                rx, ry, rw, rh = rbox
                pad_x, pad_y = 24, 20
                inside = (
                    tx >= rx + pad_x and ty >= ry + pad_y
                    and tx + tw <= rx + rw - pad_x
                    and ty + th <= ry + rh - pad_y
                )
                if not inside:
                    diagnosis, recommended_fix = text_overflow_guidance(tbox, rbox, fs or 24.0, full_text)
                    severity, code, message, risk = classify_text_fit_issue(diagnosis, fs or 24.0)
                    diagnosis["risk"] = risk
                    if risk == "major":
                        recommended_fix["priority"] = "fix_before_review"
                    elif risk == "review":
                        recommended_fix["priority"] = "review_or_fix_once"
                        recommended_fix["action"] = (
                            "这是容器贴边风险，不是硬错误。若页面肉眼拥挤，优先拆行、扩容器或减少上屏文字；"
                            "若预览可接受，可进入人工审阅。"
                        )
                    else:
                        recommended_fix["priority"] = "do_not_chase_pixels"
                        recommended_fix["action"] = (
                            "轻微 baseline/估算偏差；不要为了 1-6px 反复微调。"
                            "请在 PNG 预览中确认是否真的可见。"
                        )
                    emit = W if severity == "warning" else I
                    emit(
                        code,
                        f"{message} (rect_{ridx})",
                        target=tid,
                        detail=box_to_dict(tbox),
                        diagnosis=diagnosis,
                        recommended_fix=recommended_fix,
                    )

    # Font family consistency
    unique_ff = list(dict.fromkeys([f.split(",")[0].strip().strip('"\'') for f in font_families]))
    if len(unique_ff) > 1:
        W("FONT_FAMILY_DRIFT", f"Multiple font families on one page: {unique_ff}", target="typography")

    # Font size tiers
    unique_sizes = sorted(set(round(s) for s in font_sizes))
    if len(unique_sizes) > MAX_FONT_SIZE_TIERS:
        W("FONT_SIZE_TIERS", f"{len(unique_sizes)} distinct font sizes (max {MAX_FONT_SIZE_TIERS} recommended): {unique_sizes}", target="typography")

    # ── Palette checks (P1) ──
    all_fills = set()
    all_strokes = set()
    for node in root.iter():
        f = node.get("fill")
        if f:
            c = parse_color(f)
            if c:
                all_fills.add(c)
        s = node.get("stroke")
        if s:
            c = parse_color(s)
            if c:
                all_strokes.add(s.upper().strip())
    # Re-parse strokes with same function
    all_strokes.clear()
    for node in root.iter():
        s = node.get("stroke")
        if s:
            c = parse_color(s)
            if c:
                all_strokes.add(c)

    non_palette_fills = all_fills - palette_tokens
    non_palette_strokes = all_strokes - palette_tokens
    palette_drift = non_palette_fills | non_palette_strokes
    if palette_drift:
        W("PALETTE_DRIFT", f"Colors outside Wesdom palette: {sorted(palette_drift)}", target="palette")

    # ── Structure metadata (P1) ──
    meta = extract_metadata_comment(content)
    if meta:
        if "page_key" not in meta:
            E("MISSING_PAGE_KEY", "Metadata missing page_key", target="svg_metadata")
        if "data-layout" not in meta:
            E("MISSING_LAYOUT_ID", "Metadata missing data-layout", target="svg_metadata")
        else:
            lid = meta["data-layout"]
            if lid not in REGISTERED_LAYOUTS:
                I("UNKNOWN_LAYOUT_ID", f"Layout id '{lid}' not in L01-L15 reference library — model may have adapted a layout", target="svg_metadata")
        if "page_mode" not in meta:
            E("MISSING_PAGE_MODE", "Metadata missing page_mode", target="svg_metadata")
        elif meta["page_mode"] not in ("rational", "emotional"):
            E("INVALID_PAGE_MODE", f"Metadata page_mode must be rational or emotional, got {meta['page_mode']!r}", target="svg_metadata")
        if "visual_density" not in meta:
            E("MISSING_VISUAL_DENSITY", "Metadata missing visual_density", target="svg_metadata")
        elif meta["visual_density"] not in ("dense", "balanced", "airy"):
            E("INVALID_VISUAL_DENSITY", f"Metadata visual_density must be dense, balanced, or airy, got {meta['visual_density']!r}", target="svg_metadata")
        if "reason" not in meta:
            E("MISSING_LAYOUT_REASON", "Metadata missing reason", target="svg_metadata")

    # ── Image checks (P1) ──
    image_nodes = root.findall(".//{http://www.w3.org/2000/svg}image")
    if not image_nodes:
        image_nodes = root.findall(".//image")
    for idx, img in enumerate(image_nodes, 1):
        iid = f"image_{idx}"
        slot = img.get("data-slot", "")
        if not slot:
            W("MISSING_IMAGE_SLOT", f"<image> missing data-slot binding", target=iid)
        ibox = image_box(img, parent_map)
        w, h = ibox[2], ibox[3]
        if w > 0 and h > 0:
            if not ratio_near_approved(w, h):
                actual = round(w / h, 2)
                W("NONSTANDARD_IMAGE_RATIO", f"Image aspect ratio {actual}:1 not in approved list (16:9, 16:10, 4:3, 3:2, 1:1, 3:4, 21:9)", target=iid)

    # ── Safe areas (P0/P1) ──
    for idx, node in enumerate(text_nodes, 1):
        tbox = estimate_text_box(node, parent_map)
        if tbox[2] <= 0:
            continue
        if outside_safe_margin(tbox, margin):
            diagnosis, recommended_fix = safe_margin_guidance(tbox, margin)
            E(
                "UNSAFE_MARGIN",
                f"Text outside {margin:.0f}px safe margin",
                target=f"text_{idx}",
                detail=box_to_dict(tbox),
                diagnosis=diagnosis,
                recommended_fix=recommended_fix,
            )
        if in_footer_zone(tbox):
            # Not an error if it looks like a footer element (small font, near bottom)
            fs = parse_float(node.get("font-size"), 24.0)
            if fs > 22 or tbox[1] < FOOTER_Y_START - 10:
                W("FOOTER_ZONE_INVASION", f"Body text entering footer zone (Y>{FOOTER_Y_START})", target=f"text_{idx}", detail=box_to_dict(tbox))

    # Circle size check (P0)
    circle_nodes = root.findall(".//{http://www.w3.org/2000/svg}circle")
    if not circle_nodes:
        circle_nodes = root.findall(".//circle")
    for idx, cnode in enumerate(circle_nodes, 1):
        r = parse_float(cnode.get("r"), 0)
        if 0 < r < MIN_CIRCLE_R:
            E("CIRCLE_TOO_SMALL", f"<circle r={r:.1f}> below {MIN_CIRCLE_R}px minimum — subpixel in PPT", target=f"circle_{idx}")

    # ── Text overlap detection (P0/P1) ──
    text_boxes = []
    for idx, node in enumerate(text_nodes, 1):
        tbox = estimate_text_box(node, parent_map)
        if tbox[2] > 0:
            text_boxes.append((f"text_{idx}", tbox, "".join(node.itertext())[:30]))
    for i in range(len(text_boxes)):
        for j in range(i + 1, len(text_boxes)):
            tid_a, box_a, txt_a = text_boxes[i]
            tid_b, box_b, txt_b = text_boxes[j]
            if intersects(box_a, box_b):
                # Check if it's just slight overlap (within tolerance)
                overlap_x = min(box_a[0] + box_a[2], box_b[0] + box_b[2]) - max(box_a[0], box_b[0])
                overlap_y = min(box_a[1] + box_a[3], box_b[1] + box_b[3]) - max(box_a[1], box_b[1])
                if overlap_x > 5 and overlap_y > 5:
                    # Significant overlap
                    diagnosis, recommended_fix = overlap_guidance(box_a, box_b, tid_a, tid_b)
                    E(
                        "TEXT_OVERLAP",
                        f"Text elements overlap: '{txt_a}...' and '{txt_b}...'",
                        target=tid_a,
                        detail=f"overlaps {tid_b} ({overlap_x:.0f}x{overlap_y:.0f}px)",
                        diagnosis=diagnosis,
                        recommended_fix=recommended_fix,
                    )
                elif overlap_x > 0 and overlap_y > 0:
                    diagnosis, recommended_fix = overlap_guidance(box_a, box_b, tid_a, tid_b)
                    W(
                        "TEXT_OVERLAP_SLIGHT",
                        f"Text elements slightly overlap: '{txt_a}...' and '{txt_b}...'",
                        target=tid_a,
                        diagnosis=diagnosis,
                        recommended_fix=recommended_fix,
                    )

    image_boxes = []
    for idx, img in enumerate(image_nodes, 1):
        ibox = image_box(img, parent_map)
        if ibox[2] > 0 and ibox[3] > 0:
            image_boxes.append((f"image_{idx}", ibox))
    for tid, tbox, txt in text_boxes:
        for iid, ibox in image_boxes:
            if intersects(tbox, ibox):
                ib = intersection_box(tbox, ibox)
                ratio = box_area(ib) / max(1.0, box_area(tbox))
                if ratio > 0.12:
                    diagnosis, recommended_fix = overlap_guidance(tbox, ibox, tid, iid)
                    recommended_fix["action"] = (
                        f"文本 {tid} 压到图片 {iid} 上；优先把文字移到图片外的专用文本区，"
                        "若必须叠字，应增加半透明底板并重新验证可读性。"
                    )
                    W(
                        "TEXT_IMAGE_OVERLAP",
                        f"Text may overlap image: '{txt}...' over {iid}",
                        target=tid,
                        diagnosis=diagnosis,
                        recommended_fix=recommended_fix,
                    )

    # ── Outside-canvas detection for all elements (P0) ──
    all_positioned = []  # collect rects, circles, images that are outside canvas
    for rect_node in (root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect")):
        rbox = rect_box(rect_node, parent_map)
        if rbox[2] > 0 and rbox[3] > 0:
            x, y, w, h = rbox
            if x + w > CANVAS_W + 5 or y + h > CANVAS_H + 5 or x < -5 or y < -5:
                diagnosis, recommended_fix = safe_margin_guidance(rbox, 0)
                E(
                    "ELEMENT_OUTSIDE_CANVAS",
                    f"<rect> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas {CANVAS_W:.0f}x{CANVAS_H:.0f}",
                    target="svg_structure",
                    detail=box_to_dict(rbox),
                    diagnosis=diagnosis,
                    recommended_fix=recommended_fix,
                )

    for img_node in (root.findall(".//{http://www.w3.org/2000/svg}image") or root.findall(".//image")):
        ibox = image_box(img_node, parent_map)
        if ibox[2] > 0 and ibox[3] > 0:
            x, y, w, h = ibox
            if x + w > CANVAS_W + 5 or y + h > CANVAS_H + 5 or x < -5 or y < -5:
                diagnosis, recommended_fix = safe_margin_guidance(ibox, 0)
                E(
                    "IMAGE_OUTSIDE_CANVAS",
                    f"<image> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas",
                    target="svg_structure",
                    detail=box_to_dict(ibox),
                    diagnosis=diagnosis,
                    recommended_fix=recommended_fix,
                )

    # ── Suspiciously tiny text (P0) ──
    for idx, node in enumerate(text_nodes, 1):
        fs = parse_float(node.get("font-size"), 0)
        if 0 < fs < 16:
            content_text = "".join(node.itertext()).strip()[:30]
            E(
                "TEXT_TOO_TINY",
                f"font-size {fs:.0f}px is below 16px minimum (≈8pt in PPT — unreadable): '{content_text}...'",
                target=f"text_{idx}",
                diagnosis={"font_size": round(fs, 1), "hard_minimum_font_size": 16, "text": content_text},
                recommended_fix={
                    "type": "restore_readability",
                    "action": "字号必须提高到 16px 以上；正文/说明文字建议 20px 以上。若空间不足，必须减少上屏文字或重排版式。",
                },
            )

    # ── Empty / near-empty slide (P0) ──
    visible_elements = (
        len(text_nodes) +
        len(root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect")) +
        len(root.findall(".//{http://www.w3.org/2000/svg}image") or root.findall(".//image")) +
        len(root.findall(".//{http://www.w3.org/2000/svg}circle") or root.findall(".//circle")) +
        len(root.findall(".//{http://www.w3.org/2000/svg}line") or root.findall(".//line")) +
        len(root.findall(".//{http://www.w3.org/2000/svg}path") or root.findall(".//path")) +
        len(root.findall(".//{http://www.w3.org/2000/svg}polygon") or root.findall(".//polygon"))
    )
    if visible_elements < 3:
        W("EMPTY_SLIDE", f"Page has only {visible_elements} visible element(s) — appears empty or near-empty", target="svg_structure")

    # ── Excessive content density (P1) ──
    if len(text_nodes) > 25:
        W(
            "HIGH_TEXT_DENSITY",
            f"Page has {len(text_nodes)} text elements — may be overcrowded",
            target="svg_structure",
            diagnosis={"text_element_count": len(text_nodes), "recommended_max_for_normal_pages": 25},
            recommended_fix={
                "type": "reduce_or_group_text",
                "action": "优先合并重复标签、删减解释性小字，或把一页拆成更清晰的两页；不要通过继续缩小字号解决。",
            },
        )
    # Estimate canvas coverage by rects
    total_rect_area = 0.0
    for rect_node in (root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect")):
        rbox = rect_box(rect_node, parent_map)
        if rbox[2] > 0 and rbox[3] > 0:
            if rbox[2] < CANVAS_W * 0.95 or rbox[3] < CANVAS_H * 0.95:  # skip full-canvas background
                total_rect_area += rbox[2] * rbox[3]
    canvas_area = CANVAS_W * CANVAS_H
    coverage = total_rect_area / canvas_area if canvas_area > 0 else 0
    if coverage > 0.80:
        W(
            "HIGH_CANVAS_COVERAGE",
            f"Rect elements cover {coverage:.0%} of canvas — may feel overcrowded",
            target="svg_structure",
            diagnosis={"rect_coverage_ratio": round(coverage, 3)},
            recommended_fix={
                "type": "restore_breathing_space",
                "action": "减少大面积卡片/底块数量或降低填充面积，保留明确留白；若是情绪页，考虑用单一主视觉而不是密集容器。",
            },
        )

    visible_layout_boxes = [(tid, box) for tid, box, _ in text_boxes]
    visible_layout_boxes.extend(image_boxes)
    for ridx, rbox in rect_boxes:
        if rbox[2] > 0 and rbox[3] > 0 and not is_full_canvas_rect(rbox):
            visible_layout_boxes.append((f"rect_{ridx}", rbox))
    if len(visible_layout_boxes) >= 6:
        density = element_density_guidance(visible_layout_boxes)
        left, right = density["left"], density["right"]
        top, bottom = density["top"], density["bottom"]
        lr_min = max(min(left, right), 0.01)
        tb_min = max(min(top, bottom), 0.01)
        if max(left, right) > 0.12 and max(left, right) / lr_min > 2.8:
            heavy_side = "left" if left > right else "right"
            W(
                "DENSITY_IMBALANCE_HORIZONTAL",
                f"Page visual density is heavily biased to the {heavy_side} side",
                target="svg_structure",
                diagnosis={"region_density": density, "heavy_side": heavy_side},
                recommended_fix={
                    "type": "rebalance_layout",
                    "action": "重新分配左右空间：扩大轻侧的标题/图片/留白角色，或把重侧内容拆组；不要只靠挪动单个元素解决。",
                },
            )
        if max(top, bottom) > 0.12 and max(top, bottom) / tb_min > 3.2:
            heavy_side = "top" if top > bottom else "bottom"
            W(
                "DENSITY_IMBALANCE_VERTICAL",
                f"Page visual density is heavily biased to the {heavy_side} half",
                target="svg_structure",
                diagnosis={"region_density": density, "heavy_side": heavy_side},
                recommended_fix={
                    "type": "rebalance_layout",
                    "action": "重新分配上下节奏：检查标题区、主体区和页脚区是否过度集中；必要时改变版式结构而不是微调坐标。",
                },
            )

        content_only_boxes = [
            box for label, box in visible_layout_boxes
            if not (label.startswith("rect_") and box[2] >= CANVAS_W * 0.9 and box[3] >= CANVAS_H * 0.9)
        ]
        empty_hint = large_empty_region_guidance(content_only_boxes)
        if empty_hint:
            diagnosis, recommended_fix = empty_hint
            W(
                "LARGE_EMPTY_REGION",
                f"Large low-utilization area detected in {diagnosis['region']} region",
                target="layout_quality",
                diagnosis=diagnosis,
                recommended_fix=recommended_fix,
            )

    for ridx, rbox in rect_boxes:
        if rbox[2] <= 0 or rbox[3] <= 0 or is_full_canvas_rect(rbox):
            continue
        text_inside = []
        for _, tbox, _ in text_boxes:
            tx, ty, tw, th = tbox
            if rect_contains_point(rbox, tx + tw / 2, ty + th / 2):
                text_inside.append(tbox)
        utilization_hint = low_module_utilization_guidance(rbox, text_inside)
        if utilization_hint:
            diagnosis, recommended_fix = utilization_hint
            W(
                "LOW_MODULE_UTILIZATION",
                f"Large module rect_{ridx} uses space inefficiently",
                target=f"rect_{ridx}",
                diagnosis=diagnosis,
                recommended_fix=recommended_fix,
            )
            if len(text_inside) >= 14:
                small_count = 0
                for node in text_nodes:
                    tbox = estimate_text_box(node, parent_map)
                    if rect_contains_point(rbox, tbox[0] + tbox[2] / 2, tbox[1] + tbox[3] / 2):
                        if parse_float(node.get("font-size"), 24.0) <= 20:
                            small_count += 1
                if small_count >= 8:
                    W(
                        "TABLE_READABILITY_RISK",
                        f"Large module rect_{ridx} looks like a dense small-text table",
                        target=f"rect_{ridx}",
                        diagnosis={
                            "module_box": box_to_dict(rbox),
                            "text_count_inside": len(text_inside),
                            "small_text_count": small_count,
                        },
                        recommended_fix={
                            "type": "turn_table_into_presentation_structure",
                            "action": (
                                "表格适合存放证据，但不一定适合上屏。优先提炼为关键月份洞察卡、"
                                "小型摘要表或 heatmap；完整明细可放入 speaker notes。"
                            ),
                        },
                    )

    # ── Metadata severity escalation (P0) ──
    if not meta:
        E("MISSING_METADATA", "SVG missing metadata comment (page_key, data-layout, page_mode, visual_density, reason) — required for all pages", target="svg_metadata")

    # ── Assemble ──
    all_issues = errors + warnings + infos
    e_count = len(errors)
    w_count = len(warnings)
    i_count = len(infos)

    if e_count > 0:
        status = "fail"
    elif w_count > 0:
        status = "warning"
    else:
        status = "pass"

    return {
        "file": str(path),
        "status": status,
        "summary": {"errors": e_count, "warnings": w_count, "infos": i_count},
        "issues": all_issues,
        "meta": meta,
    }


# ── Manifest consistency check ───────────────────────────────────

def check_manifest_consistency(reports, manifest_data):
    """Check that SVG metadata matches page_manifest.json expectations."""
    issues = []
    if not manifest_data:
        return issues

    manifest_pages = manifest_data.get("pages", [])
    # Build lookup: page_key → {svg_path, ...}
    manifest_by_key = {}
    for p in manifest_pages:
        pk = p.get("page_key")
        if pk:
            manifest_by_key[pk] = p

    for r in reports:
        meta = r.get("meta", {})
        svg_path = Path(r.get("file", ""))
        # Try to match by filename to page_key
        matched_key = None
        for pk, mp in manifest_by_key.items():
            expected_path = mp.get("svg_path", "")
            if expected_path and svg_path.name == Path(expected_path).name:
                matched_key = pk
                break
            # Also try matching by page_key in filename
            if pk in svg_path.stem:
                matched_key = pk
                break

        if matched_key:
            manifest_page = manifest_by_key[matched_key]
            if meta.get("page_key") and meta["page_key"] != matched_key:
                issues.append(issue(
                    "error",
                    "METADATA_PAGE_KEY_MISMATCH",
                    f"SVG metadata page_key '{meta['page_key']}' does not match manifest page '{matched_key}'",
                    target="svg_manifest",
                ))
            # Check that svg_path in manifest matches actual file
            expected_svg = manifest_page.get("svg_path", "")
            if expected_svg and svg_path.name != Path(expected_svg).name:
                issues.append(issue(
                    "warning",
                    "MANIFEST_PATH_MISMATCH",
                    f"SVG filename '{svg_path.name}' does not match manifest svg_path '{Path(expected_svg).name}' for {matched_key}",
                    target="svg_manifest"
                ))
        elif meta.get("page_key"):
            issues.append(issue(
                "error",
                "METADATA_PAGE_KEY_UNKNOWN",
                f"SVG metadata page_key '{meta['page_key']}' is not present in page_manifest.json",
                target="svg_manifest",
            ))

    return issues


# ── Multi-page rhythm check ──────────────────────────────────────

def check_rhythm(reports):
    """Check consecutive pages for same mode+density."""
    rhythm_issues = []
    for i in range(len(reports) - 2):
        m1 = reports[i].get("meta", {})
        m2 = reports[i + 1].get("meta", {})
        m3 = reports[i + 2].get("meta", {})
        combo1 = (m1.get("page_mode"), m1.get("visual_density"))
        combo2 = (m2.get("page_mode"), m2.get("visual_density"))
        combo3 = (m3.get("page_mode"), m3.get("visual_density"))
        if combo1 == combo2 == combo3 and combo1[0] and combo1[1]:
            rhythm_issues.append(issue(
                "warning",
                "REPEATED_LAYOUT_RHYTHM",
                f"Pages {i+1}-{i+3} have the same page_mode+visual_density ({combo1[0]}+{combo1[1]})",
                target=f"pages_{i+1}_{i+3}"
            ))
    return rhythm_issues


def get_batch_pages(manifest_data, batch_id):
    batch_config = manifest_data.get("batch_config", {})
    if not isinstance(batch_config, dict) or batch_id not in batch_config:
        raise SystemExit(f"batch '{batch_id}' not found in page_manifest.json")
    batch = batch_config[batch_id]
    if not isinstance(batch, dict) or not isinstance(batch.get("pages"), list):
        raise SystemExit(f"batch_config.{batch_id}.pages must be a list")
    return batch["pages"]


def select_svg_files(svg_path, manifest_data=None, batch_id=""):
    if svg_path.is_file() and svg_path.suffix.lower() == ".svg":
        return [svg_path]
    if not svg_path.is_dir():
        return []

    all_svg = sorted(svg_path.glob("*.svg"))
    if not manifest_data or not batch_id:
        return all_svg

    wanted_keys = set(get_batch_pages(manifest_data, batch_id))
    manifest_by_key = {
        p.get("page_key"): p
        for p in manifest_data.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }
    selected = []
    for pk in wanted_keys:
        mp = manifest_by_key.get(pk, {})
        svg_rel = mp.get("svg_path", "")
        if svg_rel:
            fp = Path(svg_rel)
            if not fp.is_absolute():
                fp = svg_path.parent.parent / svg_rel if svg_path.name == "02_svg_source" else Path(svg_rel)
            if fp.exists():
                selected.append(fp)
                continue
        fallback = svg_path / f"{pk}.svg"
        if fallback.exists():
            selected.append(fallback)
    return sorted(set(selected))


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Heuristic SVG layout validator v2.0 — compatibility, text, palette, metadata, images, safe areas, rhythm."
    )
    parser.add_argument("svg_dir", help="Directory containing SVG files")
    parser.add_argument("--margin", type=float, default=MARGIN, help=f"Safe margin in px (default: {MARGIN})")
    parser.add_argument("--output", default="", help="Output JSON path (default: stdout)")
    parser.add_argument("--config", default="", help="Optional JSON config: {\"palette\": [\"#...\"]} or {\"allowed_colors\": [\"#...\"]}")
    parser.add_argument("--manifest", default="", help="Optional path to page_manifest.json for cross-validation")
    parser.add_argument("--batch", default="", help="Optional batch_id from page_manifest.json; validates only that batch")
    args = parser.parse_args()

    svg_path = Path(args.svg_dir)
    manifest_data = None
    if args.manifest:
        try:
            manifest_data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        except Exception:
            pass
    svg_files = select_svg_files(svg_path, manifest_data, args.batch)
    if not svg_files:
        print(json.dumps({"status": "fail", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                          "reports": [{"file": str(svg_path), "status": "fail",
                                       "issues": [issue("error", "NO_SVG_FILES", "No SVG files found")]}]},
                         ensure_ascii=False, indent=2))
        return

    # Load config palette override
    custom_palette = None
    if args.config:
        try:
            cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
            colors = cfg.get("palette") or cfg.get("allowed_colors") or []
            custom_palette = {c.upper() for c in colors}
        except Exception:
            pass  # fall back to Wesdom

    # Validate each file
    reports = [validate_file(f, margin=args.margin, palette_tokens=custom_palette) for f in svg_files]

    # Multi-page rhythm
    rhythm_issues = check_rhythm(reports)
    if rhythm_issues:
        # Append rhythm issues to the last page's report
        reports[-1]["issues"].extend(rhythm_issues)
        reports[-1]["summary"]["warnings"] += len(rhythm_issues)
        if reports[-1]["status"] == "pass":
            reports[-1]["status"] = "warning"

    # Manifest consistency
    manifest_issues = check_manifest_consistency(reports, manifest_data)
    if manifest_issues:
        reports[-1]["issues"].extend(manifest_issues)
        reports[-1]["summary"]["warnings"] += len(
            [i for i in manifest_issues if i["severity"] == "warning"]
        )
        reports[-1]["summary"]["errors"] += len(
            [i for i in manifest_issues if i["severity"] == "error"]
        )
        if any(i["severity"] == "error" for i in manifest_issues):
            reports[-1]["status"] = "fail"
        elif reports[-1]["status"] == "pass":
            reports[-1]["status"] = "warning"

    # Aggregate
    total_errors = sum(r["summary"]["errors"] for r in reports)
    total_warnings = sum(r["summary"]["warnings"] for r in reports)
    total_infos = sum(r["summary"]["infos"] for r in reports)

    if total_errors > 0:
        agg_status = "fail"
    elif total_warnings > 0:
        agg_status = "warning"
    else:
        agg_status = "pass"

    summary = {
        "status": agg_status,
        "summary": {"errors": total_errors, "warnings": total_warnings, "infos": total_infos},
        "reports": reports,
    }

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
