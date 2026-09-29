#!/usr/bin/env python3
"""SVG checks that protect PPT conversion and catch real defects — not design taste.

Two exits, and this validator runs the half that fits the exit it is told about
(`--route`, or the route recorded in the project state):

**Both routes** — defects that are wrong on any page regardless of style: text
overlapping text, an element (rect, image, or **text**) leaving the canvas, an empty
page, `<text>` without an explicit fill, an illegal `font-weight`, images that are not
real local project files, and stretched bitmaps.

**Slides route only** — the constraints whose only reason to exist is "the converter
cannot handle it": prohibited elements/attributes, `rotate`/`skew`/`matrix`, `tspan`
line-break form, and the readability floor (it is derived from the 1px = 0.5pt slide
conversion). Plus the strict-template lock checks. The video exit renders to PNG, so
`<style>`, animation and visual effects are legitimate there, and its font sizes are
judged by looking at the rendered page.

Every skipped check is reported in `skipped_rules` with the reason. Nothing disappears
silently: this Skill's whole subject is failing loudly.

What was retired: the readability/density/composition heuristics
(font-size tiers, body-text floor at 20px, empty-region, module utilization,
canvas coverage, density imbalance, footer-zone, safe-margin, image-slot,
approved image ratios, the page_mode rhythm scan). They did not protect correctness;
they encoded one house style and pushed every deck toward sparse, uniform,
card-based pages — the opposite of a dense, designed proposal. Design judgement now
belongs to the model, which renders the page and looks at it.
"""
import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "template"))
from canvas_frame import FRAME_H, FRAME_H_INT, FRAME_VIEWBOX, FRAME_W, FRAME_W_INT  # noqa: E402
try:
    from layout_canvas import TEMPLATE_CANVAS_VERSION, locked_sha256  # noqa: E402
except ImportError:
    TEMPLATE_CANVAS_VERSION = "2"

    def locked_sha256(_path):
        raise ValueError("legacy layout_canvas module not present")

from native_svg_to_ppt import compose_axis_aligned, parse_axis_aligned_transform  # noqa: E402
from project_state import DEFAULT_ROUTE, ROUTES, project_root_of, route as project_route  # noqa: E402

TEXT_RE = re.compile(r"\s+")
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\u2B50\u23F0-\u23FA]"
)

CANVAS_W = FRAME_W
CANVAS_H = FRAME_H
MARGIN = 60.0
VALID_FONT_WEIGHTS = {"normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"}

# Reading mode drives the readability floor. 1 SVG px = 0.5 pt on a 13.333in slide,
# so 12px is 6pt (nothing is readable below this at any zoom) and 18px is 9pt.
MODE_FLOOR = {"讲": 18.0, "读": 12.0}
DEFAULT_MODE = "读"

# v6.0: <style>, :root var(--...), stroke-dasharray, and <tspan dy> are natively supported by native_svg_to_ppt.py!
PROHIBITED_ELEMENTS = ["foreignObject", "filter", "use", "marker", "mask", "animate"]
PROHIBITED_ATTRIBUTES = [
    "textLength", "lengthAdjust",
    "marker-start", "marker-mid", "marker-end",
]
PROHIBITED_TRANSFORMS = ["rotate(", "skew(", "skewX(", "skewY(", "matrix("]


# ── Which half runs on which route ────────────────────────────────

STABLE_ID_HINT = ("给可能被强调的元素一个稳定 id（名字要读得出它在画面里是什么，例如 caption、"
                  "label-tony-alva、model-stage），并把 page_key 放进名字里（beat-04-caption-1）——"
                  "各屏会被内联进同一个 DOM，id 要在全片唯一，然后重渲这一页。")

def skipped_rules_for_route(route):
    """这条路线不跑的那几组检查，以及每一条为什么被跳过。

    跳过也要写进输出：静默消失正是这个 Skill 要防的失败方式。
    两个出口各有一半不跑，所以两边都要说得出来。
    """
    if route == "video":
        return [
            {"rule": "TEXT_BELOW_READABILITY_FLOOR",
             "codes": ["TEXT_BELOW_READABILITY_FLOOR"],
             "why": "字号下限来自 1px=0.5pt 的幻灯片换算，是幻灯片语义；"
                    "视频画面的字号合不合适，看渲染图判断。"},
            {"rule": "PROHIBITED_ELEMENTS",
             "codes": [f"PROHIBITED_{name.upper()}" for name in PROHIBITED_ELEMENTS],
             "why": f"这一组唯一的原因是「转换器处理不了」（{', '.join(PROHIBITED_ELEMENTS)}）；"
                    "视频出口是 PNG，滤镜与动画都承载得住。"},
            {"rule": "PROHIBITED_ATTRIBUTES",
             "codes": [f"PROHIBITED_{attr.replace('-', '_').upper()}" for attr in PROHIBITED_ATTRIBUTES],
             "why": "这些属性同样只因转换器不支持而被禁；PNG 渲染不受影响。"},
            {"rule": "PROHIBITED_TRANSFORM",
             "codes": ["PROHIBITED_TRANSFORM"],
             "why": "rotate／skew／matrix 只在转 PPT 时不可靠；视频出口按页面自己的坐标渲染。"},
            {"rule": "SLIDE_LAYOUT_GUARDS",
             "codes": ["LINE_CROSSES_TEXT", "EMOJI_IN_SLIDE_TEXT", "TEXT_OVERFLOWS_CONTAINER"],
             "why": "这三道防线针对幻灯片排版与转 PPTX 溢出/Emoji 位图失真；视频出口按 PNG 画面审阅。"},
            {"rule": "FIDELITY_TEMPLATE",
             "codes": ["FIDELITY_*", "REQUIRED_FIDELITY_COMPONENT_MISSING", "UNKNOWN_FIDELITY_LAYOUT"],
             "why": "严格模板锁层属于模板库，只服务幻灯片出口；视频路线不套模板库。"},
        ]
    return [
        {"rule": "MISSING_ELEMENT_ID",
         "codes": ["MISSING_ELEMENT_ID"],
         "why": "元素 id 是视频出口的接口——动画层按元素指名，不用 DOM 序号。"
                "幻灯片出口的消费者是 PPTX，不靠 id，所以这条检查不在这条路上跑。"},
        {"rule": "DUPLICATE_ELEMENT_ID",
         "codes": ["DUPLICATE_ELEMENT_ID"],
         "why": "页内 id 唯一同样是视频出口的接口要求（各屏会被内联进同一个 DOM）。"
                "幻灯片出口不按 id 指名，所以这条检查不在这条路上跑。"},
    ]


def _element_ids(root, include_root):
    return [node.get("id").strip() for node in root.iter()
            if (include_root or node is not root) and node.get("id") and node.get("id").strip()]


