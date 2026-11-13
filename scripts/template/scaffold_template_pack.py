#!/usr/bin/env python3
"""从原生 layout 目录 + 提取事实生成模板包脚手架。

脚本只做「有据可依的部分」：

  · `tokens.css` —— 画布/墨色/强调色/字号/安全边距，全部是合法单值；
  · `SPEC.md`   —— 源信息、色彩表、母版安全区、版式目录；设计哲学与逐版式用法留给模型；
  · `skyline_shell.svg` —— 画布 + 安全区上下线，明确是脚手架，模型替换；
  · `layouts.json` —— 按结构家族收的版式目录，指向 `previews/`、`anchors/`、`primitives/`；
  · `previews/pages/*.png` 与 `anchors/*.png` —— 每个家族的代表源页。

不写 `primitives/`：那是页面设计，由模型按槽位与源页制作。已有文件默认不覆盖，`--force` 才重写。
"""

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

TARGET_W, TARGET_H = 1920, 1080

USE_FOR = {
    "cover": "封面 / 标题页",
    "divider": "章节分隔 / 议题过渡",
    "one_column": "单栏完整论述 / 证据展开",
    "two_columns": "双栏并列 / 对比",
    "three_columns": "三栏并列 / 三条支柱",
    "large_image": "大图 + 说明 / 视觉证据",
    "split": "左右分栏：标题 + 内容",
    "headline_only": "标题 + 顶线 / 纯标题页",
    "quote": "引语 / 观点摘录",
    "blank": "自由版式 / 留白",
    "contact": "联系页 / 收尾",
    "chart": "图表 / 数据页",
    "full_bleed": "全幅图 / 沉浸页",
    "other": "其他结构",
}

DEFAULT_FALLBACK = {
    "canvas": "#FFFFFF", "dark": "#0C0D11", "card": "#FFFFFF", "muted": "#F4F7FA",
    "ink": "#1F2937", "ink_secondary": "#5B6472", "ink_muted": "#8A93A3", "on_dark": "#FFFFFF",
    "accent": ["#003781", "#13A0D3", "#F86200"], "border": "#D8E0EC",
}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_text(path, text, force=False):
    path = Path(path)
    if path.is_file() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def luma(hex_color):
    value = str(hex_color or "").lstrip("#")
    if len(value) != 6:
        return 0.5
    red, green, blue = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def hue(hex_color):
    value = str(hex_color or "").lstrip("#")
    if len(value) != 6:
        return 0.0
    red, green, blue = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    high, low = max(red, green, blue), min(red, green, blue)
    delta = high - low
    if delta == 0:
        return 0.0
    if high == red:
        return (60 * ((green - blue) / delta)) % 360
    if high == green:
        return 60 * ((blue - red) / delta) + 120
    return 60 * ((red - green) / delta) + 240


def saturation(hex_color):
    value = str(hex_color or "").lstrip("#")
    if len(value) != 6:
        return 0.0
    red, green, blue = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    high, low = max(red, green, blue), min(red, green, blue)
    return 0.0 if high == 0 else (high - low) / high


def _hex(value):
    text = str(value or "").strip()
    return text if re.fullmatch(r"#[0-9A-Fa-f]{6}", text) else ""


