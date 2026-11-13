#!/usr/bin/env python3
"""Layout catalog：把 PPTX 母版或 PDF 页读成可生产的版式目录。

提取脚本原来只产出渲染页与颜色/字号聚合，把 PPTX 里最结构化的东西扔掉了：
master、layout、占位符名称与几何、每一页用了哪个版式。这里把那些读出来，
写成 `layout_catalog.json`：

  · `layouts`  —— 每个源 layout 一条：名称、master/layout 序号、占位符槽位、使用页；
                PDF 没有母版，按文字/图片块推测结构家族，槽位来自代表页。
  · `families` —— 按结构家族归并（封面 / 章节分隔 / 三栏 / 大图 …），供脚手架收版式；
  · `pages`    —— 每一页用了哪个版式，以及占位符之外的内容框（文字/图/表/图表）。

单位统一到 1920×1080。只读源文件，不写图、不改 pack；脚手架拿它生成 tokens/SPEC/layouts.json。
"""

import argparse
import json
import re
from pathlib import Path

TARGET_W, TARGET_H = 1920.0, 1080.0

ROLE_BY_PLACEHOLDER = {
    "TITLE": "title",
    "CENTER_TITLE": "title",
    "SUBTITLE": "subtitle",
    "BODY": "body",
    "OBJECT": "body",
    "PICTURE": "image",
    "FOOTER": "footer",
    "SLIDE_NUMBER": "page_number",
    "DATE": "date",
    "HEADER": "header",
}

# 顺序有意义：先判结构更具体的，再落到封面/单栏。
FAMILY_RULES = (
    ("divider", "章节分隔", ("divider", "section header", "section")),
    ("full_bleed", "全幅图", ("fullblead", "full bleed", "fullbleed")),
    ("contact", "联系页", ("contact",)),
    ("quote", "引语", ("quote",)),
    ("blank", "空白/自由", ("blank",)),
    ("chart", "图表/数据", ("chart",)),
    ("three_columns", "三栏", ("3 column", "three column")),
    ("two_columns", "双栏", ("two content", "comparison", "two column", "2 column")),
    ("one_column", "单栏", ("title and content", "content with caption", "one column", "1 column")),
    ("large_image", "大图 + 文字", ("picture with caption", "large image", "images and text")),
    ("split", "左右分栏", ("side by side",)),
    ("headline_only", "标题 + 顶线", ("title only", "headline", "topline")),
    ("cover", "封面", ("title slide", "title")),
)

def _num(value):
    return None if value is None else float(value)


def _box(shape, sx, sy):
    return {
        "x": round(_num(shape.left) * sx, 1) if shape.left is not None else None,
        "y": round(_num(shape.top) * sy, 1) if shape.top is not None else None,
        "width": round(_num(shape.width) * sx, 1) if shape.width is not None else None,
        "height": round(_num(shape.height) * sy, 1) if shape.height is not None else None,
    }


def placeholder_role(placeholder_type):
    name = str(placeholder_type).split("(")[0].strip() if placeholder_type is not None else ""
    return ROLE_BY_PLACEHOLDER.get(name, "other")


def family_of(layout_name):
    name = str(layout_name or "").lower()
    for family, label, needles in FAMILY_RULES:
        if any(needle in name for needle in needles):
            return family, label
    return "other", "其他"


def _truthy_text(shape):
    if not getattr(shape, "has_text_frame", False):
        return ""
    return str(shape.text_frame.text or "").strip()


def _shape_kind(shape):
    if shape.shape_type == 13:
        return "image"
    if shape.shape_type == 3:
        return "chart"
    if shape.shape_type == 19:
        return "table"
    if getattr(shape, "has_text_frame", False) and _truthy_text(shape):
        return "text"
    return "shape"


def _slide_text_length(slide):
    return sum(len(_truthy_text(shape)) for shape in slide.shapes)


