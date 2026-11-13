"""One actual-page review: the surface entry page, the surface contract, and the snapshot.

这一份产物是三件东西，一起生成、一起作废：

  · `02_visual_review.html` —— 审阅页（review-surface 的入口），里面留 `{{REVIEW_BRIDGE}}` 注入点；
  · `_internal/05_review/snapshot.json` —— 生成这一刻的版本快照（review_id + 每页版本 + PNG hash）；
  · `_internal/05_review/review-surface.json` —— 交给宿主的 surface（页面、目录、反馈文件、唤醒文案）。

页面里的资产一律走**相对 `dir`（＝项目根）的路径**，由页面向桥要 URL：`await review.asset(rel, {v})`。
所以这里给的是 `rel` 与 `version`，不是拼好的 URL。
同时注入存储分配的稳定元素 ID 与隔离前缀 SVG，供工作台进行元素级编辑。
"""
import hashlib
import json
import re
import shlex
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from project_state import (PNG, REVIEW, SVG, content, images, local, read,
                           review_snapshot, sha, source_digest, versions, write)
from review_surface import DRAFT_REL, resolve_module, write_surface
from template import layout_index
from workbench_store import ensure, get_page
from lib.svg_style_inline import expand_for_inline

SNAPSHOT_REL = f'{REVIEW}/snapshot.json'
VERSIONS_REL = f'{REVIEW}/versions'
GALLERY_REL = f'{REVIEW}/template_gallery'
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
    # 页内 `<style>` 与 `var(--token)` 在这里展开成字面属性，然后摘掉 `<style>` 再做 id 前缀隔离。
    # 与 PPT 转换器共用 `lib/svg_style_inline` 的同一份实现：一个 SVG 的两个消费方看到的必须同一种效果。
    try:
        expand_for_inline(svg_root, raw_svg_text=record.get('svg') or '')
    except ValueError as exc:
        raise ValueError(f'{key}: {exc}') from exc

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
    tools = path.with_name('workbench-tools.js')
    # 生成器自己与版式索引也进指纹：页面里的画廊数据是这两个模块算出来的，只比皮肤会漏掉数据层。
    generator = Path(__file__).resolve()
    index = generator.parent / 'template' / 'layout_index.py'
    return ':'.join([sha(path), sha(tools) if tools.is_file() else '', sha(tokens) if tokens.is_file() else '',
                     sha(generator), sha(index) if index.is_file() else '',
                     *(sha(file) for file in ui_files if file.is_file())])


def template_library_root():
    """随 Skill 发布的内置模板库。调用方要换根（测试、私有库）时显式传。"""
    return Path(__file__).resolve().parents[1] / 'assets' / 'template_library'


def _safe_name(value):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', str(value)).strip('.-') or 'item'


def _applied_template(root):
    """项目当前这套模板：v2 看 `template_pack/`，v1 看 `fidelity_template/`。

    返回 `(manifest, pack_root, legacy)`。没有模板时 `(空, None, False)`。
    """
    project = Path(root) / '_internal' / '00_project'
    pack = project / 'template_pack'
    if pack.is_dir():
        manifest = read(pack / 'manifest.json', {}) or read(project / 'template_library_source.json', {})
        return manifest, pack, False
    if (project / 'fidelity_template' / 'template_registry.json').is_file():
        return read(project / 'template_library_source.json', {}), project, True
    return {}, None, False


def _thumb(root, template_key, key, src, cache):
    """把一张版式预览缩成画廊缩略图；源没变就复用。返回项目相对路径，失败给空串。"""
    src = Path(src)
    if not src.is_file():
        return ''
    relative = f'{GALLERY_REL}/{_safe_name(template_key)}/{_safe_name(key)}.jpg'
    destination = Path(root) / relative
    stamp = f'{src.stat().st_mtime_ns}:{src.stat().st_size}'
    cache_key = f'{template_key}|{key}'
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and cached.get('stamp') == stamp and destination.is_file():
        return relative
    try:
        image = Image.open(src).convert('RGB')
        image.thumbnail((640, 360))
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, 'JPEG', quality=84)
    except (OSError, ValueError):
        return ''
    cache[cache_key] = {'stamp': stamp, 'src': str(src)}
    return relative


