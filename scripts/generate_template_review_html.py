#!/usr/bin/env python3
"""Generate the template review page using the unified review workbench.

模板审阅复用 `assets/review/review.html` 工作台组件，保持与页面审阅一致的
左侧缩略图轨、中央 SVG 预览、右侧反馈与处理决定、顶部工具栏与 DSH 设计令牌，
实现统一的人工审阅体验。
"""
import argparse
import html
import json
import re
import shlex
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from project_state import PROJECT, TEMPLATE_REVIEW_SNAPSHOT, sha, template_version, write
from review_surface import resolve_module

ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')

MEDIA_PREFIX = '_internal/00_project/template_media/'
VISUALS_PREFIX = '_internal/00_project/template_visuals/'


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def esc(value):
    return html.escape(str(value or ""), quote=True)


MEDIA_HREF = re.compile(r"""(xlink:href|href)\s*=\s*(["'])(?:\.\./\.\./template_media/)([^"']+)\2""")
IMAGE_TAG = re.compile(r"<image\b[^>]*>")


def inline_canvas(path):
    """把 canvas SVG 内联进页面，并把里面的素材引用改成相对地址。"""
    text = MEDIA_HREF.sub(lambda m: f'{m.group(1)}={m.group(2)}{MEDIA_PREFIX}{m.group(3)}{m.group(2)}',
                          path.read_text(encoding="utf-8"))

    def tag(match):
        tag_text = match.group(0)
        already = MEDIA_HREF.search(tag_text)
        if not already or 'data-asset=' in tag_text:
            return tag_text
        return tag_text[:-1] + f' data-asset="{MEDIA_PREFIX}{already.group(3)}">'
    return IMAGE_TAG.sub(tag, text)


def inline_pack_canvas(root, path, tokens=''):
    tree = ET.parse(path).getroot()
    if not tree.get('viewBox'):
        w = tree.get('width') or '1920'
        h = tree.get('height') or '1080'
        tree.set('viewBox', f'0 0 {w} {h}')
    if tokens:
        # 作用域限定：将 :root 替换为 svg，避免污染外层工作台宿主 DOM
        scoped_tokens = tokens.replace(':root', 'svg')
        style = ET.Element('{http://www.w3.org/2000/svg}style')
        style.text = scoped_tokens
        tree.insert(0, style)
    for node in tree.iter():
        if node.tag.split('}')[-1] != 'image':
            continue
        attr = 'href' if 'href' in node.attrib else '{http://www.w3.org/1999/xlink}href'
        href = node.get(attr, '')
        if href.startswith('data:') or href.startswith('http'):
            continue
        target = (path.parent / href).resolve()
        if root not in target.parents or not target.is_file():
            raise ValueError('Template image must resolve inside project: ' + href)
        rel = target.relative_to(root).as_posix()
        node.set(attr, rel)
        node.set('data-asset', rel)
        node.set('data-project-rel', rel)
        node.set('data-project-ver', sha(target)[:12])
    return ET.tostring(tree, encoding='unicode')


def layout_title(identity):
    stem = Path(identity).stem
    names = {
        'skyline_shell': 'Skyline Shell (基底板)',
        'p01_cover_dark': 'P01 深色封面',
        'p02_cover_white': 'P02 浅色封面',
        'p03_content_split': 'P03 左右对称对比',
        'p04_data_cards': 'P04 数据指标卡片',
        'p05_three_pillars': 'P05 三列立柱框架',
        'p06_chapter_divider': 'P06 章节过渡页',
    }
    if stem in names:
        return names[stem]
    return stem.replace('_', ' ').title()


def assemble_review_html(data):
    tpl_file = Path(__file__).resolve().parents[1] / 'assets/review/review.html'
    template = tpl_file.read_text(encoding='utf-8')
    tokens = (resolve_module('planners-review-core') / 'assets' / 'dsh-tokens.css').read_text(encoding='utf-8')
    review_ui = json.loads(subprocess.check_output([
        'node', str(resolve_module('planners-review-core') / 'scripts/review-ui.mjs')], text=True))
    html_text = template.replace('__DSH_TOKENS__', tokens)
    html_text = html_text.replace('__REVIEW_UI__', review_ui['css'])
    html_text = html_text.replace('__REVIEW_UI_SCRIPT__', review_ui['script'].replace('</script', '<\\/script'))
    tools = tpl_file.with_name('workbench-tools.js').read_text(encoding='utf-8')
    html_text = html_text.replace('__WORKBENCH_TOOLS__', tools.replace('</script', '<\\/script'))
    html_text = html_text.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    return html_text