def _slide_layout_key(slide):
    layout = slide.slide_layout
    return getattr(getattr(layout, "part", None), "partname", None)


def catalog_from_pptx(source_path):
    """读一个 .pptx，返回 layout 目录 + 家族归并 + 页映射。不依赖渲染页。"""
    from pptx import Presentation  # 延迟导入：模块的纯函数不依赖 pptx

    source_path = Path(source_path).resolve()
    prs = Presentation(str(source_path))
    sx = TARGET_W / float(prs.slide_width or 1)
    sy = TARGET_H / float(prs.slide_height or 1)

    # 先按 partname 建立 layout 索引；slide 再按同一个 partname 回指。
    entries = []
    by_part = {}
    for master_index, master in enumerate(prs.slide_masters, start=1):
        for layout_index, layout in enumerate(master.slide_layouts, start=1):
            source_id = f"m{master_index}_l{layout_index}"
            family, label = family_of(layout.name)
            slots = []
            for shape in layout.shapes:
                if not shape.is_placeholder:
                    continue
                slot = {
                    "role": placeholder_role(shape.placeholder_format.type),
                    "type": str(shape.placeholder_format.type).split("(")[0].strip(),
                    **_box(shape, sx, sy),
                }
                slots.append(slot)
            entry = {
                "source_id": source_id,
                "master": master_index,
                "layout": layout_index,
                "name": str(layout.name or source_id),
                "family": family,
                "family_label": label,
                "usage": 0,
                "source_pages": [],
                "slots": slots,
                "slot_signature": [
                    [slot["role"], slot["x"], slot["y"], slot["width"], slot["height"]] for slot in slots
                ],
                "representative_page": 0,
            }
            part = getattr(getattr(layout, "part", None), "partname", None)
            if part is not None:
                by_part[part] = entry
            entries.append(entry)

    pages = []
    for page_index, slide in enumerate(prs.slides, start=1):
        key = _slide_layout_key(slide)
        layout_entry = by_part.get(key)
        source_id = layout_entry["source_id"] if layout_entry else ""
        family = layout_entry["family"] if layout_entry else "other"
        if layout_entry is not None:
            layout_entry["usage"] += 1
            layout_entry["source_pages"].append(page_index)
        title = ""
        shapes = []
        for shape in slide.shapes:
            text = _truthy_text(shape)
            if shape.is_placeholder and shape.placeholder_format.type is not None:
                role = placeholder_role(shape.placeholder_format.type)
                if role == "title" and not title:
                    title = text
                continue
            if shape.shape_type == 13:
                shapes.append({"kind": "image", **_box(shape, sx, sy)})
                continue
            if not text and _shape_kind(shape) not in ("chart", "table"):
                continue
            shapes.append({
                "kind": _shape_kind(shape),
                "text": text[:80],
                **_box(shape, sx, sy),
            })
        pages.append({
            "page": page_index,
            "layout": source_id,
            "family": family,
            "title": title[:80],
            "shapes": shapes[:24],
        })

    # 代表页：用这个 layout 的页里，文字最多的那一页（比第一页更像真实示例）。
    for entry in entries:
        used = entry["source_pages"]
        if used:
            # 第一页使用它的页作代表：版式预览要展示「槽位骨架 + 典型内容」，
            # 按文字量挑会把一页满是自定义图的页面推到「纯标题」家族上。
            entry["representative_page"] = used[0]

    families = []
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry["family"], []).append(entry)
    for family, members in grouped.items():
        members.sort(key=lambda item: (-item["usage"], item["master"], item["layout"]))
        representative = members[0]
        pages_used = sorted({page for item in members for page in item["source_pages"]})
        families.append({
            "family": family,
            "label": representative["family_label"],
            "usage": sum(item["usage"] for item in members),
            "layout_ids": [item["source_id"] for item in members],
            "layout_names": [item["name"] for item in members],
            "source_pages": pages_used[:30],
            "representative_layout": representative["source_id"],
            "representative_page": representative["representative_page"],
            "slots": representative["slots"],
        })
    families.sort(key=lambda item: (-item["usage"], item["label"]))

    return {
        "schema": "planner.template-layout-catalog.v1",
        "source": str(source_path),
        "canvas": {"width": int(TARGET_W), "height": int(TARGET_H),
                   "source_width": int(prs.slide_width or 0), "source_height": int(prs.slide_height or 0)},
        "slide_count": len(prs.slides),
        "master_count": len(prs.slide_masters),
        "layouts": entries,
        "families": families,
        "pages": pages,
    }