def _template_entry(root, template_id, manifest, pack_root, cache, applied=False, selectable=True, legacy=False):
    layouts = []
    for layout in layout_index.pack_layouts(pack_root):
        preview = layout.get('preview', '')
        thumb = _thumb(root, template_id, layout['layout_id'], Path(pack_root) / preview, cache) if preview else ''
        layouts.append({**layout, 'preview': thumb})
    cover = ''
    declared = str(manifest.get('preview') or '')
    if declared and (Path(pack_root) / declared).is_file():
        cover = _thumb(root, template_id, '__cover__', Path(pack_root) / declared, cache)
    elif legacy:
        contact = Path(pack_root) / 'fidelity_template' / 'canvas_previews' / 'full_deck_contact_sheet.png'
        cover = _thumb(root, template_id, '__cover__', contact, cache)
    if not cover and layouts:
        cover = layouts[0].get('preview', '')
    return {
        'template_id': template_id,
        'name': str(manifest.get('name') or template_id),
        'description': str(manifest.get('description') or ''),
        'schema': str(manifest.get('schema') or ('planner.template-library.v1' if legacy else '')),
        'applied': applied,
        'selectable': selectable,
        'legacy': legacy,
        'cover': cover,
        'layouts': layouts,
    }


def build_gallery(root, library_root=None):
    """工作台的模板/版式画廊数据。

    `library_root=''` 表示只列项目当前这套模板（测试用，也避免把大库的缩略图反复算）。
    默认读随 Skill 发布的库；库条目只收 approved 的 v2 四件套——legacy fidelity 套用会切走
    页面锁层流程，不适合在「版式只作参考」的面里当整套模板选。
    """
    root = Path(root)
    cache_path = root / GALLERY_REL / 'cache.json'
    cache = read(cache_path, {})
    if not isinstance(cache, dict):
        cache = {}
    manifest, pack_root, legacy = _applied_template(root)
    applied_id = str(manifest.get('template_id') or '') if manifest else ''
    templates = []
    if pack_root:
        templates.append(_template_entry(
            root, applied_id or 'project-template', manifest, pack_root, cache,
            applied=True, selectable=not legacy, legacy=legacy))
    if library_root != '':
        library = Path(library_root) if library_root else template_library_root()
        if library.is_dir():
            for manifest_path in sorted(library.glob('*/manifest.json')):
                data = read(manifest_path, {})
                if data.get('status') != 'approved':
                    continue
                is_v2 = data.get('schema') == 'planner.multimodal-template-pack.v2' or 'four_piece_contract' in data
                if not is_v2:
                    continue
                template_id = str(data.get('template_id') or manifest_path.parent.name)
                if template_id == applied_id:
                    continue
                templates.append(_template_entry(
                    root, template_id, data, manifest_path.parent, cache,
                    applied=False, selectable=True, legacy=False))
    write(cache_path, cache)
    return {'applied_template_id': applied_id, 'templates': templates}


def gallery_fingerprint(root, library_root=None):
    """这一版画廊数据是否还对应当前模板与库。

    应用了另一套模板、或库里某套包重新发布，都应重出审阅页（缩略图与可选项都变了）。
    只看 manifest 里预计算的 `package_sha256`，不为指纹重算整包哈希。
    """
    root = Path(root)
    project = root / '_internal' / '00_project'
    entries = []
    manifest, pack_root, legacy = _applied_template(root)
    if pack_root:
        if legacy:
            entries.append(['applied', str(manifest.get('template_id') or ''),
                            sha(project / 'template_library_source.json') if (project / 'template_library_source.json').is_file() else ''])
            registry = pack_root / 'fidelity_template' / 'template_registry.json'
            entries.append(['registry', sha(registry) if registry.is_file() else ''])
        else:
            entries.append(['applied', str(manifest.get('template_id') or ''),
                            str(manifest.get('package_sha256') or '')])
    if library_root != '':
        library = Path(library_root) if library_root else template_library_root()
        if library.is_dir():
            for manifest_path in sorted(library.glob('*/manifest.json')):
                data = read(manifest_path, {})
                if data.get('status') != 'approved':
                    continue
                if data.get('schema') != 'planner.multimodal-template-pack.v2' and 'four_piece_contract' not in data:
                    continue
                entries.append(['library', str(data.get('template_id') or manifest_path.parent.name),
                                str(data.get('package_sha256') or '')])
    return hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


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


def generate(root, template_path=None, library_root=None):
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
        'gallery_sha256': gallery_fingerprint(root, library_root),
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
        'gallery': build_gallery(root, library_root),
        'pages': [],
    }
    by_key = {p['page_key']: p for p in c['pages']}
    for key in head['order']:
        p = by_key.get(key) or head['pages'][key].get('input', {})
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
            'layout_id': stored.get('layout_id', ''),
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
    tools = review_template_path().with_name('workbench-tools.js').read_text(encoding='utf-8')
    html = html.replace('__WORKBENCH_TOOLS__', tools.replace('</script', '<\\/script'))
    html = html.replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    (root/'02_visual_review.html').write_text(html, encoding='utf-8')
    snap['html_sha256'] = sha(root/'02_visual_review.html')
    write(root/REVIEW/'snapshot.json', snap)
    write_surface(root)
    return snap