def generate_layout_pack_review(root, pack, tokens, declared_layouts):
    """有 `layouts.json` 的包：按版式（不是 shell + primitive 路径）审阅。

    版式条目的 key 是 layout_id；每个 primitive 必须是已经做好的文件，否则审阅页没有可看的实现。
    """
    records = [item for item in declared_layouts(pack) if item.get('selected', True)]
    if not records:
        raise ValueError('layouts.json has no selected layouts')
    pages = []
    for record in records:
        primitive = pack / str(record.get('primitive') or '')
        if not str(record.get('primitive') or '') or not primitive.is_file():
            raise ValueError(f"layout {record['layout_id']} has no authored primitive; make primitives/ before review")
        relative_primitive = primitive.resolve().relative_to(pack.resolve())
        markup = inline_pack_canvas(root, primitive, tokens)
        preview = str(record.get('preview') or '')
        png = f'{PROJECT}/template_pack/{preview}' if preview and (pack / preview).is_file() else ''
        source_pages = record.get('source_pages') or []
        source_names = '、'.join(
            str(item.get('name') or '') for item in record.get('source_layouts') or [] if item.get('name'))
        pages.append({
            'key': record['layout_id'],
            'title': record['name'],
            'png': png,
            'svg': f'{PROJECT}/template_pack/{relative_primitive.as_posix()}',
            'svgMarkup': markup,
            'revision': 1,
            'version': sha(primitive)[:12],
            'notes': f"{record.get('use_for') or ''}\n源使用 {record.get('usage', 0)} 页：{', '.join(str(page) for page in source_pages[:10]) or '—'}\n源版式：{source_names or '—'}",
            'assets': [],
            'family': record.get('family') or '',
            'usage': record.get('usage') or 0,
        })
    manifest = load(pack / 'manifest.json')
    template_name = manifest.get('name') or root.name
    version = template_version(root)
    review_id = uuid.uuid4().hex
    data = {
        'project': template_name,
        'template_name': template_name,
        'review_id': review_id,
        'snapshot': f'{PROJECT}/{TEMPLATE_REVIEW_SNAPSHOT}',
        'order': [page['key'] for page in pages],
        'workbench_root': str(root),
        'route': 'template',
        'local_fallback_command': f'python3 {shlex.quote(str(Path(__file__).with_name("review_surface.py")))} {shlex.quote(str(root))} --face template',
        'pages': pages,
    }
    out = root / '00_template_review.html'
    out.write_text(assemble_review_html(data), encoding='utf-8')
    write(root / PROJECT / TEMPLATE_REVIEW_SNAPSHOT,
          {'review_id': review_id, 'template_version': version, 'html_sha256': sha(out),
           'layouts': data['order'], 'package_format': 'four_piece_layouts'})
    return out


def generate_pack_review(root):
    from template.template_library import validate_pack_dir
    from template.layout_index import declared_layouts
    pack = root / PROJECT / 'template_pack'
    validation = validate_pack_dir(pack)
    if not validation['valid']:
        raise ValueError('Incomplete template pack: ' + str(validation['issues']))
    tokens = (pack / 'tokens.css').read_text(encoding='utf-8') if (pack / 'tokens.css').is_file() else ''
    if (pack / 'layouts.json').is_file():
        return generate_layout_pack_review(root, pack, tokens, declared_layouts)
    paths = [pack / 'skyline_shell.svg', *sorted((pack / 'primitives').glob('*.svg'))]
    layouts = [path.relative_to(pack).as_posix() for path in paths]

    manifest = load(pack / 'manifest.json')
    template_name = manifest.get('name') or root.name

    anchors = sorted((pack / 'anchors').glob('*.png'))
    anchor_map = {}
    for i, p in enumerate(paths):
        stem = p.stem
        direct_anchor = pack / 'anchors' / f'{stem}.png'
        if direct_anchor.is_file():
            anchor_map[p] = direct_anchor.relative_to(root).as_posix()
        elif i < len(anchors):
            anchor_map[p] = anchors[i].relative_to(root).as_posix()
        else:
            anchor_map[p] = ''

    pages = []
    for path, identity in zip(paths, layouts):
        v = sha(path)[:12]
        markup = inline_pack_canvas(root, path, tokens)
        pages.append({
            'key': identity,
            'title': layout_title(identity),
            'png': anchor_map.get(path, ''),
            'svg': path.relative_to(root).as_posix(),
            'svgMarkup': markup,
            'revision': 1,
            'version': v,
            'notes': f'模板原语: {identity}\n规范与约束见 SPEC.md',
            'assets': [],
        })

    version = template_version(root)
    review_id = uuid.uuid4().hex
    data = {
        'project': template_name,
        'template_name': template_name,
        'review_id': review_id,
        'snapshot': f'{PROJECT}/{TEMPLATE_REVIEW_SNAPSHOT}',
        'order': layouts,
        'workbench_root': str(root),
        'route': 'template',
        'local_fallback_command': f'python3 {shlex.quote(str(Path(__file__).with_name("review_surface.py")))} {shlex.quote(str(root))} --face template',
        'pages': pages,
    }

    out = root / '00_template_review.html'
    out.write_text(assemble_review_html(data), encoding='utf-8')
    write(root / PROJECT / TEMPLATE_REVIEW_SNAPSHOT,
          {'review_id': review_id, 'template_version': version, 'html_sha256': sha(out),
           'layouts': layouts, 'package_format': 'four_piece'})
    return out