def palette(facts):
    visual = (facts or {}).get("visual_palette_sampling") or {}
    structural = ((facts or {}).get("pptx_structural_facts") or {}).get("visible_color_stats") or {}
    lights = [item for item in visual.get("dominant_light_surfaces") or [] if _hex(item.get("hex"))]
    darks = [item for item in visual.get("dominant_dark_ink_or_surfaces") or [] if _hex(item.get("hex"))]
    accents = [item for item in visual.get("dominant_saturated_accents") or [] if _hex(item.get("hex"))]

    light = max((item for item in lights if luma(item["hex"]) >= .82), key=lambda item: item.get("pixel_weight", 0), default=None)
    if light is None and lights:
        light = max(lights, key=lambda item: luma(item["hex"]))
    dark = min(darks, key=lambda item: luma(item["hex"]), default=None)
    structural_accents = [item["hex"] for item in (structural.get("accents_bars_and_badges") or [])
                          if _hex(item.get("hex"))]
    accent_pool = structural_accents + [item["hex"] for item in accents]
    accent_hexes = []
    for hex_color in accent_pool:
        if luma(hex_color) < .08 or luma(hex_color) > .94 or saturation(hex_color) < .18:
            continue
        if hex_color not in accent_hexes:
            accent_hexes.append(hex_color)
        if len(accent_hexes) == 6:
            break
    # 第三个强调位优先给暖色（橙/黄），品牌页常把它当唯一破局色。
    warm = next((hex_color for hex_color in accent_hexes[2:]
                 if 15 <= hue(hex_color) <= 65 and saturation(hex_color) >= .35), "")
    if warm:
        accent_hexes = [accent_hexes[0], accent_hexes[1], warm]
    text_items = structural.get("text_colors") or []
    text_hexes = [item["hex"] for item in text_items if _hex(item.get("hex"))]
    ink = next((hex_color for hex_color in text_hexes if luma(hex_color) < .45), "")
    # 次级墨色要中性：源里的品牌色/青色经常是标题或强调，拿来当正文会花。
    ink_secondary = next((hex_color for hex_color in text_hexes
                          if .32 <= luma(hex_color) <= .72 and saturation(hex_color) < .25), "")
    on_dark = next((hex_color for hex_color in text_hexes if luma(hex_color) > .8), "")
    border_items = structural.get("stroke_and_line_colors") or []
    border = next((item["hex"] for item in border_items if _hex(item.get("hex")) and luma(item["hex"]) > .6), "")

    return {
        "canvas": (light or {}).get("hex") or DEFAULT_FALLBACK["canvas"],
        "dark": (dark or {}).get("hex") or DEFAULT_FALLBACK["dark"],
        "card": "#FFFFFF",
        "muted": (lights[1]["hex"] if len(lights) > 1 else DEFAULT_FALLBACK["muted"]),
        "ink": ink or DEFAULT_FALLBACK["ink"],
        "ink_secondary": ink_secondary or DEFAULT_FALLBACK["ink_secondary"],
        "ink_muted": DEFAULT_FALLBACK["ink_muted"],
        "on_dark": on_dark or DEFAULT_FALLBACK["on_dark"],
        "accent": (accent_hexes + DEFAULT_FALLBACK["accent"])[:3],
        "border": border or DEFAULT_FALLBACK["border"],
    }


def font_stack(facts):
    families = (((facts or {}).get("pptx_structural_facts") or {}).get("visible_typography_stats") or {}).get("font_families_by_char_count") or []
    if families and families[0].get("font_family"):
        name = str(families[0]["font_family"]).replace('"', "")
        return f'"{name}", Arial, "PingFang SC", sans-serif'
    return 'Arial, "PingFang SC", "Helvetica Neue", sans-serif'


def type_sizes(facts):
    tiers = (((facts or {}).get("pptx_structural_facts") or {}).get("visible_typography_stats") or {}).get("font_size_tiers_1080p") or []
    sizes = [int(item["px_1080p"]) for item in tiers if item.get("px_1080p")]
    display = max(sizes) if sizes else 120
    headline = max((size for size in sizes if size <= 120), default=64)
    body_candidates = [item for item in tiers if item.get("px_1080p") and int(item["px_1080p"]) <= 36]
    body = int(max(body_candidates, key=lambda item: item.get("char_count", 0))["px_1080p"]) if body_candidates else 24
    caption = 14
    return display, headline, body, caption


def safe_margins(catalog):
    xs, ys = [], []
    for family in (catalog or {}).get("families") or []:
        for slot in family.get("slots") or []:
            x, y = slot.get("x"), slot.get("y")
            if isinstance(x, (int, float)) and x > 0:
                xs.append(x)
            if isinstance(y, (int, float)) and y > 0:
                ys.append(y)
    return (round(min(xs)) if xs else 75, round(min(ys)) if ys else 75)


def slug(value):
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "layout"


def selected_families(catalog, only=None, limit=0, include_unused=False):
    families = [item for item in (catalog or {}).get("families") or []
                if item.get("family") != "other" and (include_unused or int(item.get("usage") or 0) > 0)]
    if only:
        wanted = {slug(item) for item in only}
        families = [item for item in families if item.get("family") in wanted]
    families.sort(key=lambda item: (-int(item.get("usage") or 0), str(item.get("label") or "")))
    if limit and limit > 0:
        families = families[:limit]
    return families


def page_shape_summary(catalog, page):
    shapes = next((item.get("shapes") or [] for item in (catalog or {}).get("pages") or []
                   if item.get("page") == page), [])
    counter = {}
    for shape in shapes:
        kind = shape.get("kind") or "shape"
        counter[kind] = counter.get(kind, 0) + 1
    return "、".join(f"{kind}×{count}" for kind, count in sorted(counter.items())) or "—"


def layout_records(catalog, families, pack):
    records = []
    used_ids = set()
    for index, family in enumerate(families, start=1):
        layout_id = slug(family.get("family") or family.get("label"))
        if layout_id in used_ids:
            layout_id = f"{layout_id}_{index}"
        used_ids.add(layout_id)
        source_layouts = [
            {"source_id": source_id, "name": name}
            for source_id, name in zip(family.get("layout_ids") or [], family.get("layout_names") or [])
        ]
        records.append({
            "layout_id": layout_id,
            "name": family.get("label") or layout_id,
            "family": family.get("family"),
            "use_for": USE_FOR.get(family.get("family"), USE_FOR["other"]),
            "usage": int(family.get("usage") or 0),
            "source_layouts": source_layouts,
            "source_pages": family.get("source_pages") or [],
            "slots": family.get("slots") or [],
            "preview": f"previews/pages/{layout_id}.png",
            "anchor": f"anchors/{layout_id}.png",
            "primitive": f"primitives/p{index:02d}_{layout_id}.svg",
            "selected": True,
            "status": "draft",
            "representative_page": family.get("representative_page") or 0,
            "source_shapes": page_shape_summary(catalog, family.get("representative_page") or 0),
        })
    return records