def element_ids_below_svg(root):
    """`<svg>` 之下每个元素自己的 `id`——回答「有没有可指名的元素」。"""
    return _element_ids(root, include_root=False)


def document_ids(root):
    """整份 SVG 里所有元素的 `id`，**含根 `<svg>`**——回答「这份 id 合法且不歧义吗」。"""
    return _element_ids(root, include_root=True)


def duplicated_ids(ids):
    """出现过一次以上的 id：[(名字, 次数)]，按名字排序。"""
    counts = {}
    for name in ids:
        counts[name] = counts.get(name, 0) + 1
    return sorted((name, count) for name, count in counts.items() if count > 1)


def resolve_route(explicit, path):
    """这条路线是哪一个，以及是从哪读到的（把来源说出来，别让它成为一个暗默认）。"""
    if explicit in ROUTES:
        return explicit, f"--route {explicit}"
    root = project_root_of(path)
    if root is None:
        return DEFAULT_ROUTE, "默认：这个路径不在任何 ppt-hell 项目里（项目状态里没有路线记录）"
    return project_route(root), f"项目状态：{root}/_internal/00_project/page_manifest.json"


# ── Helpers ──────────────────────────────────────────────────────

def parse_float(value, default=0.0):
    if value is None:
        return default
    m = re.search(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?", str(value))
    return float(m.group(0)) if m else default


def parse_color(value):
    if not value or value == "none":
        return None
    v = value.strip().upper()
    if v.startswith("URL("):
        return None
    return v


def get_accumulated_transform(node, parent_map):
    """A node's absolute translate/scale, using 转换 PPT's own coordinate model.
    v6.0: Includes both ancestor <g> transforms AND the leaf node's own transform.
    """
    chain = [node]
    current = node
    while current in parent_map:
        current = parent_map[current]
        chain.append(current)
    chain.reverse()
    accumulated = (0.0, 0.0, 1.0, 1.0)
    for item in chain:
        accumulated = compose_axis_aligned(
            accumulated, parse_axis_aligned_transform(item.get("transform", "")))
    return accumulated


def build_parent_map(root):
    pm = {}
    for parent in root.iter():
        for child in parent:
            pm[child] = parent
    return pm


def is_in_non_rendering_container(node, parent_map):
    """Return True if node is inside <defs>, <clipPath>, <mask>, <pattern>, or <symbol>."""
    cur = parent_map.get(node)
    while cur is not None:
        tag = cur.tag.split("}")[-1] if "}" in cur.tag else cur.tag
        if tag in ("defs", "clipPath", "mask", "pattern", "symbol"):
            return True
        cur = parent_map.get(cur)
    return False


# ── 同一份 SVG 里内联的 <style> ─────────────────────────────────
# 视频出口的画法是把主题的 `:root` token 块与 class 规则内联进每一页（见 03_video_route.md），
# 元素用 `class` + `var(--…)` 取值。所以「一个 <text> 有没有填色/字体」要连样式表一起看。

XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
STYLE_ELEMENT_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_DECLARATION_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,\s*([^()]*))?\)")
# 只认由 class 组成的选择器：`.a`、`.a.b`、`.a, .b`、`.card .title`。
# 带元素名、伪类、属性选择器或 > + ~ 的一律不算数——宁可让人写显式属性，
# 也不要把「没取到值」误判成「取到了」。
CLASS_COMPOUND_RE = re.compile(r"^(?:\.[A-Za-z_][-\w]*)+$")


def css_declarations(text):
    declarations = {}
    for piece in str(text or "").split(";"):
        if ":" not in piece:
            continue
        prop, value = piece.split(":", 1)
        prop = prop.strip()
        if not prop.startswith("--"):
            prop = prop.lower()
        value = value.strip()
        if prop and value:
            declarations[prop] = value
    return declarations


def class_list(node):
    return set((node.get("class") or "").split())


def selector_matches(node, parent_map, compounds):
    """后代选择器从右往左匹配：最后一个 compound 必须是元素自己，其余必须是祖先。"""
    current = node
    for index, classes in enumerate(reversed(compounds)):
        if index == 0:
            if not set(classes) <= class_list(current):
                return False
        else:
            while current is not None and not set(classes) <= class_list(current):
                current = parent_map.get(current)
            if current is None:
                return False
        current = parent_map.get(current)
    return True


def parse_stylesheet(content):
    """同一份 SVG 内联 `<style>` 的规则与自定义属性。

    返回 (规则, 自定义属性)：规则是 [(选择器列表, 声明)]；自定义属性是整份样式表里
    见过的 `--x: 值`（任何选择器上写的都算，token 通常写在 `:root` 上）。
    注释先去掉；`<style>` 在 XML 注释里的内容不算。
    """
    rules, custom = [], {}
    for block in STYLE_ELEMENT_RE.findall(XML_COMMENT_RE.sub("", content)):
        for match in CSS_RULE_RE.finditer(CSS_COMMENT_RE.sub("", block)):
            declarations = css_declarations(match.group(2))
            if not declarations:
                continue
            for name, value in declarations.items():
                if name.startswith("--"):
                    custom[name] = value
            selectors = []
            for part in match.group(1).split(","):
                compounds = part.split()
                if compounds and all(CLASS_COMPOUND_RE.match(item) for item in compounds):
                    selectors.append([item[1:].split(".") for item in compounds])
            if selectors:
                rules.append((selectors, declarations))
    return rules, custom


def element_custom_properties(root):
    """元素 `style=""` 上写的自定义属性（顶层也可以这样声明 token）。"""
    custom = {}
    for node in root.iter():
        for name, value in css_declarations(node.get("style")).items():
            if name.startswith("--"):
                custom[name] = value
    return custom


def stylesheet_value(node, parent_map, rules, prop):
    """class 命中的规则里这个属性的值；后面的规则覆盖前面的（同一份 <style> 的顺序）。"""
    found = None
    for selectors, declarations in rules:
        if prop not in declarations:
            continue
        if any(selector_matches(node, parent_map, compounds) for compounds in selectors):
            found = declarations[prop]
    return found


def text_style_value(node, parent_map, rules, prop):
    """一个文字属性最终取到的值：元素属性 > 元素 style > class 命中的样式表规则 > 祖先 <g> 继承。"""
    if node.get(prop) is not None:
        return node.get(prop)
    inline = css_declarations(node.get("style"))
    if prop in inline:
        return inline[prop]
    val = stylesheet_value(node, parent_map, rules, prop)
    if val is not None:
        return val
    cur = parent_map.get(node)
    while cur is not None:
        if cur.get(prop) is not None:
            return cur.get(prop)
        c_inline = css_declarations(cur.get("style"))
        if prop in c_inline:
            return c_inline[prop]
        cur = parent_map.get(cur)
    return None


