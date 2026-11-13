#!/usr/bin/env python3
"""版式选择页：从源 PPTX 的 layout 目录里勾选要收进模板的家族。

这是**生产范围**的决定，不是模板批准。产物是 `layout_selection.json`；模型据此只做被选中的
primitive，最终模板仍走 `00_template_review.html` 的逐版式批准。

页面复用审阅工作台的左轨/画布/侧栏；route='template-select' 时只显示源页与「收进模板」开关。
"""

import argparse
import json
import shlex
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'template'))
from generate_template_review_html import assemble_review_html  # noqa: E402
from project_state import PROJECT, read, sha, write  # noqa: E402
from scaffold_template_pack import USE_FOR  # noqa: E402

SNAPSHOT = 'template_select_snapshot.json'
ENTRY = '00_template_select.html'


def slot_svg(slots):
    """版式骨架图：矩形 + 角色标签。选择页看结构，源页看内容。"""
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">',
             '<rect width="1920" height="1080" fill="#FFFFFF"/>']
    for slot in slots or []:
        try:
            x, y, width, height = (float(slot[key]) for key in ('x', 'y', 'width', 'height'))
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        role = str(slot.get('role') or 'other')
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="4" '
            f'fill="rgba(0,82,217,.08)" stroke="var(--dsw-static-blue-500)" stroke-width="3"/>')
        parts.append(
            f'<text x="{x + 12}" y="{y + 30}" font-family="Arial, sans-serif" font-size="24" '
            f'fill="#1F2937">{role}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def _family_notes(family, catalog):
    pages = family.get('source_pages') or []
    page_text = '、'.join(str(page) for page in pages[:10]) or '—'
    slots = '；'.join(
        f"{slot.get('role')} {slot.get('x')}/{slot.get('y')}/{slot.get('width')}/{slot.get('height')}"
        for slot in family.get('slots') or []) or '—'
    names = '、'.join(family.get('layout_names') or []) or '—'
    return (f"适用：{USE_FOR.get(family.get('family'), '其他结构')}\n"
            f"源使用：{family.get('usage', 0)} 页（{page_text}）\n"
            f"源版式：{names}\n"
            f"槽位：{slots}")


def generate(root):
    root = Path(root).resolve()
    project = root / PROJECT
    pack = project / 'template_pack'
    catalog_path = pack / 'layout_catalog.json'
    catalog = read(catalog_path, {})
    families = [item for item in catalog.get('families') or [] if int(item.get('usage') or 0) > 0]
    if not families:
        raise ValueError('layout_catalog.json has no used families; run extract_template_pack.py on a .pptx first')
    previous = read(project / 'layout_selection.json', {})
    chosen = set((previous.get('families') or {}).keys()) if previous.get('families') else set()
    has_previous = bool(previous.get('families'))
    visuals = root / PROJECT / 'template_visuals'
    declared = read(pack / 'layouts.json', {})
    previews = {
        str(item.get('layout_id')): f"{PROJECT}/template_pack/{item.get('preview')}"
        for item in declared.get('layouts') or []
        if isinstance(item, dict) and item.get('preview') and (pack / str(item.get('preview'))).is_file()
    }

    order = []
    pages = []
    for item in families:
        family = str(item.get('family') or '')
        page = int(item.get('representative_page') or 0)
        preview = ''
        version = 'catalog'
        if previews.get(family):
            preview = previews[family]
            version = sha(root / preview)[:12]
        elif page and (visuals / f'page_{page:03d}.png').is_file():
            preview = f'{PROJECT}/template_visuals/page_{page:03d}.png'
            version = sha(root / preview)[:12]
        order.append(family)
        pages.append({
            'key': family,
            'title': item.get('label') or family,
            'png': preview,
            'svg': '',
            'svgMarkup': slot_svg(item.get('slots') or []),
            'revision': 1,
            'version': version,
            'notes': _family_notes(item, catalog),
            'assets': [],
            'selected': (family in chosen) if has_previous else True,
            'family': family,
            'usage': item.get('usage') or 0,
            'source_pages': item.get('source_pages') or [],
            'slots': item.get('slots') or [],
        })

    review_id = uuid.uuid4().hex
    data = {
        'project': Path(str(catalog.get('source') or root.name)).stem,
        'source': catalog.get('source') or '',
        'review_id': review_id,
        'catalog_sha256': sha(catalog_path) if catalog_path.is_file() else '',
        'order': order,
        'workbench_root': str(root),
        'route': 'template-select',
        'local_fallback_command': f'python3 {shlex.quote(str(Path(__file__).with_name("review_surface.py")))} '
                                  f'{shlex.quote(str(root))} --face select',
        'pages': pages,
    }
    out = root / ENTRY
    out.write_text(assemble_review_html(data), encoding='utf-8')
    write(project / SNAPSHOT, {
        'review_id': review_id,
        'catalog_sha256': data['catalog_sha256'],
        'families': order,
        'html_sha256': sha(out),
    })
    return out


def main():
    parser = argparse.ArgumentParser(description='Generate the layout selection page from layout_catalog.json')
    parser.add_argument('project_dir')
    args = parser.parse_args()
    print(generate(args.project_dir))


if __name__ == '__main__':
    main()