def tokens_css(palette_values, sizes, margins, font):
    display, headline, body, caption = sizes
    accents = palette_values["accent"]
    return f""":root {{
  /* 画布与表面（scaffold 由 visual_palette_sampling 生成） */
  --canvas-bg: {palette_values['canvas']};
  --canvas-dark: {palette_values['dark']};
  --surface-card: {palette_values['card']};
  --surface-muted: {palette_values['muted']};

  /* 墨色与强调 */
  --ink-primary: {palette_values['ink']};
  --ink-secondary: {palette_values['ink_secondary']};
  --ink-muted: {palette_values['ink_muted']};
  --ink-on-dark: {palette_values['on_dark']};
  --accent-1: {accents[0]};
  --accent-2: {accents[1]};
  --accent-3: {accents[2]};
  --border-line: {palette_values['border']};

  /* 字体与字号（源事实里是 px@1080p，脚手架只收合法单值） */
  --font-sans: {font};
  --size-display: {display}px;
  --size-headline: {headline}px;
  --size-body: {body}px;
  --size-caption: {caption}px;

  /* 母版占位符几何推出的安全边距 */
  --space-safe-x: {margins[0]}px;
  --space-safe-y: {margins[1]}px;
  --canvas-w: {TARGET_W}px;
  --canvas-h: {TARGET_H}px;
}}
"""


def slots_text(slots):
    parts = []
    for slot in slots or []:
        role = slot.get("role") or "other"
        box = "/".join(str(round(slot[key])) if isinstance(slot.get(key), (int, float)) else "?" for key in ("x", "y", "width", "height"))
        parts.append(f"{role} {box}")
    return "；".join(parts) or "—"


def source_layout_text(record):
    names = [f"{item['name']} ({item['source_id']})" for item in record.get("source_layouts") or []]
    return "、".join(names) or "—"


def spec_markdown(name, facts, catalog, records, palette_values, sizes, margins, font):
    source = str((facts or {}).get("source_file") or (catalog or {}).get("source") or "")
    rows = "\n".join(
        f"| `{record['primitive']}` | **{record['name']}** | {record['usage']} | "
        f"{source_layout_text(record)} | "
        f"{', '.join(str(page) for page in record['source_pages'][:8]) or '—'} | "
        f"{record.get('source_shapes') or '—'} | "
        f"`{record['layout_id']}` |" for record in records)
    return f"""# {name} · 模板包（脚手架）

> 由 `scaffold_template_pack.py` 从源 PPTX 的 master/layout 目录生成。色彩、字号、安全区、版式目录都来自源事实；设计哲学、逐版式的用法与红线、primitive 与 skyline_shell 仍需模型补齐。

## 源与覆盖

- 源文件：`{source}`
- 页数 / master / layout：{(facts or {}).get('rendered_page_count') or (catalog or {}).get('slide_count') or '—'} / {(catalog or {}).get('master_count') or '—'} / {len((catalog or {}).get('layouts') or [])}
- 本包收的结构家族：{len(records)} 个

## 一、色彩与字体

| 令牌 | 值 | 来源 |
| :--- | :--- | :--- |
| `--canvas-bg` | `{palette_values['canvas']}` | 源页像素采样 |
| `--canvas-dark` | `{palette_values['dark']}` | 源页像素采样 |
| `--ink-primary` | `{palette_values['ink']}` | 文字颜色统计 |
| `--ink-secondary` | `{palette_values['ink_secondary']}` | 文字颜色统计 |
| `--accent-1` / 2 / 3 | `{palette_values['accent'][0]}` / `{palette_values['accent'][1]}` / `{palette_values['accent'][2]}` | 强调色统计 |
| `--font-sans` | `{font}` | 源母版字体族 |
| 字阶 | display {sizes[0]}px / headline {sizes[1]}px / body {sizes[2]}px / caption {sizes[3]}px | 字号分布 |

## 二、画布与安全区

- 画布：{TARGET_W} × {TARGET_H}
- 安全边距：x = {margins[0]}px，y = {margins[1]}px（取源母版占位符的最小正值）
- 占位符几何见下表；槽位坐标是源 layout 的实际几何，不是目测。

## 三、版式目录

| primitive | 名称 | 源使用次数 | 源 layout | 源页 | 源页内容框 | layout_id |
| :--- | :--- | ---: | :--- | :--- | :--- | :--- |
{rows}

每个版式的槽位：

{chr(10).join(f"- **{record['name']}**：{slots_text(record['slots'])}" for record in records)}

## 四、待补

- 设计哲学与“不要做”的红线；
- 每个家族适合的叙事任务与内容密度；
- `skyline_shell.svg` 目前只是画布 + 安全区线，替换成真实底壳；
- `primitives/` 为空：按槽位与代表源页，为每个版式制作 1 个可渲染 primitive；
- 用真实内容试做后，把验证结果写回本文件。
"""