PDF_FAMILY_LABELS = {
    "full_bleed": "全幅图",
    "large_image": "大图 + 文字",
    "blank": "空白/自由",
    "cover": "封面",
    "divider": "章节分隔",
    "three_columns": "三栏",
    "two_columns": "双栏",
    "one_column": "单栏",
}


def _pdf_blocks(page, sx, sy):
    """把 PDF 页读成文字/图片块；字体大小折算到 1080p。"""
    blocks = page.get_text("dict").get("blocks") or []
    items = []
    for block in blocks:
        bbox = block.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = (float(value) for value in bbox[:4])
        item = {
            "x": round(x0 * sx, 1),
            "y": round(y0 * sy, 1),
            "width": round(max(0.0, x1 - x0) * sx, 1),
            "height": round(max(0.0, y1 - y0) * sy, 1),
        }
        if item["width"] <= 0 or item["height"] <= 0:
            continue
        if block.get("type") == 0:
            text = " ".join(
                span.get("text", "") for line in block.get("lines") or [] for span in line.get("spans") or []
            ).strip()
            sizes = [float(span.get("size") or 0) for line in block.get("lines") or []
                     for span in line.get("spans") or []]
            if text:
                item.update(kind="text", text=text[:120], font_size=round(max(sizes or [0]) * sy, 1))
                items.append(item)
        elif block.get("type") == 1:
            item.update(kind="image")
            items.append(item)
    return items


def _pdf_columns(body_blocks):
    centers = [item["x"] + item["width"] / 2 for item in body_blocks
               if item.get("width", 0) < TARGET_W * 0.58]
    if len(centers) < 2:
        return 1
    left = sum(1 for value in centers if value < TARGET_W * 0.44)
    right = sum(1 for value in centers if value > TARGET_W * 0.56)
    middle = len(centers) - left - right
    if left and right and not middle:
        return 2
    if left and middle and right:
        return 3
    return 1


def _pdf_family(page_index, title, body_count, columns, image_ratio):
    if image_ratio >= 0.80:
        return "full_bleed"
    if image_ratio >= 0.30:
        return "large_image"
    if not title and not body_count:
        return "blank"
    if title and body_count == 0:
        return "cover" if page_index == 1 else "divider"
    if page_index == 1 and title and image_ratio <= 0.20:
        return "cover"
    if columns >= 3:
        return "three_columns"
    if columns == 2:
        return "two_columns"
    return "one_column"


