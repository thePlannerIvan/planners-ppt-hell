#!/usr/bin/env python3
"""Template layout index：把一套模板包读成「可选的版式」列表。

模板包有两种格式，版式索引在这里收成一个形状：

  · 四件套 v2 —— 每个 `primitives/*.svg` 是一个版式；缩略图优先取
    `previews/pages/<stem>.png`（内置包），再取 `previews/<stem>.png`（dark-titanium 那种），
    最后取 `anchors/<stem>.png`。
  · legacy fidelity —— `fidelity_template/template_registry.json` 的 layouts 是版式；
    缩略图取 `fidelity_template/canvas_previews/pages/<layout_id>.png`。
    传项目 `_internal/00_project` 或库包根都可以，两种根都能找到 registry。

这个模块只做**读**：不改包、不算哈希、不写缩略图。工作台画廊与模板审阅都从这里取版式，
页面执行时再按 `primitive` 指向的 SVG 看具体构图。

版式索引不是模板契约的替代品：它只是「这一套模板能选哪些页」的目录。
"""

import argparse
import json
import re
from pathlib import Path


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def pack_format(root):
    """`four-piece` / `fidelity` / ''。只按目录事实判断，不看 manifest 的 schema 字符串。"""
    root = Path(root)
    if (root / "primitives").is_dir() and any((root / "primitives").glob("*.svg")):
        return "four-piece"
    if fidelity_dir(root) is not None:
        return "fidelity"
    return ""


def fidelity_dir(root):
    """fidelity registry 所在目录：库包是 `fidelity_template/`，项目里是 `_internal/00_project/fidelity_template/`。"""
    root = Path(root)
    for candidate in (root / "fidelity_template", root):
        if (candidate / "template_registry.json").is_file():
            return candidate
    return None


def short_number(layout_id):
    match = re.match(r"^p(\d{1,3})_", str(layout_id))
    return match.group(1).lstrip("0") or "0" if match else ""


def layout_name(layout_id):
    """给人看的短名：去掉 `pNN_` 前缀，下划线换空格，英文词首字母大写。

    不猜中文名：包里没有名字时，编一个中文名比显示英文更容易误导人。
    包以后带 `layouts.json` 时，名字由那份索引给。
    """
    value = re.sub(r"^p\d{1,3}_", "", str(layout_id))
    value = re.sub(r"(?<=\d)_(?=\d)", ":", value)
    words = [word for word in re.split(r"[_\s]+", value) if word]
    named = []
    for word in words:
        if re.fullmatch(r"\d+x\d+", word):
            named.append(word.replace("x", "×"))
        elif word.isupper():
            named.append(word)
        else:
            named.append(word[:1].upper() + word[1:])
    return " ".join(named) or str(layout_id)


def _first_existing(pack, relatives):
    for relative in relatives:
        path = Path(pack) / relative
        if path.is_file():
            return relative
    return ""


def four_piece_layouts(pack):
    pack = Path(pack)
    layouts = []
    for primitive in sorted((pack / "primitives").glob("*.svg")):
        stem = primitive.stem
        preview = _first_existing(pack, [
            f"previews/pages/{stem}.png",
            f"previews/{stem}.png",
            f"anchors/{stem}.png",
        ])
        layouts.append({
            "layout_id": stem,
            "name": layout_name(stem),
            "number": short_number(stem),
            "preview": preview,
            "primitive": primitive.relative_to(pack).as_posix(),
        })
    return layouts


def fidelity_layouts(root):
    root = Path(root)
    fidelity = fidelity_dir(root)
    if fidelity is None:
        return []
    registry = read_json(fidelity / "template_registry.json", {})
    prefix = ""
    if fidelity != root:
        prefix = fidelity.relative_to(root).as_posix() + "/"
    layouts = []
    for layout_id, layout in (registry.get("layouts") or {}).items():
        canvas = str(layout.get("canvas_file") or "")
        preview = ""
        for relative in (f"canvas_previews/pages/{layout_id}.png", f"canvas_previews/{layout_id}.png"):
            if (fidelity / relative).is_file():
                preview = prefix + relative
                break
        layouts.append({
            "layout_id": str(layout_id),
            "name": layout_name(layout_id),
            "number": short_number(layout_id),
            "preview": preview,
            "primitive": (prefix + canvas) if canvas else "",
        })
    return layouts


def declared_layouts(root):
    """包自己声明的版式索引（`layouts.json`）。脚手架与人工策展都写这一份。

    只读、只取存在的预览/primitive；`available` 表示这一条现在能不能真的当参考用。
    """
    root = Path(root)
    document = read_json(root / "layouts.json", {})
    items = document.get("layouts") if isinstance(document, dict) else None
    if not isinstance(items, list) or not items:
        return []
    layouts = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        layout_id = str(item.get("layout_id") or "").strip()
        if not layout_id:
            continue
        preview = str(item.get("preview") or "")
        primitive = str(item.get("primitive") or "")
        preview = preview if preview and (root / preview).is_file() else ""
        primitive = primitive if primitive and (root / primitive).is_file() else ""
        layouts.append({
            "layout_id": layout_id,
            "name": str(item.get("name") or layout_name(layout_id)),
            "number": str(index),
            "preview": preview,
            "primitive": primitive,
            "family": str(item.get("family") or ""),
            "use_for": str(item.get("use_for") or ""),
            "usage": item.get("usage") or 0,
            "source_pages": item.get("source_pages") or [],
            "source_layouts": item.get("source_layouts") or [],
            "slots": item.get("slots") or [],
            "selected": item.get("selected") is not False,
            "available": bool(preview or primitive),
        })
    return layouts


def pack_layouts(root):
    """一套包的版式列表。包不可识别时返回空列表，不抛异常。

    优先读包自己声明的 `layouts.json`；旧包没有它时，按原语/legacy registry 派生。
    """
    declared = declared_layouts(root)
    if declared:
        return declared
    kind = pack_format(root)
    if kind == "four-piece":
        return four_piece_layouts(root)
    if kind == "fidelity":
        return fidelity_layouts(root)
    return []


def main():
    parser = argparse.ArgumentParser(description="Read a template pack's layout index")
    parser.add_argument("pack_dir")
    args = parser.parse_args()
    result = {
        "pack_dir": str(Path(args.pack_dir).resolve()),
        "format": pack_format(args.pack_dir),
        "layouts": pack_layouts(args.pack_dir),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
