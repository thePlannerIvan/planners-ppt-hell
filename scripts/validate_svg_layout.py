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
from layout_canvas import TEMPLATE_CANVAS_VERSION, locked_sha256  # noqa: E402
from native_svg_to_ppt import compose_axis_aligned, parse_axis_aligned_transform  # noqa: E402
from project_state import DEFAULT_ROUTE, ROUTES, project_root_of, route as project_route  # noqa: E402

TEXT_RE = re.compile(r"\s+")

CANVAS_W = FRAME_W
CANVAS_H = FRAME_H
MARGIN = 60.0
VALID_FONT_WEIGHTS = {"normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"}

# Reading mode drives the readability floor. 1 SVG px = 0.5 pt on a 13.333in slide,
# so 12px is 6pt (nothing is readable below this at any zoom) and 18px is 9pt.
MODE_FLOOR = {"讲": 18.0, "读": 12.0}
DEFAULT_MODE = "读"

PROHIBITED_ELEMENTS = ["foreignObject", "filter", "use", "style", "marker", "mask", "animate"]
PROHIBITED_ATTRIBUTES = [
    "stroke-dasharray", "textLength", "lengthAdjust",
    "marker-start", "marker-mid", "marker-end",
]
PROHIBITED_TRANSFORMS = ["rotate(", "skew(", "matrix("]


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
                    "视频出口是 PNG，<style> 与动画都承载得住。"},
            {"rule": "PROHIBITED_ATTRIBUTES",
             "codes": [f"PROHIBITED_{attr.replace('-', '_').upper()}" for attr in PROHIBITED_ATTRIBUTES],
             "why": "这些属性同样只因转换器不支持而被禁；PNG 渲染不受影响。"},
            {"rule": "PROHIBITED_TRANSFORM",
             "codes": ["PROHIBITED_TRANSFORM"],
             "why": "rotate／skew／matrix 只在转 PPT 时不可靠；视频出口按页面自己的坐标渲染。"},
            {"rule": "TSPAN_LINEBREAK",
             "codes": ["TSPAN_LINEBREAK"],
             "why": "tspan 换行是 PPT 文本解析器的要求，PNG 渲染没有这道限制。"},
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
    """`<svg>` 之下每个元素自己的 `id`——回答「有没有可指名的元素」。

    不算数的三样：根 `<svg>` 自己的 id（它指不了页面内的东西）、`data-*-id` 这类属性
    （`data-layout-id`／`data-template-*` 是别的语义，实测那 8 页里有 16 个这样的值）、
    注释里的一切（`ET` 解析时就不产生注释节点）。
    """
    return _element_ids(root, include_root=False)


def document_ids(root):
    """整份 SVG 里所有元素的 `id`，**含根 `<svg>`**——回答「这份 id 合法且不歧义吗」。

    根也是一个 id：`<svg id="page">` 与子元素撞车时 `#page` 只命中第一个（根），
    那个子元素再也指不到。所以页内 id 唯一要连根一起看。
    """
    return _element_ids(root, include_root=True)


def duplicated_ids(ids):
    """出现过一次以上的 id：[(名字, 次数)]，按名字排序。

    只看这一页。跨页碰撞不在这里管——一次只读一页，那是各屏被内联进同一个 DOM 之后
    才看得出来的事（导入器负责在导入前报告待导入页面之间的 id 碰撞）。
    """
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
    cleaned = re.sub(r"[^\d.\-]", "", value)
    return float(cleaned) if cleaned else default


def parse_color(value):
    if not value or value == "none":
        return None
    v = value.strip().upper()
    if v.startswith("URL("):
        return None
    return v


def get_accumulated_transform(node, parent_map):
    """A node's absolute translate/scale, using 转换 PPT's own coordinate model.

    This no longer mirrors native_svg_to_ppt by hand — it calls it. The hand-written
    copy silently disagreed (same input, answers 100px apart), which is exactly the
    class of failure a second implementation always eventually produces.
    """
    ancestors = []
    current = node
    while current in parent_map:
        current = parent_map[current]
        ancestors.append(current)
    ancestors.reverse()
    accumulated = (0.0, 0.0, 1.0, 1.0)
    for ancestor in ancestors:
        accumulated = compose_axis_aligned(
            accumulated, parse_axis_aligned_transform(ancestor.get("transform", "")))
    return accumulated


def build_parent_map(root):
    pm = {}
    for parent in root.iter():
        for child in parent:
            pm[child] = parent
    return pm


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
    """一个文字属性最终取到的值：元素属性 > 元素 style > class 命中的样式表规则。

    这个优先序与 CSS 一致（presentation attribute 的优先级低于作者样式，但这里
    只回答「有没有取到值」，所以先看更明确的那一处）。
    """
    if node.get(prop) is not None:
        return node.get(prop)
    inline = css_declarations(node.get("style"))
    if prop in inline:
        return inline[prop]
    return stylesheet_value(node, parent_map, rules, prop)