def generate_fidelity_review(root):
    project = root / "_internal" / "00_project"
    registry = load(project / "fidelity_template" / "template_registry.json")
    profile = load(project / "template_profile.json")
    assets = load(project / "template_asset_registry.json")
    visual_manifest = load(project / "template_visuals" / "visual_manifest.json")
    if not profile or not assets or not registry.get("layouts"):
        raise SystemExit("template review requires profile, asset registry, and fidelity registry")

    page_images = {int(x["page"]): x.get("image", f"page_{int(x['page']):03d}.png")
                   for x in visual_manifest.get("pages", []) if isinstance(x, dict) and x.get("page")}

    layout_ids = list(registry["layouts"])
    template_name = profile.get("template_name") or root.name
    pages = []
    for index, layout_id in enumerate(layout_ids, 1):
        layout = registry["layouts"][layout_id]
        canvas = project / "fidelity_template" / str(layout.get("canvas_file", ""))
        if not canvas.is_file():
            raise SystemExit(f"missing Builder canvas: {canvas}")
        markup = inline_canvas(canvas)
        v = sha(canvas)[:12]

        png_path = ''
        if index in page_images and (project / "template_visuals" / page_images[index]).is_file():
            png_path = f"{VISUALS_PREFIX}{page_images[index]}"

        usage = "默认开放内容页" if layout_id == "content_base" else (
            "仅在内容关系精确匹配时使用" if layout_id.startswith(("content_", "data_", "two_column_", "process_", "funnel_", "compare_"))
            else "核心功能页")

        pages.append({
            'key': layout_id,
            'title': f'{index}. {layout_id}',
            'png': png_path,
            'svg': canvas.relative_to(root).as_posix(),
            'svgMarkup': markup,
            'revision': 1,
            'version': v,
            'notes': f'{usage}\nRequired: {", ".join(layout.get("required_components", []))}\nOptional: {", ".join(layout.get("optional_components", []))}',
            'assets': [],
        })

    version = template_version(root)
    review_id = uuid.uuid4().hex
    data = {
        'project': template_name,
        'template_name': template_name,
        'review_id': review_id,
        'snapshot': f'{PROJECT}/{TEMPLATE_REVIEW_SNAPSHOT}',
        'order': layout_ids,
        'workbench_root': str(root),
        'route': 'template',
        'local_fallback_command': f'python3 {shlex.quote(str(Path(__file__).with_name("review_surface.py")))} {shlex.quote(str(root))} --face template',
        'pages': pages,
    }

    out = root / "00_template_review.html"
    out.write_text(assemble_review_html(data), encoding="utf-8")
    write(project / TEMPLATE_REVIEW_SNAPSHOT,
          {"review_id": review_id, "template_version": version, "html_sha256": sha(out),
           "layouts": layout_ids})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    project = root / "_internal" / "00_project"
    if (project / 'template_pack').is_dir():
        print(generate_pack_review(root))
        return
    print(generate_fidelity_review(root))


if __name__ == "__main__":
    main()