def text_style_source(node, parent_map, rules, prop):
    if node.get(prop) is not None:
        return f"元素属性 {prop}=\"{node.get(prop)}\""
    inline = css_declarations(node.get("style"))
    if prop in inline:
        return f'元素 style 上的 {prop}: {inline[prop]}'
    value = stylesheet_value(node, parent_map, rules, prop)
    if value is not None:
        return "class 命中的 <style> 规则"
    cur = parent_map.get(node)
    while cur is not None:
        if cur.get(prop) is not None or prop in css_declarations(cur.get("style")):
            return "祖先 <g> 继承属性"
        cur = parent_map.get(cur)
    return "四处都没有"


def undefined_css_vars(value, custom_properties):
    """值里引用了、但同一份 SVG 没定义的 token。返回 [(token, 回退值或 None)]。"""
    if not value or "var(" not in str(value):
        return []
    return [(token, fallback) for token, fallback in CSS_DECLARATION_RE.findall(str(value))
            if token not in custom_properties]


def estimate_text_width(content, font_size):
    w = 0.0
    for ch in content:
        w += font_size * (0.56 if ord(ch) < 128 else 0.92)
    return w


def estimate_text_box(node, parent_map, rules=None):
    """Estimated ink box. Honors text-anchor, <tspan dy> multi-line height/width,
    <tspan font-size>, and letter-spacing."""
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    scale_f = min(sx, sy)
    x = dx + parse_float(node.get("x")) * sx
    y = dy + parse_float(node.get("y")) * sy

    raw_fs = text_style_value(node, parent_map, rules or [], "font-size")
    base_fs = parse_float(raw_fs, 24.0) * scale_f
    base_ls = parse_float(text_style_value(node, parent_map, rules or [], "letter-spacing"), 0.0) * scale_f

    # Split into logical lines when child <tspan> has non-zero dy
    lines = [{"dy": 0.0, "w": 0.0, "max_fs": base_fs}]
    if node.text and node.text.strip():
        txt = TEXT_RE.sub(" ", node.text.strip())
        lines[-1]["w"] += estimate_text_width(txt, base_fs) + max(0.0, base_ls) * len(txt)

    for child in node:
        ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if ctag == "tspan":
            cfs = parse_float(child.get("font-size"), base_fs / scale_f if scale_f else 24.0) * scale_f
            cls_val = parse_float(child.get("letter-spacing"), base_ls / scale_f if scale_f else 0.0) * scale_f
            cdy_str = child.get("dy")
            cdy = 0.0
            if cdy_str:
                if str(cdy_str).strip().lower().endswith("em"):
                    cdy = parse_float(cdy_str, 0.0) * cfs
                else:
                    cdy = parse_float(cdy_str, 0.0) * sy
            if abs(cdy) > 1e-3:
                if lines[-1]["w"] > 0:
                    lines.append({"dy": cdy, "w": 0.0, "max_fs": cfs})
                else:
                    y += cdy
            if child.text and child.text.strip():
                ctxt = TEXT_RE.sub(" ", child.text.strip())
                lines[-1]["w"] += estimate_text_width(ctxt, cfs) + max(0.0, cls_val) * len(ctxt)
                lines[-1]["max_fs"] = max(lines[-1]["max_fs"], cfs)
        if child.tail and child.tail.strip():
            ttxt = TEXT_RE.sub(" ", child.tail.strip())
            lines[-1]["w"] += estimate_text_width(ttxt, base_fs) + max(0.0, base_ls) * len(ttxt)

    non_empty_lines = [ln for ln in lines if ln["w"] > 0]
    if not non_empty_lines:
        return (x, y - base_fs, 0.0, base_fs * 1.18)

    w = max(ln["w"] for ln in non_empty_lines)
    total_dy = sum(max(0.0, ln["dy"]) for ln in non_empty_lines[1:])
    first_fs = non_empty_lines[0]["max_fs"]
    if total_dy > 0:
        h = first_fs * 1.55 + total_dy
    else:
        h = first_fs * 1.18

    anchor = (text_style_value(node, parent_map, rules or [], "text-anchor") or "start").strip()
    if anchor == "middle":
        x -= w / 2.0
    elif anchor == "end":
        x -= w
    return (x, y - first_fs, w, h)


def rect_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        dx + parse_float(node.get("x")) * sx,
        dy + parse_float(node.get("y")) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def image_box(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        dx + parse_float(node.get("x")) * sx,
        dy + parse_float(node.get("y")) * sy,
        parse_float(node.get("width")) * sx,
        parse_float(node.get("height")) * sy,
    )


def line_coords(node, parent_map):
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    return (
        dx + parse_float(node.get("x1")) * sx,
        dy + parse_float(node.get("y1")) * sy,
        dx + parse_float(node.get("x2")) * sx,
        dy + parse_float(node.get("y2")) * sy,
    )


def outside_canvas(box, tolerance=5.0):
    """同一套画布容差，rect／image／text 共用一份，免得三条检查各说一套话。"""
    x, y, w, h = box
    return (x + w > CANVAS_W + tolerance or y + h > CANVAS_H + tolerance
            or x < -tolerance or y < -tolerance)


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and by < ay + ah and by + bh > ay


def outside_safe_margin(box, margin=MARGIN):
    x, y, w, h = box
    return x < margin or y < margin or x + w > CANVAS_W - margin or y + h > CANVAS_H - margin


def box_to_dict(box):
    return {"x": round(box[0], 1), "y": round(box[1], 1), "w": round(box[2], 1), "h": round(box[3], 1)}


def text_content(node):
    return TEXT_RE.sub(" ", "".join(node.itertext())).strip()


def is_full_canvas_rect(box):
    x, y, w, h = box
    return x <= 5 and y <= 5 and w >= CANVAS_W * 0.95 and h >= CANVAS_H * 0.95


def issue(severity, code, message, target=None, detail=None, hint=None):
    i = {"severity": severity, "code": code, "message": message}
    if target:
        i["target"] = target
    if detail:
        i["detail"] = detail
    if hint:
        i["hint"] = hint
    return i


# ── Fidelity template component checks (only in the strict-template branch) ──