def text_style_source(node, parent_map, rules, prop):
    if node.get(prop) is not None:
        return f"元素属性 {prop}=\"{node.get(prop)}\""
    inline = css_declarations(node.get("style"))
    if prop in inline:
        return f'元素 style 上的 {prop}: {inline[prop]}'
    value = stylesheet_value(node, parent_map, rules, prop)
    if value is not None:
        return "class 命中的 <style> 规则"
    return "三处都没有"


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


def estimate_text_box(node, parent_map):
    """Estimated ink box. Honors text-anchor, so centred/right-aligned text is not
    reported as overflowing the right margin or colliding with a neighbour."""
    dx, dy, sx, sy = get_accumulated_transform(node, parent_map)
    x = dx + parse_float(node.get("x")) * sx
    y = dy + parse_float(node.get("y")) * sy
    font_size = parse_float(node.get("font-size"), 24.0) * min(sx, sy)
    content = TEXT_RE.sub(" ", "".join(node.itertext())).strip()
    w = estimate_text_width(content, font_size) if content else 0.0
    h = font_size * 1.18
    anchor = (node.get("text-anchor") or "start").strip()
    if anchor == "middle":
        x -= w / 2.0
    elif anchor == "end":
        x -= w
    return (x, y - font_size, w, h)


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
        # 一条 line 没有「填充」这回事：拿 fill 去比会永远对不上。比的是这个元素
        # 实际会画的那些属性。
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
        for el_name in PROHIBITED_ELEMENTS:
            if f"<{el_name}".lower() in content.lower():
                E(f"PROHIBITED_{el_name.upper()}", f"SVG uses <{el_name}> — unsupported in PPT conversion",
                  target="svg_structure")
        for attr in PROHIBITED_ATTRIBUTES:
            if attr.lower() in content.lower():
                E(f"PROHIBITED_{attr.replace('-', '_').upper()}",
                  f"SVG uses {attr} — unsupported in PPT conversion", target="svg_structure")
        for tf in PROHIBITED_TRANSFORMS:
            if tf.lower() in content.lower():
                E("PROHIBITED_TRANSFORM", f"SVG uses transform with {tf} — unsupported in PPT conversion",
                  target="svg_structure")

    # ── Images must be real local project files, never stretched (both routes) ──
    image_nodes = list(root.findall(".//{http://www.w3.org/2000/svg}image")) or list(root.findall(".//image"))
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
    # 视频出口交出去的不是几张图，是一个能被按元素指名的活结构：后面要按实测音频做
    # 「讲到哪强调哪」的轻动画。实测 44 张真实页面 0 个 id，所以这一条必须有人核。
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

    # ── tspan line breaks break the PPT text parser (slides route only) ──
    if slides:
        tspans = re.findall(r"<tspan\b[^>]*>", content, re.I)
        if any("dy=" in t.lower() for t in tspans):
            E("TSPAN_LINEBREAK",
              "SVG uses <tspan> with dy for line breaks — causes PPT parse errors; use separate <text> elements",
              target="svg_structure")

    # ── Text: fill / family / weight ──
    # 幻灯片出口要显式字面值（转换器写进 PPTX 的就是这些属性本身）。
    # 视频出口是 PNG，风格 token 按 `03_video_route.md` 经内联 <style> 的 class 规则落地，
    # 所以「取到值」的三种方式都算：元素属性、元素 style=""、class 命中的同页 <style> 规则。
    # 三处都取不到才是 MISSING_*；三处里出现没定义的 var(--x) 是硬错误。
    text_nodes = list(root.findall(".//{http://www.w3.org/2000/svg}text")) or list(root.findall(".//text"))
    font_families, font_sizes = [], []
    stylesheet_rules, custom_properties = ({}, {}) if slides else parse_stylesheet(content)
    if not slides:
        # 元素 style="" 上声明的 token 也算「这一页定义了」。
        custom_properties = {**element_custom_properties(root), **custom_properties}
    for idx, node in enumerate(text_nodes, 1):
        tid = f"text_{idx}"
        snippet = "".join(node.itertext()).strip()[:40]
        if slides:
            fill_value = node.get("fill")
            family_value = node.get("font-family")
            weight_value = (node.get("font-weight") or "").strip()
        else:
            fill_value = text_style_value(node, parent_map, stylesheet_rules, "fill")
            family_value = text_style_value(node, parent_map, stylesheet_rules, "font-family")
            weight_value = (text_style_value(node, parent_map, stylesheet_rules, "font-weight") or "").strip()
        if fill_value is None:
            E("MISSING_FILL",
              (f"<text> missing explicit fill: '{snippet}…'" if slides else
               f"<text> 没有取到填色：元素上没有 fill、style 里没有、class 命中的 <style> 规则里也没有: "
               f"'{snippet}…'"), target=tid)
        if family_value is None:
            W("MISSING_FONT_FAMILY",
              (f"<text> missing explicit font-family: '{snippet}…'" if slides else
               f"<text> 没有取到字体：元素上没有 font-family、style 里没有、class 命中的 <style> 规则里也没有: "
               f"'{snippet}…'"), target=tid)
        else:
            font_families.append(str(family_value).strip())
        if weight_value and weight_value not in VALID_FONT_WEIGHTS:
            E("INVALID_FONT_WEIGHT", f"font-weight '{weight_value}' is not a valid value", target=tid)
        if not slides:
            for prop, value in (("fill", fill_value), ("font-family", family_value),
                                ("font-weight", weight_value)):
                for token, fallback in undefined_css_vars(value, custom_properties):
                    source = text_style_source(node, parent_map, stylesheet_rules, prop)
                    if fallback:
                        # 回退值让它看起来正常，但代价是这一处不再跟着主题走——
                        # 那正是风格库存在的理由，所以它也是 error，只是要把后果说清楚。
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
        fs = parse_float(node.get("font-size"), 0)
        if fs > 0:
            font_sizes.append(fs)

    # ── Readability floor, per declared reading mode (slides route only) ──
    if slides:
        floor = MODE_FLOOR.get(page_mode, MODE_FLOOR[DEFAULT_MODE])
        for idx, node in enumerate(text_nodes, 1):
            fs = parse_float(node.get("font-size"), 0)
            if 0 < fs < floor:
                snippet = "".join(node.itertext()).strip()[:30]
                E("TEXT_BELOW_READABILITY_FLOOR",
                  f"font-size {fs:.0f}px is below the {page_mode} floor of {floor:.0f}px "
                  f"(≈{floor * 0.5:.0f}pt): '{snippet}…'",
                  target=f"text_{idx}",
                  hint="Raise the size, or declare this page as a 读 page if it is meant to be read up close.")

    # ── Text overlapping text: wrong on any page, any style ──
    if not quick_mode:
        text_boxes = []
        for idx, node in enumerate(text_nodes, 1):
            tbox = estimate_text_box(node, parent_map)
            if tbox[2] > 0:
                text_boxes.append((f"text_{idx}", tbox, "".join(node.itertext())[:30]))
        for i in range(len(text_boxes)):
            for j in range(i + 1, len(text_boxes)):
                tid_a, box_a, txt_a = text_boxes[i]
                tid_b, box_b, txt_b = text_boxes[j]
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
        for idx, node in enumerate(text_nodes, 1):
            tbox = estimate_text_box(node, parent_map)
            if tbox[2] > 0 and outside_safe_margin(tbox, margin):
                I("OUTSIDE_SAFE_MARGIN",
                  f"Text sits outside the {margin:.0f}px safe margin — verify on the PNG",
                  target=f"text_{idx}", detail=box_to_dict(tbox))

    # ── Nothing may leave the canvas: rect, image, and text alike ──
    # 文字此前只有一条 info 级的 OUTSIDE_SAFE_MARGIN，一条伸出画布 640px 的标题
    # 也能判 pass。安全区是美术方向（保持 info）；画布不是。
    for rect_node in (root.findall(".//{http://www.w3.org/2000/svg}rect") or root.findall(".//rect")):
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
        tbox = estimate_text_box(node, parent_map)
        if tbox[2] > 0 and outside_canvas(tbox):
            x, y, w, h = tbox
            snippet = "".join(node.itertext()).strip()[:30]
            E("TEXT_OUTSIDE_CANVAS",
              f"<text> at ({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} extends beyond canvas "
              f"{CANVAS_W:.0f}x{CANVAS_H:.0f}: '{snippet}…'",
              target=f"text_{idx}", detail=box_to_dict(tbox),
              hint="重排、断行或换表达，不要靠缩字塞回去；框是估算的，先在渲染 PNG 上确认这一处。")

    # ── Empty slide ──
    # The genuinely blank page is the one with nothing to look at: neither text nor image.
    # The old `visible < 3` element count was written for slides, where one or two elements
    # are suspicious; it misreads a screen that is one full-bleed picture, and a title-only
    # page, as empty. Still a warning: it flags, it does not block.
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