def shell_svg(margins):
    top, bottom = margins[1], TARGET_H - margins[1]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{TARGET_W}" height="{TARGET_H}" viewBox="0 0 {TARGET_W} {TARGET_H}">
  <rect width="{TARGET_W}" height="{TARGET_H}" fill="var(--canvas-bg, #FFFFFF)"/>
  <g data-scaffold="shell" stroke="var(--border-line, #D8E0EC)" stroke-width="1">
    <line x1="0" y1="{top}" x2="{TARGET_W}" y2="{top}"/>
    <line x1="0" y1="{bottom}" x2="{TARGET_W}" y2="{bottom}"/>
  </g>
</svg>
"""


def _thumbnail(source, destination, size):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail(size)
        image.save(destination, "PNG")
    return destination


def scaffold(project, force=False, families=None, limit=0, include_unused=False):
    project = Path(project).resolve()
    pack = project / "_internal" / "00_project" / "template_pack"
    facts = read_json(pack / "extraction_facts.json", {}) or {}
    catalog = read_json(pack / "layout_catalog.json", {}) or {}
    if not catalog.get("families"):
        raise ValueError("layout_catalog.json is missing; run extract_template_pack.py on a .pptx first")
    chosen = selected_families(catalog, only=families, limit=limit, include_unused=include_unused)
    if not chosen:
        raise ValueError("no layout family selected")
    records = layout_records(catalog, chosen, pack)
    margins = safe_margins(catalog)
    palette_values = palette(facts)
    sizes = type_sizes(facts)
    font = font_stack(facts)
    source_name = Path(str(facts.get("source_file") or catalog.get("source") or project.name)).stem

    written = []
    if write_text(pack / "tokens.css", tokens_css(palette_values, sizes, margins, font), force):
        written.append("tokens.css")
    if write_text(pack / "SPEC.md", spec_markdown(source_name, facts, catalog, records, palette_values, sizes, margins, font), force):
        written.append("SPEC.md")
    if write_text(pack / "skyline_shell.svg", shell_svg(margins), force):
        written.append("skyline_shell.svg")
    layouts_document = {
        "schema": "planner.template-layouts.v1",
        "canvas": {"width": TARGET_W, "height": TARGET_H},
        "source": {"file": facts.get("source_file") or catalog.get("source"), "families": len(records)},
        "layouts": records,
    }
    if write_text(pack / "layouts.json", json.dumps(layouts_document, ensure_ascii=False, indent=2) + "\n", force):
        written.append("layouts.json")

    visuals = Path(facts.get("visuals_dir") or (project / "_internal" / "00_project" / "template_visuals"))
    copied = 0
    missing = []
    for record in records:
        page = int(record.get("representative_page") or 0)
        source = visuals / f"page_{page:03d}.png"
        if not page or not source.is_file():
            missing.append(record["layout_id"])
            record["preview"] = ""
            record["anchor"] = ""
            continue
        _thumbnail(source, pack / record["preview"], (640, 360))
        _thumbnail(source, pack / record["anchor"], (1280, 720))
        copied += 1
    (pack / "layouts.json").write_text(json.dumps(layouts_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "pack": str(pack),
        "layouts": len(records),
        "written": written,
        "previews": copied,
        "missing_previews": missing,
        "margins": margins,
        "palette": palette_values,
    }


def main():
    parser = argparse.ArgumentParser(description="Scaffold tokens/SPEC/shell/layouts from a PPTX layout catalog")
    parser.add_argument("--project", required=True)
    parser.add_argument("--force", action="store_true", help="Overwrite tokens/SPEC/shell/layouts if they exist")
    parser.add_argument("--families", default="", help="Comma-separated family ids (default: all)")
    parser.add_argument("--max-layouts", type=int, default=0, help="Keep only the N most-used families")
    parser.add_argument("--include-unused", action="store_true", help="Also scaffold layouts not used by any slide")
    args = parser.parse_args()
    families = [item.strip() for item in args.families.split(",") if item.strip()]
    try:
        result = scaffold(args.project, force=args.force, families=families, limit=args.max_layouts,
                          include_unused=args.include_unused)
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