def fidelity_component_node_errors(component, node):
    """Validate a v2 fidelity instance beyond the presence of its ID."""
    errors = []
    geometry = component.get("geometry", {})
    preset = component.get("shape", {}).get("preset")
    expected_tag = "image" if component.get("source_kind") == "asset" else {
        "roundRect": "rect", "rect": "rect", "ellipse": "ellipse", "line": "line",
    }.get(preset, "rect")
    actual_tag = node.tag.rsplit("}", 1)[-1]
    component_id = component.get("component_id", "")
    if actual_tag != expected_tag:
        return [("FIDELITY_COMPONENT_TYPE_MISMATCH",
                 f"Template component {component_id} must be <{expected_tag}>, got <{actual_tag}>")]

    if expected_tag in {"rect", "image"}:
        actual_geometry = {key: parse_float(node.get(key)) for key in ("x", "y", "width", "height")}
        expected_geometry = {key: float(geometry.get(key, 0)) for key in actual_geometry}
        positive = actual_geometry["width"] > 0 and actual_geometry["height"] > 0
    elif expected_tag == "ellipse":
        actual_geometry = {key: parse_float(node.get(key)) for key in ("cx", "cy", "rx", "ry")}
        expected_geometry = {
            "cx": float(geometry.get("x", 0)) + float(geometry.get("width", 0)) / 2,
            "cy": float(geometry.get("y", 0)) + float(geometry.get("height", 0)) / 2,
            "rx": float(geometry.get("width", 0)) / 2,
            "ry": float(geometry.get("height", 0)) / 2,
        }
        positive = actual_geometry["rx"] > 0 and actual_geometry["ry"] > 0
    else:
        actual_geometry = {key: parse_float(node.get(key)) for key in ("x1", "y1", "x2", "y2")}
        expected_geometry = {
            "x1": float(geometry.get("x", 0)), "y1": float(geometry.get("y", 0)),
            "x2": float(geometry.get("x", 0)) + float(geometry.get("width", 0)),
            "y2": float(geometry.get("y", 0)) + float(geometry.get("height", 0)),
        }
        positive = math.hypot(actual_geometry["x2"] - actual_geometry["x1"],
                              actual_geometry["y2"] - actual_geometry["y1"]) > 0
    if not positive:
        errors.append(("FIDELITY_COMPONENT_EMPTY", f"Template component {component_id} has zero visual geometry"))
    if component.get("geometry_policy", "fixed") == "fixed":
        mismatched = [key for key in expected_geometry if abs(actual_geometry[key] - expected_geometry[key]) > 3.0]
        if mismatched:
            errors.append(("FIDELITY_COMPONENT_GEOMETRY_MISMATCH",
                           f"Template component {component_id} changed fixed geometry: {', '.join(mismatched)}"))

    if expected_tag != "image":
        style = component.get("style", {})
        keys = ("stroke", "stroke_width") if expected_tag == "line" else ("fill", "stroke", "stroke_width")
        for key in keys:
            if key == "stroke_width":
                expected_width = float(style.get(key) or 0)
                if expected_width and abs(parse_float(node.get("stroke-width")) - expected_width) > 1.0:
                    errors.append(("FIDELITY_COMPONENT_STYLE_MISMATCH",
                                   f"Template component {component_id} changed stroke-width"))
                continue
            expected = parse_color(style.get(key))
            if expected and parse_color(node.get(key)) != expected:
                errors.append(("FIDELITY_COMPONENT_STYLE_MISMATCH",
                               f"Template component {component_id} changed {key}: expected {expected}"))
    return errors


# ── Per-file validation ──────────────────────────────────────────

