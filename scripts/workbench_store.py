"""Durable SVG revisions. All writers cross commit; compatibility SVGs are views."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from canvas_frame import project_frame

STORE = '_internal/06_workbench'
VIEW = '_internal/02_svg_source'
PNG = '_internal/03_png_preview/pages'
ID_ATTR = 'data-workbench-id'
XLINK = '{http://www.w3.org/1999/xlink}href'
KEY = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
# 版式引用是模板包里的 primitive/canvas 名（p24_... / cover_dark），允许数字开头。
LAYOUT_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


class StoreError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def load(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).is_file() else default


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inside(root, value):
    root = Path(root).resolve()
    result = (root / value).resolve()
    if result == root or root not in result.parents:
        raise StoreError('outside_project', 'Path is outside project', path=str(value))
    return result


@contextmanager
def locked(root):
    base = Path(root) / STORE
    base.mkdir(parents=True, exist_ok=True)
    with (base / '.lock').open('a+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield base


def parse_svg(svg):
    if re.search(r'<!DOCTYPE|<!ENTITY', svg, re.I):
        raise StoreError('unsafe_svg', 'SVG declarations are not supported')
    try:
        tree = ET.fromstring(svg)
    except ET.ParseError as error:
        raise StoreError('invalid_svg', str(error)) from error
    if tree.tag.split('}')[-1] != 'svg':
        raise StoreError('invalid_svg', 'Expected SVG root')
    seen = set()
    for element in tree.iter():
        if element.tag.split('}')[-1] in ('script', 'foreignObject'):
            raise StoreError('unsafe_svg', 'Executable SVG elements are not supported')
        if any(key.lower().startswith('on') for key in element.attrib):
            raise StoreError('unsafe_svg', 'SVG event handlers are not supported')
        for attribute, value in element.attrib.items():
            if attribute.split('}')[-1] == 'href' and element.tag.split('}')[-1] != 'image' and not value.startswith('#'):
                raise StoreError('unsafe_svg', 'Non-image SVG references must target local element IDs')
        styles = [element.get('style', '')]
        if element.tag.split('}')[-1] == 'style':
            styles.append(element.text or '')
        for style in styles:
            if re.search(r'@import|expression\s*\(', style, re.I):
                raise StoreError('unsafe_svg', 'External or executable CSS is not supported')
            for resource in re.findall(r'url\(\s*[\"\']?([^\)\"\']+)', style, re.I):
                if not resource.strip().startswith('#'):
                    raise StoreError('unsafe_svg', 'CSS resources must target local SVG element IDs')
        identity = element.get(ID_ATTR) or element.get('id') or ('wb_' + uuid.uuid4().hex)
        if identity in seen:
            raise StoreError('duplicate_element', 'Duplicate stable element identity', element_id=identity)
        seen.add(identity)
        element.set(ID_ATTR, identity)
    return tree


def xml(tree):
    return ET.tostring(tree, encoding='unicode')


def elements(tree):
    return {node.get(ID_ATTR): node for node in tree.iter()}


def freeze_assets(root, tree, source_dir, destination, visiting=None):
    """Pin byte dependencies and rewrite only their paths, never IDs or animation fields."""
    assets = []
    visiting = set() if visiting is None else visiting
    for node in tree.iter():
        if node.tag.split('}')[-1] != 'image':
            continue
        attribute = 'href' if 'href' in node.attrib else XLINK
        href = node.get(attribute, '')
        if not href or href.startswith(('http:', 'https:', 'javascript:', 'file:', '#')):
            raise StoreError('invalid_asset', 'Images must use project-local files or data URIs')
        if href.startswith('data:'):
            assets.append({'element_id': node.get(ID_ATTR), 'sha256': digest(href.encode()), 'embedded': True})
            continue
        original = inside(root, str((Path(source_dir) / href).resolve()))
        if not original.is_file():
            raise StoreError('missing_asset', 'Image file not found', path=str(original))
        data = original.read_bytes()
        source_hash = digest(data)
        suffix = original.suffix.lower()
        if suffix not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
            raise StoreError('invalid_asset', 'Unsupported image extension', path=str(original))
        dependencies = []
        if suffix == '.svg':
            if original in visiting:
                raise StoreError('cyclic_asset', 'SVG image dependency cycle', path=str(original))
            nested = parse_svg(data.decode('utf-8'))
            dependencies = freeze_assets(root, nested, original.parent, destination, visiting | {original})
            # The nested SVG is itself inside assets/, so its paths omit that prefix.
            for child in nested.iter():
                for nested_attribute in ('href', XLINK):
                    ref = child.get(nested_attribute, '')
                    if child.tag.split('}')[-1] == 'image' and ref.startswith('assets/'):
                        child.set(nested_attribute, ref[len('assets/'):])
            data = xml(nested).encode()
        fingerprint = digest(data)
        relative = 'assets/' + fingerprint + suffix
        target = destination / relative
        if not target.exists():
            atomic(target, data)
        node.set(attribute, relative)
        assets.append({'element_id': node.get(ID_ATTR), 'path': relative, 'sha256': fingerprint,
                       'source_path': str(original), 'source_sha256': source_hash,
                       'dependencies': dependencies})
    return assets


def revision_dir(root, revision):
    if not KEY.fullmatch(str(revision)):
        raise StoreError('invalid_revision', 'Invalid revision identity')
    return Path(root) / STORE / 'revisions' / revision


def revision_record(root, revision):
    directory = revision_dir(root, revision)
    record = load(directory / 'revision.json')
    if not record or digest((directory / 'page.svg').read_bytes()) != record['svg_sha256']:
        raise StoreError('damaged_revision', 'Revision SVG is missing or changed', revision=revision)
    def check_assets(items):
        for asset in items:
            if not asset.get('embedded') and digest((directory / asset['path']).read_bytes()) != asset['sha256']:
                raise StoreError('damaged_revision', 'Revision asset is missing or changed', revision=revision)
            check_assets(asset.get('dependencies', []))
    check_assets(record['assets'])
    return record


def create_revision(root, key, svg, source_dir, notes, protected, author, parent=None, origin=None):
    tree = parse_svg(svg)
    revision = 'r_' + uuid.uuid4().hex
    directory = revision_dir(root, revision)
    directory.mkdir(parents=True)
    assets = freeze_assets(root, tree, source_dir, directory)
    data = xml(tree).encode()
    atomic(directory / 'page.svg', data)
    record = {'page_key': key, 'revision': revision, 'parent': parent, 'created_at': now(),
              'author': author, 'origin': origin, 'notes': notes, 'protected': protected,
              'svg_sha256': digest(data), 'assets': assets}
    atomic(directory / 'revision.json', encoded(record))
    return record


def view_bytes(root, revision):
    directory = revision_dir(root, revision)
    tree = ET.fromstring((directory / 'page.svg').read_text())
    view_dir = Path(root) / VIEW
    for node in tree.iter():
        for attribute in ('href', XLINK):
            href = node.get(attribute, '')
            if node.tag.split('}')[-1] == 'image' and href and not href.startswith('data:'):
                node.set(attribute, os.path.relpath(directory / href, view_dir))
    return xml(tree).encode()


def rebuild(root, head, check=True):
    if head.get('collection_managed'):
        update_content_collection(root, head)
        for key in head.get('deleted_pages', {}):
            for directory, suffix in ((VIEW, '.svg'), (PNG, '.png')):
                path = Path(root) / directory / (key + suffix)
                if path.is_file():
                    path.unlink()
    for key in head['order']:
        revision = head['pages'].get(key, {}).get('revision')
        if not revision:
            continue
        revision_record(root, revision)
        path = Path(root) / VIEW / (key + '.svg')
        expected = view_bytes(root, revision)
        if check and path.exists() and path.read_bytes() != expected:
            # A previous commit can die between head replacement and view rebuilding.
            old_hash = head['pages'][key].get('previous_view_sha256')
            if digest(path.read_bytes()) != old_hash:
                raise StoreError('external_write', 'Current SVG was changed outside workbench; preserve it as a candidate',
                                 page_key=key, candidate=str(path), revision=revision)
        if not path.exists() or path.read_bytes() != expected:
            atomic(path, expected)


def initialize(root):
    base = Path(root) / STORE
    head_path = base / 'head.json'
    head = load(head_path)
    if head:
        rebuild(root, head)
        return head
    content = load(Path(root) / '_internal/01_content/page_content.json', {})
    manifest = load(Path(root) / '_internal/00_project/page_manifest.json', {})
    pages = content.get('pages', [])
    head = {'version': 'svg-workbench/1', 'order': [], 'pages': {}, 'tasks': {}, 'operations': {},
            'route': manifest.get('route', 'slides'), 'upstream': manifest.get('input_binding', {}),
            'input_kind': manifest.get('input_kind', 'production'), 'created_at': now()}
    for page in pages:
        key = page.get('page_key', '')
        if not KEY.fullmatch(key) or key in head['pages']:
            raise StoreError('invalid_page', 'Each page needs a unique stable page_key')
        head['order'].append(key)
        source = Path(root) / VIEW / (key + '.svg')
        head['pages'][key] = {'revision': None, 'title': page.get('title', key), 'input': page}
        if source.is_file():
            original_hash = digest(source.read_bytes())
            record = create_revision(root, key, source.read_text(), source.parent,
                                     page.get('notes', ''), {}, 'import', origin=str(source))
            head['pages'][key]['revision'] = record['revision']
            head['pages'][key]['baseline_revision'] = record['revision']
            head['pages'][key]['previous_view_sha256'] = original_hash
    # Legacy PNG/history remain untouched and are not represented as invented revisions.
    atomic(head_path, encoded(head))
    rebuild(root, head, check=False)
    return head


def ensure(root):
    root = Path(root).resolve()
    with locked(root):
        return copy.deepcopy(initialize(root))


def state(root):
    return ensure(root)


def page_value(root, head, key):
    if key not in head['pages']:
        raise StoreError('unknown_page', 'Unknown page', page_key=key)
    revision = head['pages'][key]['revision']
    layout_id = head['pages'][key].get('layout_id', '')
    if not revision:
        return {'page_key': key, 'revision': None, 'svg': '', 'layout_id': layout_id,
                'notes': head['pages'][key]['input'].get('notes', ''), 'protected': {}}
    record = revision_record(root, revision)
    return {**record, 'svg': (revision_dir(root, revision) / 'page.svg').read_text(),
            'layout_id': layout_id, 'svg_path': str(revision_dir(root, revision) / 'page.svg')}


def get_page(root, key):
    root = Path(root).resolve()
    with locked(root):
        return page_value(root, initialize(root), key)


GEOMETRY_ATTRIBUTES = ('x', 'y', 'transform')


def _pin_geometry(node, guard):
    """用户改过字的元素，把它的位置也一并钉住。

    只钉文字的话，模型一次「排版调整」就能把这块字挪走，人看到的是「我改过的又被改回去了」。
    位置进 guard 之后，模型要动它必须拿到任务里的元素授权（rewrite_elements）。
    """
    attributes = guard.setdefault('attributes', {})
    for attribute in GEOMETRY_ATTRIBUTES:
        value = node.get(attribute)
        if value is not None and attribute not in attributes:
            attributes[attribute] = value


def with_implicit_geometry(protected, current_svg):
    """老修订只记了文字、没记位置的 guard：按它现在所在的位置补上。

    新写入的 guard 自带几何；历史页面不能因为「当时只钉了文字」就继续让模型自由挪动。
    """
    if not protected or not current_svg:
        return protected
    lookup = elements(ET.fromstring(current_svg))
    effective = copy.deepcopy(protected)
    for identity, guard in effective.items():
        if guard.get('deleted') or 'text' not in guard or 'attributes' in guard:
            continue
        node = lookup.get(identity)
        if node is None:
            continue
        attributes = {attribute: node.get(attribute) for attribute in GEOMETRY_ATTRIBUTES
                      if node.get(attribute) is not None}
        if attributes:
            guard['attributes'] = attributes
    return effective


def apply_edits(tree, edits, protected):
    for edit in edits:
        identity = edit.get('element_id')
        node = elements(tree).get(identity)
        if node is None:
            raise StoreError('missing_element', 'Edited element no longer exists', element_id=identity)
        guard = protected.setdefault(identity, {})
        kind = edit.get('kind')
        if kind == 'text':
            value = edit.get('value')
            if not isinstance(value, str) or node.tag.split('}')[-1] not in ('text', 'tspan'):
                raise StoreError('invalid_edit', 'Text edits require a text element and string')
            for descendant in list(node.iter())[1:]:
                protected.pop(descendant.get(ID_ATTR), None)
            for child in list(node):
                node.remove(child)
            node.text = value
            guard['text'] = value
            guard.pop('text_nodes', None)
            _pin_geometry(node, guard)
        elif kind == 'text_nodes':
            edits = edit.get('nodes')
            if node.tag.split('}')[-1] != 'text' or not isinstance(edits, list) or not edits:
                raise StoreError('invalid_edit', 'Text-node edits require a text element and nodes')
            descendants = {child.get(ID_ATTR): child for child in node.iter()
                           if child.tag.split('}')[-1] in ('text', 'tspan')}
            for item in edits:
                if not isinstance(item, dict):
                    raise StoreError('invalid_edit', 'Text-node edits must be objects')
                target = descendants.get(item.get('element_id'))
                slot, value = item.get('slot'), item.get('value')
                if target is None or slot not in ('text', 'tail') or not isinstance(value, str) or (target is node and slot == 'tail'):
                    raise StoreError('invalid_edit', 'Text-node edits must stay inside the target text')
                setattr(target, slot, value)
            guard['text'] = ''.join(node.itertext())
            # Node-level guards retain formatting boundaries without flattening tspans.
            guard['text_nodes'] = [dict(item) for item in edits]
            _pin_geometry(node, guard)
        elif kind == 'attributes':
            attributes = edit.get('attributes', {})
            allowed = {'x', 'y', 'dx', 'dy', 'transform', 'font-size', 'font-weight', 'font-family',
                       'fill', 'opacity', 'width', 'height', 'preserveAspectRatio'}
            if not isinstance(attributes, dict) or not set(attributes).issubset(allowed):
                raise StoreError('invalid_edit', 'Unsupported edit attributes')
            for attribute, value in attributes.items():
                if value is None:
                    node.attrib.pop(attribute, None)
                else:
                    node.set(attribute, str(value))
                guard.setdefault('attributes', {})[attribute] = None if value is None else str(value)
        elif kind == 'delete':
            parent = next((p for p in tree.iter() if node in list(p)), None)
            if parent is None:
                raise StoreError('invalid_edit', 'Cannot delete SVG root')
            for descendant in node.iter():
                protected[descendant.get(ID_ATTR)] = {'deleted': True}
            parent.remove(node)
        else:
            raise StoreError('invalid_edit', 'Unknown edit kind')
    # A later human edit to a child updates its already-protected parent's text too.
    lookup = elements(tree)
    for identity, guard in protected.items():
        node = lookup.get(identity)
        if node is None or guard.get('deleted'):
            continue
        if 'text' in guard:
            guard['text'] = ''.join(node.itertext())
        if 'text_nodes' in guard:
            guard['text_nodes'] = [{**run, 'value': getattr(lookup[run['element_id']], run['slot']) or ''}
                                   for run in guard['text_nodes'] if run['element_id'] in lookup]
    return tree


def lost_edits(tree, protected, authorized=()):
    lookup = elements(tree)
    lost = []
    for identity, guard in protected.items():
        if identity in authorized:
            continue
        node = lookup.get(identity)
        wrong = bool(node is not None) if guard.get('deleted') else node is None
        if node is not None and not guard.get('deleted'):
            if 'text' in guard and ''.join(node.itertext()) != guard['text']:
                wrong = True
            for run in guard.get('text_nodes', []):
                target = lookup.get(run['element_id'])
                if target is None or getattr(target, run['slot']) != run['value']:
                    wrong = True
            if any(node.get(k) != v for k, v in guard.get('attributes', {}).items()):
                wrong = True
        if wrong:
            lost.append(identity)
    return lost


def prepare_candidate(root, command):
    candidate = command.get('candidate')
    if not candidate:
        return None
    directory = Path(root) / STORE / 'commands' / command['operation_id']
    metadata = directory / 'candidate.json'
    record = load(metadata)
    if record:
        if record.get('request_hash') != digest(encoded(command)):
            raise StoreError('operation_reused', 'Pinned operation ID used with a different command')
        path = directory / 'candidate.svg'
        if digest(path.read_bytes()) != record['sha256']:
            raise StoreError('damaged_candidate', 'Pinned request candidate changed')
        def verify(items):
            for asset in items:
                if not asset.get('embedded') and digest((directory / asset['path']).read_bytes()) != asset['sha256']:
                    raise StoreError('damaged_candidate', 'Pinned candidate dependency changed')
                verify(asset.get('dependencies', []))
        verify(record['assets'])
        return path
    original = inside(root, candidate)
    data = original.read_bytes()
    # Retain raw bytes even for an invalid candidate or a rejected CAS request.
    atomic(directory / 'original.svg', data)
    tree = parse_svg(data.decode('utf-8'))
    assets = freeze_assets(root, tree, original.parent, directory)
    path = directory / 'candidate.svg'
    atomic(path, xml(tree).encode())
    atomic(metadata, encoded({'sha256': digest(path.read_bytes()), 'original_sha256': digest(data),
                              'original_path': str(original), 'assets': assets,
                              'request_hash': digest(encoded(command))}))
    return path


def revision_changes(before, after, after_svg):
    """Compare frozen content, not candidate paths or revision metadata."""
    def values(svg, assets):
        if not svg:
            return {}, {}
        tree = ET.fromstring(svg)
        images = {a['element_id']: a['sha256'] for a in assets}
        nodes = {}
        texts = {}
        text_nodes = {n for text in tree.iter() if text.tag.split('}')[-1] == 'text' for n in text.iter()}
        parents = {child: parent for parent in tree.iter() for child in parent}
        for node in tree.iter():
            identity = node.get(ID_ATTR)
            attrs = dict(node.attrib)
            if node.tag.split('}')[-1] == 'image':
                attrs.pop('href', None)
                attrs.pop(XLINK, None)
                attrs['image_content_sha256'] = images.get(identity)
            # Ignore indentation between elements; preserve all text within text runs.
            text = node.text if node in text_nodes or (node.text and node.text.strip()) else None
            tail = node.tail if parents.get(node) in text_nodes or (node.tail and node.tail.strip()) else None
            nodes[identity] = (node.tag, attrs, text, tail,
                               [child.get(ID_ATTR) for child in node])
            if node.tag.split('}')[-1] == 'text':
                texts[identity] = ''.join(node.itertext())
        return nodes, texts

    old, old_text = values(before.get('svg', ''), before.get('assets', []))
    new, new_text = values(after_svg, after.get('assets', []))
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    modified = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
    old_images = {a['element_id']: a['sha256'] for a in before.get('assets', [])}
    new_images = {a['element_id']: a['sha256'] for a in after.get('assets', [])}
    image_ids = sorted(k for k in old_images.keys() | new_images.keys()
                       if old_images.get(k) != new_images.get(k))
    text_ids = sorted(k for k in old_text.keys() | new_text.keys()
                      if old_text.get(k) != new_text.get(k))
    notes_changed = before.get('notes', '') != after['notes']
    protection_changed = before.get('protected', {}) != after['protected']
    return {'elements': {'added': added, 'removed': removed, 'modified': modified,
                         'counts': {'added': len(added), 'removed': len(removed), 'modified': len(modified)}},
            'image_elements': image_ids, 'text_elements': text_ids,
            'svg_changed': bool(added or removed or modified),
            'notes_changed': notes_changed, 'protection_changed': protection_changed,
            'byte_delta': len(after_svg.encode()) - len(before.get('svg', '').encode()),
            'no_change': not (added or removed or modified or notes_changed or protection_changed)}


def _queue_render(root, key, revision):
    """保存之后异步重渲这一页的位图。

    同步渲一次要 ~2 秒，人打字时每个自动保存都等它，会把保存队列拖长；
    后台渲、并且只写回「仍是当前版本」的那一次，位图就不会长期停在旧内容上。
    """
    script = Path(__file__).resolve().parent / 'render_revision.py'
    if not script.is_file():
        return False
    try:
        subprocess.Popen([sys.executable, str(script), str(Path(root).resolve()), key, revision],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def sync_human_copy(root, head, key, before, tree):
    """用户改字之后，标题和文案基线跟着走。

    不跟的话：轨道标题还挂着旧句子、copy audit 还报「这句不在基线里」，
    同一条文案在画布、标题、基线三处各有一版，看起来就像「我改的没生效」。
    """
    if not before.get('svg'):
        return
    old_texts = {node.get(ID_ATTR): ''.join(node.itertext()) for node in ET.fromstring(before['svg']).iter()
                 if node.tag.split('}')[-1] == 'text'}
    new_texts = {node.get(ID_ATTR): ''.join(node.itertext()) for node in tree.iter()
                 if node.tag.split('}')[-1] == 'text'}
    changed = [(old_texts[i], new_texts[i]) for i in new_texts
               if i in old_texts and old_texts[i] != new_texts[i] and new_texts[i].strip()]
    if not changed:
        return
    path = Path(root) / '_internal/01_content/page_content.json'
    data = load(path, {})
    entry = next((page for page in data.get('pages', []) if page.get('page_key') == key), None)
    page = head['pages'][key]
    title = str((entry or {}).get('title') or page.get('title') or '')
    content = str((entry or {}).get('content') or page.get('input', {}).get('content') or '')
    for old, new in changed:
        if old and old in title:
            title = title.replace(old, new, 1)
        if new and new not in content:
            content = (content.rstrip() + '\n' + new).strip()
    page['title'] = title
    page.setdefault('input', {})
    page['input']['title'] = title
    page['input']['content'] = content
    if entry is not None:
        entry['title'] = title
        entry['content'] = content
        entry['copy_confirmed'] = True
        atomic(path, encoded(data))


def save_page(root, head, command, browser, prepared_candidate=None):
    key = command.get('page_key')
    current = page_value(root, head, key)
    if command.get('base_revision') != current['revision']:
        raise StoreError('conflict', 'Page changed since this edit started', page_key=key,
                         current_revision=current['revision'], base_revision=command.get('base_revision'))
    author = command.get('author', 'human' if browser else 'model')
    if author not in ('human', 'model') or (browser and author != 'human'):
        raise StoreError('invalid_author', 'Browser cannot submit model candidates')
    layout_id = command.get('layout_id')
    if layout_id is not None:
        if author != 'model':
            raise StoreError('invalid_layout', 'Only the model records a layout reference')
        if not isinstance(layout_id, str) or (layout_id and not LAYOUT_KEY.fullmatch(layout_id)):
            raise StoreError('invalid_layout', 'layout_id must be a template layout key')
    protected = copy.deepcopy(current['protected'])
    source_dir = revision_dir(root, current['revision']) if current['revision'] else Path(root) / VIEW
    candidate = command.get('candidate')
    if candidate:
        if browser or author != 'model':
            raise StoreError('invalid_candidate', 'Candidates are submitted by the model CLI')
        candidate = prepared_candidate or inside(root, candidate)
        svg = candidate.read_text()
        source_dir = candidate.parent
    else:
        svg = current['svg']
    if not svg:
        raise StoreError('missing_svg', 'A first model save needs a candidate SVG')
    tree = parse_svg(svg)
    if author == 'human':
        tree = apply_edits(tree, command.get('edits', []), protected)
    else:
        authorized = []
        task_id = command.get('task_id')
        if task_id:
            task = head['tasks'].get(task_id, {})
            page_task = task.get('pages', {}).get(key, {})
            if task.get('status') != 'pending' or page_task.get('revision') != current['revision']:
                raise StoreError('stale_task', 'Rewrite task is not bound to this current revision')
            authorized = page_task.get('rewrite_elements', [])
        effective = with_implicit_geometry(protected, current['svg'])
        missing = lost_edits(tree, effective, authorized)
        if missing:
            # 把 guard 原样带回去：整页重建时照着它把节点写回来即可，不必再 op=get 猜一遍。
            raise StoreError(
                'human_edits_lost',
                'Candidate drops retained human edits; re-apply each element with the same '
                'data-workbench-id carrying the guarded text and attributes',
                elements=missing,
                guards={identity: effective[identity] for identity in missing},
                candidate=str(candidate) if candidate else None)
        for identity in authorized:
            protected.pop(identity, None)
    notes = command.get('notes', current['notes'])
    if not isinstance(notes, str):
        raise StoreError('invalid_notes', 'Speaker notes must be a string')
    record = create_revision(root, key, xml(tree), source_dir, notes, protected, author,
                             parent=current['revision'], origin=command.get('operation_id'))
    page = head['pages'][key]
    view = Path(root) / VIEW / (key + '.svg')
    page['previous_view_sha256'] = digest(view.read_bytes()) if view.is_file() else None
    page['revision'] = record['revision']
    page.setdefault('baseline_revision', record['revision'])
    if layout_id is not None:
        page['layout_id'] = layout_id
    changes = revision_changes(current, record, (revision_dir(root, record['revision']) / 'page.svg').read_text())
    if author == 'human':
        sync_human_copy(root, head, key, current, tree)
    rendered = command.get('render') is True and author == 'human' and _queue_render(root, key, record['revision'])
    return {'ok': True, 'page_key': key, 'revision': record['revision'], 'saved': True,
            'rendered': 'queued' if rendered else False, 'notes': notes, 'changes': changes,
            'warnings': ['no_change'] if changes['no_change'] else []}


def feedback(head, command):
    pages = command.get('pages', {})
    scope = command.get('scope')
    template_id = command.get('template_id')
    if template_id is not None:
        if not isinstance(template_id, str) or (template_id and not LAYOUT_KEY.fullmatch(template_id)):
            raise StoreError('invalid_feedback', 'template_id must be a template library key')
        if template_id and scope != 'deck':
            raise StoreError('invalid_feedback', 'A whole-template request needs deck scope')
    # 整套模板请求可以不绑页面：这一步只换项目的视觉语言，页面重做由逐页版式另说。
    if (scope not in ('page', 'deck') or (scope == 'page' and len(pages) != 1)
            or (not pages and not template_id)):
        raise StoreError('invalid_feedback', 'Feedback needs page or deck scope and targets')
    for key, item in pages.items():
        if key not in head['pages'] or item.get('revision') != head['pages'][key]['revision']:
            raise StoreError('conflict', 'Feedback baseline changed', page_key=key,
                             current_revision=head['pages'].get(key, {}).get('revision'))
        if not isinstance(item.get('rewrite_elements', []), list):
            raise StoreError('invalid_feedback', 'Rewrite scope must be an element list')
        layout_id = item.get('layout_id')
        if layout_id is not None and (not isinstance(layout_id, str)
                                      or (layout_id and not LAYOUT_KEY.fullmatch(layout_id))):
            raise StoreError('invalid_feedback', 'layout_id must be a template layout key')
    identity = 'task_' + uuid.uuid4().hex
    head['tasks'][identity] = {'task_id': identity, 'scope': scope, 'pages': copy.deepcopy(pages),
                               'template_id': template_id or '',
                               'overall_feedback': str(command.get('overall_feedback') or ''),
                               'status': 'pending', 'created_at': now()}
    return {'ok': True, 'task_id': identity, 'saved': True}


def make_snapshot(root, head, purpose, operation_id=None):
    if any(not head['pages'][k]['revision'] for k in head['order']):
        raise StoreError('missing_page', 'Every snapshot page needs a saved SVG')
    identity = 'snap_' + uuid.uuid4().hex
    directory = Path(root) / STORE / 'snapshots' / identity
    directory.mkdir(parents=True)
    records = []
    for key in head['order']:
        page = page_value(root, head, key)
        source = revision_dir(root, page['revision'])
        tree = parse_svg(page['svg'])
        # Per-scene assets avoid any dependency on the live project.
        scene_dir = directory / 'scenes'
        assets = freeze_assets(root, tree, source, scene_dir)
        path = scene_dir / (key + '.svg')
        atomic(path, xml(tree).encode())
        baseline = head['pages'][key].get('baseline_revision')
        baseline_tree = ET.fromstring((revision_dir(root, baseline) / 'page.svg').read_text()) if baseline else tree
        text_values = lambda t: {n.get(ID_ATTR): ''.join(n.itertext()) for n in t.iter()
                                 if n.tag.split('}')[-1] in ('text', 'tspan')}
        before, after = text_values(baseline_tree), text_values(tree)
        delta = [{'kind': 'text', 'element_id': identity, 'before': before.get(identity), 'after': after.get(identity)}
                 for identity in sorted(set(before) | set(after)) if before.get(identity) != after.get(identity)]
        before_nodes, after_nodes = elements(baseline_tree), elements(tree)
        delta.extend({'kind': 'deleted', 'element_id': identity} for identity in sorted(set(before_nodes) - set(after_nodes))
                     if identity not in before)
        baseline_record = revision_record(root, baseline) if baseline else page
        if baseline_record['notes'] != page['notes']:
            delta.append({'kind': 'notes', 'before': baseline_record['notes'], 'after': page['notes']})
        before_images = {a['element_id']: a['sha256'] for a in baseline_record['assets']}
        after_images = {a['element_id']: a['sha256'] for a in page['assets']}
        delta.extend({'kind': 'asset', 'element_id': identity, 'before': before_images.get(identity),
                      'after': after_images.get(identity)} for identity in sorted(set(before_images) | set(after_images))
                     if before_images.get(identity) != after_images.get(identity))
        def snapshot_assets(items):
            return [{**asset,
                     **({'path': 'scenes/' + asset['path']} if not asset.get('embedded') else {}),
                     'dependencies': snapshot_assets(asset.get('dependencies', []))} for asset in items]
        records.append({'page_key': key, 'revision': page['revision'], 'svg': 'scenes/' + path.name,
                        'svg_sha256': digest(path.read_bytes()), 'notes': page['notes'],
                        'assets': snapshot_assets(assets),
                        'input': head['pages'][key].get('input', {}),
                        'human_edits': page['protected'], 'content_delta': delta,
                        'fact_audit_coverage': 'upstream_baseline_only' if delta else 'upstream_binding'})
    manifest = load(Path(root) / '_internal/00_project/page_manifest.json', {})
    if manifest.get('route', head['route']) != head['route']:
        raise StoreError('route_changed', 'Project route changed after workbench initialization')
    upstream = copy.deepcopy(manifest.get('input_binding', head.get('upstream', {})))
    binding = manifest.get('visual_plan') or manifest.get('visual_contract') or manifest.get('contract')
    standalone = head.get('input_kind') == 'standalone' and not binding
    if head['route'] == 'video' and not binding and not standalone:
        raise StoreError('missing_contract', 'Video snapshot needs the bound visual-plan.json and script.md')
    if binding:
        upstream['visual_contract'] = binding
        declaration = Path(binding.get('path', '')) if isinstance(binding, dict) else None
        if declaration and declaration.is_file():
            data = declaration.read_bytes()
            if binding.get('sha256') and digest(data) != binding['sha256']:
                raise StoreError('contract_changed', 'Upstream declaration changed; rebind explicitly before packaging')
            declaration_data = json.loads(data)
            declared_hash = declaration_data.get('script_hash')
            if (not binding.get('script_hash') or not declared_hash or binding['script_hash'] != declared_hash):
                raise StoreError('script_binding_missing', 'Manifest and declaration must carry the same script_hash')
            atomic(directory / 'upstream/visual-plan.json', data)
            upstream['visual_plan_snapshot'] = 'upstream/visual-plan.json'
            script = declaration.parent / 'script.md'
            if script.is_file():
                data = script.read_bytes()
                if binding.get('script_hash') and digest(data) != binding['script_hash']:
                    raise StoreError('script_changed', 'Script no longer matches declared script_hash')
                atomic(directory / 'upstream/script.md', data)
                upstream['script_snapshot'] = 'upstream/script.md'
                upstream['script_sha256'] = digest(data)
            elif head['route'] == 'video':
                raise StoreError('missing_script', 'Video snapshot needs the bound script.md')
        elif head['route'] == 'video':
            raise StoreError('missing_contract', 'Video snapshot needs the bound visual-plan.json')
    # Preserve the exact declaration and script bytes when their recorded paths exist.
    for name, value in list(upstream.items()):
        if isinstance(value, str) and name.endswith(('path', 'file')):
            source = Path(value)
            if source.is_file():
                source_bytes = source.read_bytes()
                expected = upstream.get(name[:-len('_path')] + '_sha256') if name.endswith('_path') else None
                if expected and digest(source_bytes) != expected:
                    raise StoreError('upstream_changed', 'Bound production input changed', path=str(source))
                destination = directory / 'upstream' / (digest(source_bytes) + '-' + source.name)
                atomic(destination, source_bytes)
                upstream[name + '_snapshot'] = str(destination.relative_to(directory))
                upstream[name + '_sha256'] = digest(destination.read_bytes())
    snapshot = {'version': 'svg-workbench-snapshot/1', 'snapshot_id': identity, 'created_at': now(),
                'purpose': purpose, 'route': head['route'], 'order': list(head['order']), 'pages': records,
                'upstream': upstream, 'operation_id': operation_id,
                'canvas': project_frame(root).as_dict(),
                'input_kind': 'standalone' if standalone else 'production'}
    snapshot['content_binding'] = 'changed_needs_check' if any(p['content_delta'] for p in records) else 'baseline'
    if binding and upstream.get('visual_plan_snapshot'):
        declarations = declaration_data.get('screens', declaration_data.get('blueprints', []))
        declared = [item.get('screen_id', item.get('blueprint_id')) for item in declarations]
        snapshot['collection_delta'] = {'added': [key for key in head['order'] if key not in declared],
                                        'removed': [key for key in declared if key not in head['order']]}
        if any(snapshot['collection_delta'].values()):
            snapshot['content_binding'] = 'changed_needs_check'
    if head['route'] == 'video' and standalone:
        snapshot['content_binding'] = 'unbound'
    atomic(directory / 'snapshot.json', encoded(snapshot))
    atomic(directory / 'snapshot.sha256', digest(encoded(snapshot)).encode())
    return {**snapshot, 'root': str(directory), 'path': str(directory / 'snapshot.json'), 'ok': True}


def snapshot(root, purpose='slides'):
    root = Path(root).resolve()
    with locked(root):
        return make_snapshot(root, initialize(root), purpose)


def load_snapshot(root, path):
    """Verify a selected output snapshot without consulting mutable current pages."""
    root = Path(root).resolve()
    path = inside(root / STORE / 'snapshots', path)
    if path.name != 'snapshot.json' or not KEY.fullmatch(path.parent.name):
        raise StoreError('invalid_snapshot', 'Select an existing workbench snapshot.json')
    raw = path.read_bytes()
    if (path.parent / 'snapshot.sha256').read_text().strip() != digest(raw):
        raise StoreError('damaged_snapshot', 'Snapshot manifest fingerprint changed')
    data = json.loads(raw)
    if data.get('version') != 'svg-workbench-snapshot/1' or data.get('snapshot_id') != path.parent.name:
        raise StoreError('invalid_snapshot', 'Snapshot identity or format is invalid')
    order = data.get('order', [])
    pages = data.get('pages', [])
    if (not order or len(order) != len(set(order)) or [p.get('page_key') for p in pages] != order
            or any(not isinstance(key, str) or not KEY.fullmatch(key) for key in order)):
        raise StoreError('invalid_snapshot', 'Snapshot page identities/order are invalid')
    def checked(relative, expected):
        asset = inside(path.parent, relative)
        if not expected or digest(asset.read_bytes()) != expected:
            raise StoreError('damaged_snapshot', 'Snapshot dependency changed', path=str(asset))
        return asset
    def assets(items):
        for item in items:
            if not item.get('embedded'):
                checked(item['path'], item['sha256'])
            assets(item.get('dependencies', []))
    for page in pages:
        if page.get('svg') != 'scenes/' + page['page_key'] + '.svg':
            raise StoreError('invalid_snapshot', 'Scene path differs from its page identity')
        checked(page['svg'], page['svg_sha256'])
        assets(page.get('assets', []))
    upstream = data.get('upstream', {})
    binding = upstream.get('visual_contract', {})
    standalone = data.get('input_kind') == 'standalone' and data.get('content_binding') == 'unbound' and not binding
    if data.get('route') == 'video' and not standalone:
        plan_path = checked(upstream.get('visual_plan_snapshot', ''), binding.get('sha256'))
        script_path = checked(upstream.get('script_snapshot', ''), binding.get('script_hash'))
        if json.loads(plan_path.read_bytes()).get('script_hash') != digest(script_path.read_bytes()):
            raise StoreError('damaged_snapshot', 'Declaration and script snapshot binding differ')
    for name, value in upstream.items():
        if name.endswith('_snapshot') and name not in ('visual_plan_snapshot', 'script_snapshot'):
            checked(value, upstream.get(name[:-len('_snapshot')] + '_sha256'))
    return {**data, 'ok': True, 'path': str(path), 'root': str(path.parent)}


def _page_input(command):
    value = command.get('page') if isinstance(command.get('page'), dict) else command
    key = value.get('page_key') or command.get('page_key')
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise StoreError('invalid_page', 'A new page needs a stable page_key')
    assets = value.get('source_assets', [])
    if not isinstance(assets, list) or any(not isinstance(item, str) for item in assets):
        raise StoreError('invalid_page', 'source_assets must be an array of asset IDs')
    if value.get('mode', '读') not in ('讲', '读'):
        raise StoreError('invalid_page', 'mode must be 讲 or 读')
    return key, {
        'page_key': key,
        'title': str(value.get('title') or key),
        'content': str(value.get('content') or ''),
        'notes': str(value.get('notes') or ''),
        'mode': value.get('mode') or '读',
        'source_assets': list(value.get('source_assets') or []),
        'copy_confirmed': value.get('copy_confirmed') is True,
    }


def update_content_collection(root, head):
    path = Path(root) / '_internal/01_content/page_content.json'
    data = load(path, {})
    previous = {page.get('page_key'): page for page in data.get('pages', [])}
    pages = [previous.get(key) or copy.deepcopy(head['pages'][key]['input']) for key in head['order']]
    data['pages'] = pages
    available = {asset.get('asset_id') for asset in load(Path(root) / '_internal/00_project/source/source_assets.json', {}).get('assets', [])}
    used = {asset for page in pages for asset in page.get('source_assets', [])}
    unused = dict(data.get('unused_assets') or {})
    for asset in sorted(used): unused.pop(asset, None)
    for asset in sorted(available - used): unused.setdefault(asset, 'Page removed from the workbench; source asset retained.')
    data['unused_assets'] = unused
    desired = encoded(data)
    if not path.is_file() or path.read_bytes() != desired:
        atomic(path, desired)


def add_page(root, head, command, prepared_candidate, operation_id):
    if prepared_candidate is None:
        raise StoreError('missing_candidate', 'Adding a page needs a complete candidate SVG')
    key, page_input = _page_input(command)
    if key in head['pages'] or key in head.get('deleted_pages', {}):
        raise StoreError('duplicate_page', 'Page key already exists', page_key=key)
    if command.get('base_order') != head['order']:
        raise StoreError('conflict', 'Page order changed')
    available = {asset['asset_id'] for asset in load(Path(root) / '_internal/00_project/source/source_assets.json', {}).get('assets', [])}
    if set(page_input['source_assets']) - available:
        raise StoreError('invalid_page', 'Unknown source asset IDs')
    candidate = Path(prepared_candidate)
    before = command.get('before_page_key')
    if before is not None and before not in head['order']:
        raise StoreError('unknown_page', 'before_page_key is not in the current order')
    layout_id = command.get('layout_id')
    if layout_id is not None and (not isinstance(layout_id, str)
                                  or (layout_id and not LAYOUT_KEY.fullmatch(layout_id))):
        raise StoreError('invalid_layout', 'layout_id must be a template layout key')
    tree = parse_svg(candidate.read_text())
    record = create_revision(root, key, xml(tree), candidate.parent, page_input['notes'], {}, 'model', None, operation_id)
    head['pages'][key] = {'revision': record['revision'], 'baseline_revision': record['revision'],
                          'title': page_input['title'], 'input': page_input}
    if layout_id is not None:
        head['pages'][key]['layout_id'] = layout_id
    order = list(head['order'])
    if before is None:
        order.append(key)
    else:
        order.insert(order.index(before), key)
    head['order'] = order
    head['collection_managed'] = True
    return {'ok': True, 'page_key': key, 'revision': record['revision'], 'order': order, 'added': True}


def delete_page(root, head, command):
    key = command.get('page_key')
    if key not in head['pages']:
        raise StoreError('unknown_page', 'Unknown page', page_key=key)
    if len(head['order']) <= 1:
        raise StoreError('last_page', 'Cannot delete the only page')
    if command.get('base_order') != head['order']:
        raise StoreError('conflict', 'Page order changed')
    current = head['pages'][key]
    if command.get('base_revision') != current['revision']:
        raise StoreError('conflict', 'Page changed before deletion', current_revision=current['revision'])
    head.setdefault('deleted_pages', {})[key] = {**copy.deepcopy(current), 'deleted_at': now()}
    head['order'].remove(key)
    head['pages'].pop(key)
    head['collection_managed'] = True
    for task in head['tasks'].values():
        if task.get('status') == 'pending' and key in task.get('pages', {}):
            task.setdefault('removed_pages', {})[key] = task['pages'].pop(key)
            if not task['pages']:
                task['status'] = 'cancelled'
    return {'ok': True, 'page_key': key, 'order': list(head['order']), 'deleted': True}


def commit(root, command, browser=False):
    root = Path(root).resolve()
    if not isinstance(command, dict):
        raise StoreError('invalid_command', 'Expected command object')
    with locked(root) as base:
        head = initialize(root)
        op = command.get('op')
        if op == 'state':
            public = {key: value for key, value in head.items() if key != 'operations'}
            if not browser:
                public['tasks'] = {key: task for key, task in head['tasks'].items() if task.get('status') == 'pending'}
            return {**public, 'ok': True}
        if op == 'task':
            task = head['tasks'].get(command.get('task_id'))
            if not task or task.get('status') != 'pending':
                raise StoreError('inactive_task', 'Only a pending task is an active modification instruction')
            return {'ok': True, 'task': copy.deepcopy(task)}
        if op == 'get':
            value = page_value(root, head, command.get('page_key'))
            requested = command.get('revision')
            if requested:
                record = revision_record(root, requested)
                if record['page_key'] != command.get('page_key'):
                    raise StoreError('invalid_revision', 'Revision belongs to another page')
                directory = revision_dir(root, requested)
                value = {**record, 'svg': (directory / 'page.svg').read_text(),
                         'svg_path': str(directory / 'page.svg')}
            history = []
            revision = value['revision']
            while revision:
                record = revision_record(root, revision)
                history.append({k: record[k] for k in ('revision', 'parent', 'author', 'created_at')})
                revision = record['parent']
            return {**value, 'history': history, 'ok': True}
        identity = command.get('operation_id')
        if not isinstance(identity, str) or not KEY.fullmatch(identity):
            raise StoreError('invalid_operation', 'Writes need a stable operation_id')
        request_hash = digest(encoded(command))
        previous = head['operations'].get(identity)
        if previous:
            if previous['request_hash'] != request_hash:
                raise StoreError('operation_reused', 'Operation ID used with a different command')
            return previous['receipt']
        request_path = base / 'commands' / (identity + '.json')
        pending = load(request_path)
        if pending and pending != command:
            raise StoreError('operation_reused', 'Operation ID used with a different command')
        try:
            prepared_candidate = None
            if command.get('candidate'):
                if browser and command.get('author') == 'model':
                    raise StoreError('invalid_author', 'Browser cannot submit model candidates')
                if browser or command.get('author', 'model') != 'model':
                    raise StoreError('invalid_candidate', 'Candidates are submitted by model CLI')
                prepared_candidate = prepare_candidate(root, command)
            # Journal the command after all mutable model inputs have been pinned.
            atomic(request_path, encoded(command))
            if op == 'save':
                result = save_page(root, head, command, browser, prepared_candidate)
            elif op == 'add_page':
                if browser: raise StoreError('invalid_command', 'Page creation is a model workbench action')
                result = add_page(root, head, command, prepared_candidate, identity)
            elif op == 'delete_page':
                if browser: raise StoreError('invalid_command', 'Page deletion is a model workbench action')
                result = delete_page(root, head, command)
            elif op == 'feedback':
                if not browser:
                    raise StoreError('human_action_required', 'Feedback authorization is submitted by the workbench')
                result = feedback(head, command)
            elif op == 'snapshot':
                result = make_snapshot(root, head, command.get('purpose', head['route']), identity)
            elif op == 'checkout':
                if browser:
                    raise StoreError('invalid_command', 'Candidate checkout is a model CLI action')
                key = command.get('page_key')
                current = page_value(root, head, key)
                destination = base / 'candidates' / (identity + '.svg')
                destination.parent.mkdir(parents=True, exist_ok=True)
                if current['revision']:
                    tree = ET.fromstring(current['svg'])
                    source = revision_dir(root, current['revision'])
                    for node in tree.iter():
                        for attribute in ('href', XLINK):
                            href = node.get(attribute, '')
                            if node.tag.split('}')[-1] == 'image' and href and not href.startswith('data:'):
                                node.set(attribute, os.path.relpath(source / href, destination.parent))
                    atomic(destination, xml(tree).encode())
                result = {'ok': True, 'page_key': key, 'base_revision': current['revision'],
                          'candidate': str(destination), 'notes': current['notes'],
                          'protected': current['protected']}
            elif op == 'order':
                order = command.get('order')
                if not isinstance(order, list) or len(order) != len(set(order)) or set(order) != set(head['pages']):
                    raise StoreError('invalid_order', 'Order must contain every page once')
                if command.get('base_order') != head['order']:
                    raise StoreError('conflict', 'Page order changed')
                head['order'] = order
                result = {'ok': True, 'order': order}
            elif op == 'restore':
                if not browser:
                    raise StoreError('human_action_required', 'Restore is a human workbench action')
                key = command.get('page_key')
                old = revision_record(root, command.get('revision'))
                current = page_value(root, head, key)
                if old['page_key'] != key or command.get('base_revision') != current['revision']:
                    raise StoreError('conflict', 'Restore baseline or page identity changed')
                source = revision_dir(root, old['revision'])
                record = create_revision(root, key, (source / 'page.svg').read_text(), source,
                                         old['notes'], old['protected'], 'human', current['revision'], identity)
                view = root / VIEW / (key + '.svg')
                head['pages'][key]['previous_view_sha256'] = digest(view.read_bytes())
                head['pages'][key]['revision'] = record['revision']
                result = {'ok': True, 'page_key': key, 'revision': record['revision'], 'saved': True}
            elif op == 'resolve':
                if browser:
                    raise StoreError('invalid_command', 'Task results are submitted by model CLI')
                task = head['tasks'].get(command.get('task_id'))
                if not task:
                    raise StoreError('unknown_task', 'Task not found')
                if not command.get('note'):
                    raise StoreError('invalid_result', 'Task result needs a note')
                results = command.get('results', {})
                if set(results) != set(task['pages']):
                    raise StoreError('invalid_result', 'Results must cover all task pages')
                for key, rev in results.items():
                    if revision_record(root, rev)['page_key'] != key:
                        raise StoreError('invalid_result', 'Result revision belongs to another page')
                task.update(status='resolved', results=results, note=command['note'], resolved_at=now())
                result = {'ok': True, 'task_id': task['task_id'], 'status': 'resolved'}
            else:
                raise StoreError('invalid_command', 'Unknown workbench operation')
        except StoreError as error:
            if not request_path.exists():
                atomic(request_path, encoded(command))
            result = {'ok': False, 'code': error.code, 'error': str(error), **error.details,
                      'recovery': str(request_path)}
            if (base / 'commands' / identity / 'original.svg').exists():
                result['candidate_recovery'] = str(base / 'commands' / identity / 'original.svg')
        # Receipt and page pointers become durable together, before compatibility rebuild.
        result['operation_id'] = identity
        head['operations'][identity] = {'request_hash': request_hash, 'receipt': result}
        head['updated_at'] = now()
        atomic(base / 'head.json', encoded(head))
        if result.get('ok'):
            rebuild(root, head, check=False)
        return result


def record_render(root, key, revision, png, renderer):
    root = Path(root).resolve()
    with locked(root) as base:
        head = initialize(root)
        record = revision_record(root, revision)
        if record['page_key'] != key:
            raise StoreError('invalid_render', 'Render revision belongs to another page')
        data = Path(png).read_bytes()
        target = base / 'renders' / revision / 'page.png'
        atomic(target, data)
        result = {'revision': revision, 'png_sha256': digest(data), 'svg_sha256': record['svg_sha256'],
                  'assets': record['assets'], 'renderer': renderer, 'created_at': now()}
        atomic(target.parent / 'render.json', encoded(result))
        if head['pages'].get(key, {}).get('revision') == revision:
            atomic(root / '_internal/03_png_preview/pages' / (key + '.png'), data)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--command-json', action='store_true', help='Read JSON command from stdin')
    parser.add_argument('--browser', action='store_true', help='Restricted human transport mode')
    parser.add_argument('--state', action='store_true')
    args = parser.parse_args()
    try:
        result = commit(args.root, json.load(sys.stdin) if args.command_json else {'op': 'state'}, args.browser)
    except (StoreError, OSError, ValueError) as error:
        result = {'ok': False, 'code': getattr(error, 'code', 'io_error'), 'error': str(error),
                  **getattr(error, 'details', {})}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
