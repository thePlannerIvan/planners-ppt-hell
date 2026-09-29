"""One actual-page review: the surface entry page, the surface contract, and the snapshot.

这一份产物是三件东西，一起生成、一起作废：

  · `02_visual_review.html` —— 审阅页（review-surface 的入口），里面留 `{{REVIEW_BRIDGE}}` 注入点；
  · `_internal/05_review/snapshot.json` —— 生成这一刻的版本快照（review_id + 每页版本 + PNG hash）；
  · `_internal/05_review/review-surface.json` —— 交给宿主的 surface（页面、目录、反馈文件、唤醒文案）。

页面里的资产一律走**相对 `dir`（＝项目根）的路径**，由页面向桥要 URL：`await review.asset(rel, {v})`。
所以这里给的是 `rel` 与 `version`，不是拼好的 URL。
同时注入每页的 `svgMarkup`（带确定性 `data-review-id` 树路径与隔离前缀 ID），供审阅工作台在舞台上进行元素级点选、框选命中检测与轻量直改（改字、改字号、拖拽位置）。
"""
import json
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from project_state import (PNG, REVIEW, SVG, approvals, content, images, local, read,
                           review_snapshot, sha, versions, write)
from review_surface import write_surface

SNAPSHOT_REL = f'{REVIEW}/snapshot.json'
VERSIONS_REL = f'{REVIEW}/versions'
XLINK_HREF = '{http://www.w3.org/1999/xlink}href'
SVG_NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG_NS)
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def asset_records(root, key):
    """这一页的素材，每条多一个能直接放进 URL 的短版本。

    `version` = 文件内容 sha256 的前 12 位。页内素材是**原地替换**的（同名覆盖），
    所以页面的资产 URL 必须带版本，才拿得到新图；页面大图用的是页版本，同一个道理。
    """
    return [{**item, 'version': str(item.get('sha256') or '')[:12]}
            for item in images(root, root/SVG/(key+'.svg'))]


def prepare_inline_svg(root, key):
    """读取 `<key>.svg`，为每个可交互节点打上确定性的 `data-review-id`（XML 树路径），
    并将内部 `id` 添加页面前缀以避免污染审阅页宿主 DOM ID（如 `#title`、`#slide`）。
    """
    svg_path = Path(root) / SVG / f'{key}.svg'
    if not svg_path.is_file():
        return ''
    try:
        tree = ET.parse(svg_path)
        svg_root = tree.getroot()
    except ET.ParseError:
        return ''

    prefix = f'rvsvg_{key}_'
    id_map = {}

    def walk_assign(node, path_str):
        tag = node.tag.split('}')[-1]
        node.set('data-review-id', path_str)
        orig_id = node.get('id')
        if orig_id:
            new_id = prefix + orig_id
            id_map[orig_id] = new_id
            node.set('data-orig-id', orig_id)
            node.set('id', new_id)
        if tag == 'image':
            href = node.get('href') or node.get(XLINK_HREF) or ''
            if href and not href.startswith(('data:', 'http:', 'https:', '#')):
                try:
                    img_file = local(root, str((svg_path.parent / href).resolve()))
                    if img_file.is_file():
                        rel = img_file.relative_to(Path(root).resolve()).as_posix()
                        ver = sha(img_file)[:12]
                        node.set('data-project-rel', rel)
                        node.set('data-project-ver', ver)
                except Exception:
                    pass
        children = list(node)
        for idx, child in enumerate(children):
            walk_assign(child, f'{path_str}.{idx}')

    walk_assign(svg_root, '0')

    # Rewrite url(#...) and href="#..." references to match prefixed IDs
    if id_map:
        url_re = re.compile(r'url\(\s*#([^)\s]+)\s*\)')
        for node in svg_root.iter():
            for attr, val in list(node.attrib.items()):
                if not isinstance(val, str):
                    continue
                if 'url(#' in val:
                    new_val = url_re.sub(
                        lambda m: f'url(#{id_map.get(m.group(1), m.group(1))})', val
                    )
                    node.set(attr, new_val)
                elif attr in ('href', XLINK_HREF) and val.startswith('#'):
                    ref_id = val[1:]
                    if ref_id in id_map:
                        node.set(attr, '#' + id_map[ref_id])
            if node.tag.split('}')[-1] == 'style' and node.text:
                node.text = url_re.sub(
                    lambda m: f'url(#{id_map.get(m.group(1), m.group(1))})', node.text
                )

    svg_root.set('data-review-page', key)
    if not svg_root.get('viewBox'):
        w = svg_root.get('width') or '1920'
        h = svg_root.get('height') or '1080'
        svg_root.set('viewBox', f'0 0 {w} {h}')
    return ET.tostring(svg_root, encoding='unicode')


def previous_page_feedback(root, current):
    """旧一轮反馈里「这一页已经按意见改过、待人复核」的那些条目。"""
    old = read(root/REVIEW/'feedback.json', {}).get('pages', {})
    if not isinstance(old, dict):
        return {}
    carried = {}
    for key, version in current.items():
        item = old.get(key)
        if not isinstance(item, dict) or item.get('version') == version:
            continue
        carried[key] = {
            'previousDecision': item.get('decision') or 'pending',
            'previousFeedback': str(item.get('feedback') or ''),
            'previousAnnotations': item.get('annotations') or [],
            'previousAssets': item.get('assets') or [],
            'previousSvgEdits': item.get('svg_edits') or [],
        }
    return carried


def generate(root, template_path=None):
    c = content(root)
    v = versions(root)
    old = review_snapshot(root)
    allowed = approvals(root)
    carried = previous_page_feedback(root, v)
    snap = {
        'review_id': uuid.uuid4().hex,
        'versions': v,
        'order': list(v),
        'png_hashes': {k: sha(root/PNG/(k+'.png')) for k in v},
        'assets': {k: asset_records(root, k) for k in v},
    }
    data = {
        'project': c.get('project', ''),
        'review_id': snap['review_id'],
        'snapshot': SNAPSHOT_REL,
        'pages': [],
    }
    for p in c['pages']:
        k = p['page_key']
        previous = root/REVIEW/'versions'/f'{k}-{old.get("versions", {}).get(k, "")}.png'
        data['pages'].append({
            'key': k,
            'title': p['title'],
            'png': f'{PNG}/{k}.png',
            'svg': f'{SVG}/{k}.svg',
            'svgMarkup': prepare_inline_svg(root, k),
            'version': v[k],
            'png_sha256': snap['png_hashes'][k],
            'assets': snap['assets'][k],
            'previous': f'{VERSIONS_REL}/{previous.name}' if previous.exists() else '',
            'decision': 'approved' if allowed.get(k, {}).get('decision') == 'approved' else 'pending',
            **carried.get(k, {}),
        })
    tpl_file = Path(template_path) if template_path else (Path(__file__).resolve().parents[1]/'assets/review/review.html')
    if not tpl_file.is_file():
        tpl_file = Path(__file__).resolve().parent / 'review.html'
    template = tpl_file.read_text(encoding='utf-8')
    html = template.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    (root/'02_visual_review.html').write_text(html, encoding='utf-8')
    snap['html_sha256'] = sha(root/'02_visual_review.html')
    write(root/REVIEW/'snapshot.json', snap)
    write_surface(root)
    return snap