def validate_file(path, page_mode=DEFAULT_MODE, margin=MARGIN, quick_mode=False, route=DEFAULT_ROUTE):
    content = Path(path).read_text(encoding="utf-8-sig")
    uncommented = XML_COMMENT_RE.sub("", content)
    root = ET.fromstring(content)
    parent_map = build_parent_map(root)

    errors, warnings, infos = [], [], []
    E = lambda code, msg, **kw: errors.append(issue("error", code, msg, **kw))
    W = lambda code, msg, **kw: warnings.append(issue("warning", code, msg, **kw))
    I = lambda code, msg, **kw: infos.append(issue("info", code, msg, **kw))
    slides = route != "video"
    skipped = skipped_rules_for_route(route)

    # ── Canvas contract（取值来自画幅 owner canvas_frame，不自己写数字） ──
    if root.get("width") != str(FRAME_W_INT) or root.get("height") != str(FRAME_H_INT):
        E("INVALID_CANVAS_SIZE",
          f'SVG root must use width="{FRAME_W_INT}" and height="{FRAME_H_INT}"', target="svg_root")
    if root.get("viewBox") != FRAME_VIEWBOX:
        E("INVALID_VIEWBOX", f'SVG root must use viewBox="{FRAME_VIEWBOX}"', target="svg_root")

    # ── SVG → PPT compatibility (slides route only) ──
    if slides:
        seen_els = {n.tag.split("}")[-1].lower() for n in root.iter()}
        for el_name in PROHIBITED_ELEMENTS:
            if el_name.lower() in seen_els or f"<{el_name}".lower() in uncommented.lower():
                E(f"PROHIBITED_{el_name.upper()}", f"SVG uses <{el_name}> — unsupported in PPT conversion",
                  target="svg_structure")
        seen_attrs = {k.split("}")[-1].lower() for n in root.iter() for k in n.attrib}
        for attr in PROHIBITED_ATTRIBUTES:
            if attr.lower() in seen_attrs:
                E(f"PROHIBITED_{attr.replace('-', '_').upper()}",
                  f"SVG uses {attr} — unsupported in PPT conversion", target="svg_structure")
        all_transforms = " ".join((n.get("transform") or "") for n in root.iter()).lower()
        for tf in PROHIBITED_TRANSFORMS:
            if tf.lower() in all_transforms:
                E("PROHIBITED_TRANSFORM", f"SVG uses transform with {tf} — unsupported in PPT conversion",
                  target="svg_structure")
                break

    # ── Images must be real local project files, never stretched (both routes) ──
    image_nodes = [
        n for n in (list(root.findall(".//{http://www.w3.org/2000/svg}image")) or list(root.findall(".//image")))
        if not is_in_non_rendering_container(n, parent_map)
    ]
    for idx, node in enumerate(image_nodes, 1):
        href = (node.get("href") or node.get("{http://www.w3.org/1999/xlink}href") or "").strip()
        if not href or href.startswith(("data:", "http://", "https://", "#")):
            continue
        if Path(href).is_absolute():
            E("ABSOLUTE_IMAGE_PATH", f"Image href must be portable and relative: {href}", target=f"image_{idx}")
        elif not (Path(path).parent / href).resolve().is_file():
            E("MISSING_IMAGE_FILE", f"Image href does not resolve from the SVG: {href}", target=f"image_{idx}")
        preserve = (node.get("preserveAspectRatio") or "xMidYMid meet").strip()
        if preserve == "none" or not re.search(r"\b(meet|slice)\b", preserve):
            E("IMAGE_ASPECT_DISTORTION",
              "Image must use preserveAspectRatio with meet or slice; 'none' stretches the bitmap",
              target=f"image_{idx}")

    # ── 元素必须可被指名、且指得准（视频出口独有） ──
    if not slides:
        ids = element_ids_below_svg(root)
        if not ids:
            E("MISSING_ELEMENT_ID",
              "这一页在 <svg> 之下没有任何元素 id——动画层没有东西可以指名 "
              "(no element id below <svg>)",
              target="svg_structure",
              hint=STABLE_ID_HINT)
        duplicates = duplicated_ids(document_ids(root))
        if duplicates:
            page_key = Path(path).stem
            E("DUPLICATE_ELEMENT_ID",
              "这一页里有重复的 id：" + "、".join(f"{name}（{count} 次）" for name, count in duplicates)
              + "。同一份 SVG 里 id 必须唯一——重复的 id 是非法 HTML，各屏又会被内联进同一个 DOM，"
                "按 id 指名只会命中第一个。",
              target="svg_structure",
              detail="重复的是这份 SVG 里的元素 id（含根 <svg> 自己的 id；data-*-id 与注释不计）。",
              hint=f"把 page_key 放进 id（例如 {page_key}-caption-1），让每一页的 id 在全片唯一。")

    # ── Text: fill / family / weight / CSS vars (both routes support <style> + :root var(--...)) ──
    text_nodes = [
        n for n in (list(root.findall(".//{http://www.w3.org/2000/svg}text")) or list(root.findall(".//text")))
        if not is_in_non_rendering_container(n, parent_map)
    ]
    font_families, font_sizes = [], []
    stylesheet_rules, custom_properties = parse_stylesheet(content)
    custom_properties = {**element_custom_properties(root), **custom_properties}

    for idx, node in enumerate(text_nodes, 1):
        tid = f"text_{idx}"
        full_txt = "".join(node.itertext())
        snippet = full_txt.strip()[:40]
        fill_value = text_style_value(node, parent_map, stylesheet_rules, "fill")
        family_value = text_style_value(node, parent_map, stylesheet_rules, "font-family")
        weight_value = (text_style_value(node, parent_map, stylesheet_rules, "font-weight") or "").strip()

        if fill_value is None:
            E("MISSING_FILL",
              f"<text> 没有取到填色：元素上没有 fill、style 里没有、class 命中的 <style> 规则里也没有: "
              f"'{snippet}…'", target=tid)
        if family_value is None:
            W("MISSING_FONT_FAMILY",
              f"<text> 没有取到字体：元素上没有 font-family、style 里没有、class 命中的 <style> 规则里也没有: "
              f"'{snippet}…'", target=tid)
        else:
            font_families.append(str(family_value).strip())
        if weight_value and weight_value not in VALID_FONT_WEIGHTS:
            E("INVALID_FONT_WEIGHT", f"font-weight '{weight_value}' is not a valid value", target=tid)

        for prop, value in (("fill", fill_value), ("font-family", family_value),
                            ("font-weight", weight_value)):
            for token, fallback in undefined_css_vars(value, custom_properties):
                source = text_style_source(node, parent_map, stylesheet_rules, prop)
                if fallback:
                    detail = (f"取值方式：{source}；这一处用了没定义的 token {token}"
                              f"（回退值 {fallback.strip()} 让它看起来正常）"
                              f"——但换主题时这一处不会跟着变，风格库对它失效。")
                else:
                    detail = f"取值方式：{source}；这一处没有回退值，实际取不到颜色。"
                E("UNDEFINED_CSS_VAR",
                  f"这一页用了没定义的 token：<text> 的 {prop} 取 var({token})，"
                  f"但同一份 SVG 里没有定义 {token}: '{snippet}…'",
                  target=tid, detail=detail,
                  hint=f"在页内 <style> 的 :root 里定义 {token}（值从风格库取），或改用一个已定义的 token。")

        # ── Guard 2 (slides only): EMOJI_IN_SLIDE_TEXT ──
        if slides:
            found_emojis = sorted(set(EMOJI_RE.findall(full_txt)))
            if found_emojis:
                E("EMOJI_IN_SLIDE_TEXT",
                  f"<text> contains system bitmap emoji ({''.join(found_emojis)}): '{snippet}…' — "
                  "use native SVG geometric icons or monospace index numbers (01, 02) instead",
                  target=tid,
                  hint="严禁用 🛡️💧🎯⚠️ 等系统 Emoji 当图标；请改用原生 SVG 几何路径或等宽数字编号。")

        _, _, sx, sy = get_accumulated_transform(node, parent_map)
        raw_fs = text_style_value(node, parent_map, stylesheet_rules, "font-size")
        fs = parse_float(raw_fs, 0) * min(sx, sy)
        if fs > 0:
            font_sizes.append(fs)

    # ── Readability floor, per declared reading mode (slides route only) ──
    if slides:
        floor = MODE_FLOOR.get(page_mode, MODE_FLOOR[DEFAULT_MODE])
        for idx, node in enumerate(text_nodes, 1):
            _, _, sx, sy = get_accumulated_transform(node, parent_map)
            raw_fs = text_style_value(node, parent_map, stylesheet_rules, "font-size")
            fs = parse_float(raw_fs, 0) * min(sx, sy)
            if 0 < fs < floor:
                snippet = "".join(node.itertext()).strip()[:30]
                E("TEXT_BELOW_READABILITY_FLOOR",
                  f"font-size {fs:.0f}px is below the {page_mode} floor of {floor:.0f}px "
                  f"(≈{floor * 0.5:.0f}pt): '{snippet}…'",
                  target=f"text_{idx}",
                  hint="Raise the size, or declare this page as a 读 page if it is meant to be read up close.")

    visible_rect_nodes = [
        n for n in (root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect"))
        if not is_in_non_rendering_container(n, parent_map)
    ]
    visible_line_nodes = [
        n for n in (root.findall(".//{http://www.w3.org/2000/svg}line") or root.findall(".//line"))
        if not is_in_non_rendering_container(n, parent_map)
    ]

    # ── Text overlapping text & slide geometry guards ──
    if not quick_mode:
        text_boxes = []
        for idx, node in enumerate(text_nodes, 1):
            tbox = estimate_text_box(node, parent_map, stylesheet_rules)
            if tbox[2] > 0:
                text_boxes.append((f"text_{idx}", node, tbox, "".join(node.itertext()).strip()[:30]))
        def _is_decorative_watermark(t_node):
            _, _, sx, sy = get_accumulated_transform(t_node, parent_map)
            raw_fs = text_style_value(t_node, parent_map, stylesheet_rules, "font-size") or "20"
            for tok, fb in CSS_DECLARATION_RE.findall(str(raw_fs)):
                raw_fs = custom_properties.get(tok, fb or raw_fs)
            t_fs = parse_float(raw_fs, 20.0) * min(sx, sy)
            if t_fs < 88.0:
                return False
            t_op = parse_float(text_style_value(t_node, parent_map, stylesheet_rules, "opacity"), 1.0)
            if t_op <= 0.75:
                return True
            raw_fill = str(text_style_value(t_node, parent_map, stylesheet_rules, "fill") or "").strip()
            for tok, fb in CSS_DECLARATION_RE.findall(raw_fill):
                raw_fill = custom_properties.get(tok, fb or raw_fill)
            t_fill = raw_fill.strip().upper()
            if re.fullmatch(r"#[0-9A-F]{6}", t_fill):
                r, g, b = int(t_fill[1:3], 16), int(t_fill[3:5], 16), int(t_fill[5:7], 16)
                if min(r, g, b) >= 216:
                    return True
            return False

        for i in range(len(text_boxes)):
            for j in range(i + 1, len(text_boxes)):
                tid_a, node_a, box_a, txt_a = text_boxes[i]
                tid_b, node_b, box_b, txt_b = text_boxes[j]
                if _is_decorative_watermark(node_a) or _is_decorative_watermark(node_b):
                    continue
                if not intersects(box_a, box_b):
                    continue
                overlap_x = min(box_a[0] + box_a[2], box_b[0] + box_b[2]) - max(box_a[0], box_b[0])
                overlap_y = min(box_a[1] + box_a[3], box_b[1] + box_b[3]) - max(box_a[1], box_b[1])
                if overlap_x > 5 and overlap_y > 5:
                    W("TEXT_OVERLAP",
                      f"Text elements overlap: '{txt_a}…' and '{txt_b}…'",
                      target=tid_a,
                      detail=f"overlaps {tid_b} ({overlap_x:.0f}x{overlap_y:.0f}px)",
                      hint="Estimated boxes are approximate — confirm on the rendered PNG before rewriting the page.")

        # ── Safe margin: advisory only (full-bleed art direction is legitimate) ──
        for tid_a, _, tbox, _ in text_boxes:
            if tbox[2] > 0 and outside_safe_margin(tbox, margin):
                I("OUTSIDE_SAFE_MARGIN",
                  f"Text sits outside the {margin:.0f}px safe margin — verify on the PNG",
                  target=tid_a, detail=box_to_dict(tbox))

        if slides:
            # ── Guard 1 (slides only): LINE_CROSSES_TEXT ──
            # Build DOM z-order index so lines masked behind opaque pill/card <rect>s are not false positives
            dom_order = {n: idx for idx, n in enumerate(root.iter())}
            opaque_rects = []
            for r_node in visible_rect_nodes:
                fill_v = (text_style_value(r_node, parent_map, stylesheet_rules, "fill") or "").strip().lower()
                if not fill_v or fill_v in ("none", "transparent"):
                    continue
                op_v = parse_float(text_style_value(r_node, parent_map, stylesheet_rules, "opacity"), 1.0)
                fop_v = parse_float(text_style_value(r_node, parent_map, stylesheet_rules, "fill-opacity"), 1.0)
                if op_v * fop_v < 0.75:
                    continue
                rbox = rect_box(r_node, parent_map)
                if not is_full_canvas_rect(rbox) and rbox[2] >= 20.0 and rbox[3] >= 16.0:
                    opaque_rects.append((dom_order.get(r_node, 0), rbox))

            # Collect horizontal and vertical divider segments from <line> and thin <rect>
            divider_segments = []
            for l_idx, l_node in enumerate(visible_line_nodes, 1):
                stroke_v = text_style_value(l_node, parent_map, stylesheet_rules, "stroke")
                if stroke_v == "none":
                    continue
                x1, y1, x2, y2 = line_coords(l_node, parent_map)
                l_z = dom_order.get(l_node, 0)
                if abs(y1 - y2) <= 2.0 and abs(x2 - x1) >= 40.0:
                    divider_segments.append(("horizontal", f"line_{l_idx}", min(x1, x2), max(x1, x2), (y1 + y2) / 2.0, l_z))
                elif abs(x1 - x2) <= 2.0 and abs(y2 - y1) >= 40.0:
                    divider_segments.append(("vertical", f"line_{l_idx}", min(y1, y2), max(y1, y2), (x1 + x2) / 2.0, l_z))

            for r_idx, r_node in enumerate(visible_rect_nodes, 1):
                fill_v = text_style_value(r_node, parent_map, stylesheet_rules, "fill")
                if fill_v == "none":
                    continue
                rx, ry, rw, rh = rect_box(r_node, parent_map)
                r_z = dom_order.get(r_node, 0)
                if 0.5 <= rh <= 4.0 and rw >= 40.0:
                    divider_segments.append(("horizontal", f"rect_{r_idx}", rx, rx + rw, ry + rh / 2.0, r_z))
                elif 0.5 <= rw <= 4.0 and rh >= 40.0:
                    divider_segments.append(("vertical", f"rect_{r_idx}", ry, ry + rh, rx + rw / 2.0, r_z))

            for tid_a, t_node, tbox, txt_a in text_boxes:
                tx, ty, tw, th = tbox
                t_z = dom_order.get(t_node, 0)
                _, _, sx, sy = get_accumulated_transform(t_node, parent_map)
                t_fs = parse_float(text_style_value(t_node, parent_map, stylesheet_rules, "font-size"), 20.0) * min(sx, sy)
                t_op = parse_float(text_style_value(t_node, parent_map, stylesheet_rules, "opacity"), 1.0)
                t_fill = (text_style_value(t_node, parent_map, stylesheet_rules, "fill") or "").strip().upper()
                # Skip giant decorative background watermark numbers (e.g. 140px #F0F0F0 or opacity <= 0.25)
                if t_fs >= 80.0 or t_op <= 0.25 or (t_fs >= 56.0 and t_fill in ("#F0F0F0", "#EEEEEE", "#F5F5F5", "#EAECEF")):
                    continue

                for kind, seg_id, s_min, s_max, s_pos, seg_z in divider_segments:
                    # If the line was drawn BEFORE an opaque pill/card rect that sits behind this text, the line is occluded
                    if seg_z < t_z and any(
                        seg_z < rz < t_z
                        and rb[0] - 4.0 <= tx + tw / 2.0 <= rb[0] + rb[2] + 4.0
                        and rb[1] - 4.0 <= ty + th / 2.0 <= rb[1] + rb[3] + 4.0
                        and rb[2] < 600.0 and rb[3] < 120.0
                        for rz, rb in opaque_rects
                    ):
                        continue
                    if kind == "horizontal":
                        overlap_w = min(s_max, tx + tw) - max(s_min, tx)
                        # Multi-line <tspan dy> text blocks expand downward in PPTX (+2px buffer); single-line text stops at baseline
                        max_y_cut = (ty + th + 2.0) if th > t_fs * 1.5 else (ty + th - 1.5)
                        if overlap_w > 8.0 and (ty + 2.0) <= s_pos <= max_y_cut:
                            E("LINE_CROSSES_TEXT",
                              f"Horizontal divider ({seg_id} at y={s_pos:.0f}) cuts across <text> "
                              f"(y={ty:.0f}..{ty + th:.0f}): '{txt_a}…'",
                              target=tid_a,
                              detail={"divider": seg_id, "line_y": round(s_pos, 1), "text_box": box_to_dict(tbox)},
                              hint="调整分割线 y 坐标或上移/精简文本，严禁分割线切过文字包围盒。")
                            break
                    else:
                        overlap_h = min(s_max, ty + th) - max(s_min, ty)
                        if overlap_h > 6.0 and (tx + 4.0) <= s_pos <= (tx + tw - 4.0):
                            E("LINE_CROSSES_TEXT",
                              f"Vertical divider ({seg_id} at x={s_pos:.0f}) cuts across <text> "
                              f"(x={tx:.0f}..{tx + tw:.0f}): '{txt_a}…'",
                              target=tid_a,
                              detail={"divider": seg_id, "line_x": round(s_pos, 1), "text_box": box_to_dict(tbox)},
                              hint="调整竖向分割线 x 坐标或缩短文本，避免竖线从字中间劈开。")
                            break

            # ── Guard 3 (slides only): TEXT_OVERFLOWS_CONTAINER ──
            container_rects = []
            for r_idx, r_node in enumerate(visible_rect_nodes, 1):
                rbox = rect_box(r_node, parent_map)
                rx, ry, rw, rh = rbox
                if is_full_canvas_rect(rbox):
                    continue
                if 36.0 <= rw <= 1760.0 and 22.0 <= rh <= 860.0:
                    container_rects.append((f"rect_{r_idx}", rbox))

            for tid_a, t_node, tbox, txt_a in text_boxes:
                tx, ty, tw, th = tbox
                dx, dy, sx, sy = get_accumulated_transform(t_node, parent_map)
                anchor_x = dx + parse_float(t_node.get("x")) * sx
                anchor_y = dy + parse_float(t_node.get("y")) * sy
                enclosing = [
                    (rid, rb) for rid, rb in container_rects
                    if (rb[0] <= anchor_x <= rb[0] + rb[2]) and (rb[1] <= anchor_y <= rb[1] + rb[3])
                ]
                if not enclosing:
                    continue
                smallest_id, smallest_box = min(enclosing, key=lambda item: item[1][2] * item[1][3])
                rx, ry, rw, rh = smallest_box
                # For small pill badges (rh <= 56), require at least 2px horizontal fit; for cards, allow 4px tolerance
                limit_w = rw if rh <= 56.0 else rw + 4.0
                if tw > limit_w:
                    W("TEXT_OVERFLOWS_CONTAINER",
                      f"<text> estimated width ({tw:.0f}px) exceeds enclosing container {smallest_id} "
                      f"width ({rw:.0f}px): '{txt_a}…'",
                      target=tid_a,
                      detail={"container": smallest_id, "container_box": box_to_dict(smallest_box),
                              "text_box": box_to_dict(tbox)},
                      hint="加宽胶囊/卡片容器（建议 width >= 字数×字号 + 32px）、缩短文案或用 <tspan dy> 换行，防止导出 PPTX 后折行溢出。")

    # ── Nothing may leave the canvas: rect, image, and text alike ──
    for rect_node in visible_rect_nodes:
        rbox = rect_box(rect_node, parent_map)
        if rbox[2] > 0 and rbox[3] > 0 and outside_canvas(rbox):
            x, y, w, h = rbox
            E("ELEMENT_OUTSIDE_CANVAS",
              f"<rect> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas "
              f"{CANVAS_W:.0f}x{CANVAS_H:.0f}",
              target="svg_structure", detail=box_to_dict(rbox))
    for img_node in image_nodes:
        ibox = image_box(img_node, parent_map)
        if ibox[2] > 0 and ibox[3] > 0 and outside_canvas(ibox):
            x, y, w, h = ibox
            E("IMAGE_OUTSIDE_CANVAS",
              f"<image> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas",
              target="svg_structure", detail=box_to_dict(ibox))
    for idx, node in enumerate(text_nodes, 1):
        tbox = estimate_text_box(node, parent_map, stylesheet_rules)
        if tbox[2] > 0 and outside_canvas(tbox):
            x, y, w, h = tbox
            snippet = "".join(node.itertext()).strip()[:30]
            E("TEXT_OUTSIDE_CANVAS",
              f"<text> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas "
              f"{CANVAS_W:.0f}x{CANVAS_H:.0f}: '{snippet}…'",
              target=f"text_{idx}", detail=box_to_dict(tbox),
              hint="重排、断行或换表达，不要靠缩字塞回去；框是估算的，先在渲染 PNG 上确认这一处。")

    # ── Empty slide ──
    if not text_nodes and not image_nodes:
        W("EMPTY_SLIDE", "Page has neither text nor image — nothing to look at",
          target="svg_structure")

    all_issues = errors + warnings + infos
    if errors:
        status = "fail"
    elif warnings:
        status = "warning"
    else:
        status = "pass"
    return {
        "file": str(path),
        "page_mode": page_mode,
        "route": route,
        "skipped_rules": skipped,
        "status": status,
        "summary": {"errors": len(errors), "warnings": len(warnings), "infos": len(infos)},
        "issues": all_issues,
    }


def select_svg_files(svg_path, manifest_data=None):
    if svg_path.is_file():
        return [svg_path]
    if not manifest_data:
        return sorted(svg_path.glob("*.svg"))
    return [svg_path / (p["page_key"] + ".svg") for p in manifest_data.get("pages", [])]


def main():
    parser = argparse.ArgumentParser(
        description="SVG → PPT conversion checks and real layout defects. No design-style heuristics."
    )
    parser.add_argument("svg_dir", help="Directory containing SVG files")
    parser.add_argument("--margin", type=float, default=MARGIN, help=f"Advisory safe margin in px (default: {MARGIN})")
    parser.add_argument("--output", default="", help="Output JSON path (default: stdout)")
    parser.add_argument("--file", default="", help="Single SVG file to validate (alternative to svg_dir)")
    parser.add_argument("--page-mode", default=DEFAULT_MODE, choices=sorted(MODE_FLOOR),
                        help="Reading mode for this page: 讲 (projected) or 读 (read up close)")
    parser.add_argument("--route", default="auto", choices=["auto", *ROUTES],
                        help="Exit route: slides runs every check, video runs only the half both exits share "
                             "(default: read the route from the project state)")
    parser.add_argument("--fidelity-template", default="", help="Optional reviewed fidelity template_registry.json")
    parser.add_argument("--self-check", action="store_true",
                        help="Skip text-overlap estimation; only hard conversion errors")
    args = parser.parse_args()

    if args.file:
        svg_path = Path(args.file)
        if not svg_path.is_file() or svg_path.suffix.lower() != ".svg":
            print(json.dumps({"status": "fail", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                              "reports": [{"file": str(svg_path), "status": "fail",
                                           "issues": [issue("error", "INVALID_SVG_FILE",
                                                            f"Not a valid SVG file: {svg_path}")]}]},
                             ensure_ascii=False, indent=2))
            return 1
        svg_files, manifest_data = [svg_path], None
    else:
        svg_path = Path(args.svg_dir)
        svg_files = select_svg_files(svg_path, None)

    if not svg_files:
        print(json.dumps({"status": "fail", "summary": {"errors": 1, "warnings": 0, "infos": 0},
                          "reports": [{"file": str(svg_path), "status": "fail",
                                       "issues": [issue("error", "NO_SVG_FILES", "No SVG files found")]}]},
                         ensure_ascii=False, indent=2))
        return 1

    route_value, route_source = resolve_route(args.route, svg_files[0])

    reports = [validate_file(f, page_mode=args.page_mode, margin=args.margin,
                             quick_mode=args.self_check, route=route_value)
               for f in svg_files]

    skipped = skipped_rules_for_route(route_value)

    if args.fidelity_template and route_value == "video":
        # 视频出口不套模板库；显式给了也只是把跳过的原因写清楚，不静默忽略。
        reports[-1]["issues"].append(issue(
            "info", "FIDELITY_TEMPLATE_SKIPPED",
            "fidelity template was given but this project's route is video; the strict-template checks do not run"))
        reports[-1]["summary"]["infos"] += 1
        if reports[-1]["status"] == "pass":
            reports[-1]["status"] = "warning"
    elif args.fidelity_template:
        try:
            fidelity_path = Path(args.fidelity_template).resolve()
            template = json.loads(fidelity_path.read_text(encoding="utf-8"))
            layouts = template.get("layouts", {})
            component_map = {item.get("component_id"): item for item in template.get("components", [])
                             if isinstance(item, dict)}
            strict_components = template.get("schema") == "planner.fidelity-template.v2"

            def fail(report, code, message, page_key):
                report["issues"].append(issue("error", code, message, target=page_key))
                report["summary"]["errors"] += 1
                report["status"] = "fail"

            for report in reports:
                page_key = Path(report["file"]).stem
                root = ET.parse(report["file"]).getroot()
                layout_id = root.attrib.get("data-layout-id", "")
                if not layout_id:
                    fail(report, "FIDELITY_LAYOUT_NOT_DECLARED",
                         "SVG does not declare data-layout-id", page_key)
                    continue
                layout = layouts.get(layout_id)
                if layout is None:
                    fail(report, "UNKNOWN_FIDELITY_LAYOUT",
                         f"SVG declares an unknown fidelity layout: {layout_id}", page_key)
                    continue
                canvas_file = layout.get("canvas_file", "")
                if strict_components and not canvas_file:
                    fail(report, "FIDELITY_CANVAS_NOT_BOUND",
                         f"Layout {layout_id} does not declare canvas_file", page_key)
                elif canvas_file:
                    canvas_path = fidelity_path.parent / canvas_file
                    if not canvas_path.is_file():
                        fail(report, "FIDELITY_CANVAS_MISSING",
                             f"Layout canvas is missing: {canvas_file}", page_key)
                    else:
                        # 这个 canvas 是哪一代的形状，页面必须说自己用的是同一代——
                        # 不对着一个版本号比较，旧页面在新 canvas 上会被当成「没改锁层」。
                        canvas_version = ET.parse(canvas_path).getroot().attrib.get(
                            "data-template-canvas-version", "")
                        page_version_declared = root.attrib.get("data-template-canvas-version", "")
                        if not page_version_declared:
                            fail(report, "FIDELITY_CANVAS_VERSION_MISSING",
                                 f"SVG does not declare data-template-canvas-version; canvas {layout_id} is "
                                 f"version {canvas_version or TEMPLATE_CANVAS_VERSION}", page_key)
                        elif page_version_declared != canvas_version:
                            fail(report, "FIDELITY_CANVAS_VERSION_MISMATCH",
                                 f"SVG was built from canvas version {page_version_declared}, but {layout_id} "
                                 f"is version {canvas_version}", page_key)
                        expected_lock = layout.get("locked_sha256", "")
                        try:
                            canvas_lock = locked_sha256(canvas_path)
                            page_lock = locked_sha256(Path(report["file"]))
                        except ValueError as exc:
                            fail(report, "FIDELITY_LOCKED_LAYER_MISSING", str(exc), page_key)
                            continue
                        if not expected_lock or canvas_lock != expected_lock:
                            fail(report, "FIDELITY_CANVAS_INTEGRITY_ERROR",
                                 f"Layout canvas lock hash is stale for {layout_id}", page_key)
                        elif page_lock != expected_lock:
                            fail(report, "FIDELITY_LOCKED_LAYER_MISMATCH",
                                 f"SVG changed the locked layer of canvas {layout_id}", page_key)
                used_nodes = {}
                for node in root.iter():
                    component_id = node.attrib.get("data-template-component")
                    if component_id:
                        used_nodes.setdefault(component_id, []).append(node)
                used = set(used_nodes)
                for component_id in sorted(used - set(component_map)):
                    fail(report, "UNKNOWN_FIDELITY_COMPONENT",
                         f"SVG uses unknown template component {component_id}", page_key)
                for component_id in layout.get("required_components", []):
                    if component_id not in used:
                        fail(report, "REQUIRED_FIDELITY_COMPONENT_MISSING",
                             f"Layout {layout_id} requires template component {component_id}", page_key)
                if strict_components:
                    for component_id, nodes in used_nodes.items():
                        component = component_map.get(component_id)
                        if not component:
                            continue
                        if component.get("geometry_policy", "fixed") == "fixed" and len(nodes) != 1:
                            fail(report, "FIDELITY_FIXED_COMPONENT_DUPLICATED",
                                 f"Fixed template component {component_id} must appear exactly once", page_key)
                        for node in nodes:
                            for code, message in fidelity_component_node_errors(component, node):
                                fail(report, code, message, page_key)
        except Exception as exc:
            reports[-1]["issues"].append(issue("error", "INVALID_FIDELITY_TEMPLATE", str(exc),
                                              target="fidelity_template"))
            reports[-1]["summary"]["errors"] += 1
            reports[-1]["status"] = "fail"

    total_errors = sum(r["summary"]["errors"] for r in reports)
    total_warnings = sum(r["summary"]["warnings"] for r in reports)
    total_infos = sum(r["summary"]["infos"] for r in reports)
    agg_status = "fail" if total_errors else ("warning" if total_warnings else "pass")

    summary = {
        "status": agg_status,
        "route": route_value,
        "route_source": route_source,
        "summary": {"errors": total_errors, "warnings": total_warnings, "infos": total_infos},
        "skipped_rules": skipped,
        "reports": reports,
    }

    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