def _pdf_page(page_index, page):
    page_width = float(page.rect.width or 1)
    page_height = float(page.rect.height or 1)
    sx, sy = TARGET_W / page_width, TARGET_H / page_height
    blocks = _pdf_blocks(page, sx, sy)
    text_blocks = [item for item in blocks if item["kind"] == "text"]
    image_blocks = [item for item in blocks if item["kind"] == "image"]
    image_ratio = min(1.0, sum(item["width"] * item["height"] for item in image_blocks) / (TARGET_W * TARGET_H))
    sizes = sorted((item.get("font_size", 0) for item in text_blocks if item.get("font_size", 0) > 0), reverse=True)
    second = sizes[1] if len(sizes) > 1 else 0
    title_block = max(text_blocks, key=lambda item: item.get("font_size", 0), default=None)
    if title_block is not None and second and title_block.get("font_size", 0) < second * 1.35:
        title_block = None
    body = [item for item in text_blocks if item is not title_block]
    columns = _pdf_columns(body)
    family = _pdf_family(page_index, bool(title_block), len(body), columns, image_ratio)
    subtitle_block = None
    if family in ("cover", "divider") and body:
        subtitle_block = max(body, key=lambda item: item.get("font_size", 0))
        body = [item for item in body if item is not subtitle_block]
    slots = []
    for item, role in [(title_block, "title"), (subtitle_block, "subtitle"),
                       *[(item, "body") for item in body], *[(item, "image") for item in image_blocks]]:
        if item is None:
            continue
        slots.append({"role": role, "x": item["x"], "y": item["y"],
                      "width": item["width"], "height": item["height"]})
    shapes = [
        {"kind": item["kind"], "role": role, "text": item.get("text", ""),
         "x": item["x"], "y": item["y"], "width": item["width"], "height": item["height"]}
        for item, role in [(title_block, "title"), (subtitle_block, "subtitle"),
                           *[(item, "body") for item in body], *[(item, "image") for item in image_blocks]]
        if item is not None
    ]
    title = (title_block.get("text") or "")[:80] if title_block else ""
    return {
        "page": page_index,
        "layout": family,
        "family": family,
        "title": title,
        "slots": slots,
        "shapes": shapes[:24],
    }


def catalog_from_pdf(source_path):
    """PDF 没有母版：按每页的文字/图片块推测结构家族，并生成可用的槽位。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as error:
        raise RuntimeError("PyMuPDF is required to catalog PDF layouts") from error
    source_path = Path(source_path).resolve()
    doc = fitz.open(str(source_path))
    pages = [_pdf_page(index, page) for index, page in enumerate(doc, start=1)]
    doc.close()

    grouped = {}
    for page in pages:
        grouped.setdefault(page["family"], []).append(page)
    ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    layouts = []
    families = []
    for index, (family, group) in enumerate(ordered, start=1):
        representative = group[0]
        label = PDF_FAMILY_LABELS.get(family, family)
        layout = {
            "source_id": family,
            "master": 0,
            "layout": index,
            "name": label,
            "family": family,
            "family_label": label,
            "usage": len(group),
            "source_pages": [page["page"] for page in group],
            "slots": representative["slots"],
            "slot_signature": [[slot["role"], slot["x"], slot["y"], slot["width"], slot["height"]]
                               for slot in representative["slots"]],
            "representative_page": representative["page"],
        }
        layouts.append(layout)
        families.append({
            "family": family,
            "label": label,
            "usage": len(group),
            "layout_ids": [family],
            "layout_names": [label],
            "source_pages": [page["page"] for page in group][:30],
            "representative_layout": family,
            "representative_page": representative["page"],
            "slots": representative["slots"],
        })
    return {
        "schema": "planner.template-layout-catalog.v1",
        "source": str(source_path),
        "source_kind": "pdf",
        "canvas": {"width": int(TARGET_W), "height": int(TARGET_H), "source_width": 0, "source_height": 0},
        "slide_count": len(pages),
        "master_count": 0,
        "layouts": layouts,
        "families": families,
        "pages": pages,
    }


def write_catalog(project, catalog):
    path = Path(project) / "_internal" / "00_project" / "template_pack" / "layout_catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Read a PPTX/PDF layout catalog")
    parser.add_argument("source", help="Path to .pptx or .pdf")
    parser.add_argument("--project", required=True, help="Project root to write layout_catalog.json into")
    args = parser.parse_args()
    catalog = catalog_from_pdf(args.source) if Path(args.source).suffix.lower() == ".pdf" else catalog_from_pptx(args.source)
    path = write_catalog(args.project, catalog)
    print(json.dumps({
        "catalog": str(path),
        "layouts": len(catalog["layouts"]),
        "families": len(catalog["families"]),
        "slides": catalog["slide_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
