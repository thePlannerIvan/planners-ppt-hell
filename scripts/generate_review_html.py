"""One actual-page review: the surface entry page, the surface contract, and the snapshot.

这一份产物是三件东西，一起生成、一起作废：

  · `02_visual_review.html` —— 审阅页（review-surface 的入口），里面留 `{{REVIEW_BRIDGE}}` 注入点；
  · `_internal/05_review/snapshot.json` —— 生成这一刻的版本快照（review_id + 每页版本 + PNG hash）；
  · `_internal/05_review/review-surface.json` —— 交给宿主的 surface（页面、目录、反馈文件、唤醒文案）。

页面里的资产一律走**相对 `dir`（＝项目根）的路径**，由页面向桥要 URL：`await review.asset(rel, {v})`。
所以这里给的是 `rel` 与 `version`，不是拼好的 URL。
同时注入存储分配的稳定元素 ID 与隔离前缀 SVG，供工作台进行元素级编辑。
"""
import json
import re
import shlex
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from project_state import (PNG, REVIEW, SVG, content, images, local, read,
                           review_snapshot, sha, source_digest, versions, write)
from review_surface import DRAFT_REL, resolve_module, write_surface
from workbench_store import ensure, get_page

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


def prepare_inline_svg(root, key, page_record=None):
    """Only expose store-stamped identities; isolate SVG IDs from the host DOM."""
    record = page_record if page_record is not None else get_page(root, key)
    svg_path = Path(record.get('svg_path') or Path(root) / SVG / f'{key}.svg')
    try:
        svg_root = ET.fromstring(record.get('svg') or '')
    except ET.ParseError:
        return ''
    if any(node.tag.split('}')[-1] == 'style' and (node.text or '').strip()
           for node in svg_root.iter()):
        raise ValueError(f'{key}: workbench inline preview does not support SVG CSS rules; use presentation attributes')

    prefix = f'rvsvg_{key}_'
    id_map = {}

    def walk_assign(node):
        tag = node.tag.split('}')[-1]
        identity = node.get('data-workbench-id')
        if identity:
            node.set('data-review-id', identity)
        else:
            node.attrib.pop('data-review-id', None)
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
        for child in node:
            walk_assign(child)

    walk_assign(svg_root)

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


def review_template_path():
    """审阅页模板（本 Skill 持有的那一份）。"""
    return Path(__file__).resolve().parents[1]/'assets/review/review.html'


def template_fingerprint():
    """「这个页面是拿哪一版模板生成的」。

    页面 = 模板 + 内联的令牌表，两样任一变了，磁盘上那份页面就不再是"用当前模板生成的"。
    快照里记下它，`make_review` 才能分辨"这一版页面还是最新的"和"模板升级了、页面该重出"
    ——单看页面自己的 sha 是分辨不出来的（那时页面与快照互相印证，两个都是旧的）。
    """
    path = review_template_path()
    if not path.is_file():
        return ''
    tokens = resolve_module('planners-review-core')/'assets'/'dsh-tokens.css'
    ui = resolve_module('planners-review-core')/'assets'
    ui_files = [ui/'review-ui.css', *sorted((ui/'review-ui').glob('*'))]
    return ':'.join([sha(path), sha(tokens) if tokens.is_file() else '',
                     *(sha(file) for file in ui_files if file.is_file())])


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
            'previousFeedback': str(item.get('feedback') or ''),
            'previousAnnotations': item.get('annotations') or [],
            'previousAssets': item.get('assets') or [],
            'previousSvgEdits': item.get('svg_edits') or [],
        }
    return carried


def generate(root, template_path=None):
    root = Path(root).resolve()
    head = ensure(root)
    c = content(root)
    v = versions(root)
    old = review_snapshot(root)
    carried = previous_page_feedback(root, v)
    snap = {
        'review_id': uuid.uuid4().hex,
        'versions': v,
        'order': list(head['order']),
        'revisions': {k: p.get('revision') for k, p in head['pages'].items()},
        'png_hashes': {k: sha(root/PNG/(k+'.png')) if (root/PNG/(k+'.png')).is_file() else '' for k in v},
        'assets': {k: asset_records(root, k) for k in v},
        'template_sha256': template_fingerprint(),
        'source_sha256': source_digest(root),
    }
    data = {
        'project': c.get('project', ''),
        'review_id': snap['review_id'],
        'snapshot': SNAPSHOT_REL,
        # 草稿文件的**相对 dir 路径**（页面用它读回未提交的草稿）。与 surface 里那个
        # `draft` 同一个来源（`review_surface.VISUAL['draft_rel']`），只是基准不同：
        # surface 里相对它自己，页面里相对 dir。
        'draft': DRAFT_REL,
        'order': head['order'],
        'workbench_root': str(root),
        'route': head.get('route', 'slides'),
        'export_command_base': f'python3 {shlex.quote(str(Path(__file__).parent / "orchestrate/ppt_pipeline.py"))} {shlex.quote(str(root))} export',
        'local_fallback_command': f'python3 {shlex.quote(str(Path(__file__).with_name("review_surface.py")))} {shlex.quote(str(root))}',
        'pages': [],
    }
    by_key = {p['page_key']: p for p in c['pages']}
    for key in head['order']:
        p = by_key[key]
        k = p['page_key']
        stored = get_page(root, k)
        previous = root/REVIEW/'versions'/f'{k}-{old.get("versions", {}).get(k, "")}.png'
        data['pages'].append({
            'key': k,
            'title': p['title'],
            'png': f'{PNG}/{k}.png',
            'svg': f'{SVG}/{k}.svg',
            'svgMarkup': prepare_inline_svg(root, k, stored),
            'revision': stored['revision'],
            'svg_path': stored.get('svg_path', ''),
            'notes': stored.get('notes', ''),
            'protected': stored.get('protected', {}),
            'history': stored.get('history', []),
            'parent': stored.get('parent'),
            'preview_pending': not (root/'_internal/06_workbench/renders'/str(stored['revision'])/'render.json').is_file(),
            'version': v[k],
            'png_sha256': snap['png_hashes'][k],
            'assets': snap['assets'][k],
            'previous': f'{VERSIONS_REL}/{previous.name}' if previous.exists() else '',
            **carried.get(k, {}),
        })
    tpl_file = Path(template_path) if template_path else (Path(__file__).resolve().parents[1]/'assets/review/review.html')
    if not tpl_file.is_file():
        tpl_file = Path(__file__).resolve().parent / 'review.html'
    template = tpl_file.read_text(encoding='utf-8')
    # DSH 设计令牌随页面一起发：审阅页在不透明源 iframe 里，宿主的变量继承不进来、
    # 外链样式表也会被信任围栏打回 403，所以这张表必须是**内联的**。
    # 表只有一份，在公共接缝那儿（planners-review-core）—— 本 Skill 不再存副本。
    tokens = (resolve_module('planners-review-core')/'assets'/'dsh-tokens.css').read_text(encoding='utf-8')
    review_ui = json.loads(subprocess.check_output([
        'node', str(resolve_module('planners-review-core')/'scripts/review-ui.mjs')], text=True))
    html = template.replace('__DSH_TOKENS__', tokens)
    html = html.replace('__REVIEW_UI__', review_ui['css'])
    html = html.replace('__REVIEW_UI_SCRIPT__', review_ui['script'].replace('</script', '<\\/script'))
    html = html.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    (root/'02_visual_review.html').write_text(html, encoding='utf-8')
    snap['html_sha256'] = sha(root/'02_visual_review.html')
    write(root/REVIEW/'snapshot.json', snap)
    write_surface(root)
    return snap
