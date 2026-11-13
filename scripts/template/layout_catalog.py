#!/usr/bin/env python3
"""PPTX layout catalog：把母版里的版式目录读成可生产的数据。

提取脚本原来只产出渲染页与颜色/字号聚合，把 PPTX 里最结构化的东西扔掉了：
master、layout、占位符名称与几何、每一页用了哪个版式。这里把那些读出来，
写成 `layout_catalog.json`：

  · `layouts`  —— 每个源 layout 一条：名称、master/layout 序号、占位符槽位、使用页；
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


def write_catalog(project, catalog):
    path = Path(project) / "_internal" / "00_project" / "template_pack" / "layout_catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Read a PPTX master/layout catalog")
    parser.add_argument("source", help="Path to .pptx")
    parser.add_argument("--project", required=True, help="Project root to write layout_catalog.json into")
    args = parser.parse_args()
    catalog = catalog_from_pptx(args.source)
    path = write_catalog(args.project, catalog)
    print(json.dumps({
        "catalog": str(path),
        "layouts": len(catalog["layouts"]),
        "families": len(catalog["families"]),
        "slides": catalog["slide_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
