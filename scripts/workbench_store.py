"""Durable SVG revisions. All writers cross commit; compatibility SVGs are views."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STORE = '_internal/06_workbench'
VIEW = '_internal/02_svg_source'
ID_ATTR = 'data-workbench-id'
XLINK = '{http://www.w3.org/1999/xlink}href'
KEY = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}')
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
            'created_at': now()}
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
    if not revision:
        return {'page_key': key, 'revision': None, 'svg': '', 'notes': head['pages'][key]['input'].get('notes', ''),
                'protected': {}}
    record = revision_record(root, revision)
    return {**record, 'svg': (revision_dir(root, revision) / 'page.svg').read_text(),
            'svg_path': str(revision_dir(root, revision) / 'page.svg')}


def get_page(root, key):
    root = Path(root).resolve()
    with locked(root):
        return page_value(root, initialize(root), key)


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


def save_page(root, head, command, browser, prepared_candidate=None):
    key = command.get('page_key')
    current = page_value(root, head, key)
    if command.get('base_revision') != current['revision']:
        raise StoreError('conflict', 'Page changed since this edit started', page_key=key,
                         current_revision=current['revision'], base_revision=command.get('base_revision'))
    author = command.get('author', 'human' if browser else 'model')
    if author not in ('human', 'model') or (browser and author != 'human'):
        raise StoreError('invalid_author', 'Browser cannot submit model candidates')
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
        missing = lost_edits(tree, protected, authorized)
        if missing:
            raise StoreError('human_edits_lost', 'Candidate drops retained human edits', elements=missing,
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
    return {'ok': True, 'page_key': key, 'revision': record['revision'], 'saved': True,
            'rendered': False, 'notes': notes}


def feedback(head, command):
    pages = command.get('pages', {})
    scope = command.get('scope')
    if scope not in ('page', 'deck') or not pages or (scope == 'page' and len(pages) != 1):
        raise StoreError('invalid_feedback', 'Feedback needs page or deck scope and targets')
    for key, item in pages.items():
        if key not in head['pages'] or item.get('revision') != head['pages'][key]['revision']:
            raise StoreError('conflict', 'Feedback baseline changed', page_key=key,
                             current_revision=head['pages'].get(key, {}).get('revision'))
        if not isinstance(item.get('rewrite_elements', []), list):
            raise StoreError('invalid_feedback', 'Rewrite scope must be an element list')
    identity = 'task_' + uuid.uuid4().hex
    head['tasks'][identity] = {'task_id': identity, 'scope': scope, 'pages': copy.deepcopy(pages),
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
    if head['route'] == 'video' and not binding:
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
                'upstream': upstream, 'operation_id': operation_id}
    snapshot['content_binding'] = 'changed_needs_check' if any(p['content_delta'] for p in records) else 'baseline'
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
    if data.get('route') == 'video':
        plan_path = checked(upstream.get('visual_plan_snapshot', ''), binding.get('sha256'))
        script_path = checked(upstream.get('script_snapshot', ''), binding.get('script_hash'))
        if json.loads(plan_path.read_bytes()).get('script_hash') != digest(script_path.read_bytes()):
            raise StoreError('damaged_snapshot', 'Declaration and script snapshot binding differ')
    for name, value in upstream.items():
        if name.endswith('_snapshot') and name not in ('visual_plan_snapshot', 'script_snapshot'):
            checked(value, upstream.get(name[:-len('_snapshot')] + '_sha256'))
    return {**data, 'ok': True, 'path': str(path), 'root': str(path.parent)}


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
        if head['pages'][key]['revision'] == revision:
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
