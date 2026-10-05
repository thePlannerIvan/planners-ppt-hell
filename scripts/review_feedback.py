"""反馈的 Skill 侧：形状校验、绑定核对、SVG 轻量直改写回、轮次留档。

**写反馈的人变了。** 以前是 `review_server.py` 在提交那一刻校验并写盘；现在是**页面自己**
经宿主（DSH 侧栏 / `serve-review.mjs`）把整份状态写进 `feedback.json` —— 宿主不解释内容。
所以校验、直改落地与留档都归 Skill：

  · `consume(root)` —— 模型这一侧的**收件口**：形状校验 + 绑定核对 + `svg_edits` 确定性写回 SVG + 规范化写回 + 把这一轮留档（幂等）。
"""
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from project_state import (PNG, REVIEW, SVG, VALIDATION, content, digest, event, local,
                           page_version, read, review_current, review_snapshot, sha, write)

HISTORY = 'history'
APPLIED_EDITS_FILE = 'applied_svg_edits.json'
# 人改完那几版 SVG 的快照目录（PNG 的 versions/ 在同一个父目录下）。
VERSIONS = f'{REVIEW}/versions'
TREE_PATH_RE = re.compile(r'^0(?:\.\d+)*$')
SVG_NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG_NS)
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')


def _round_paths(root):
    history = root/REVIEW/HISTORY
    rounds = []
    if history.is_dir():
        for path in history.iterdir():
            match = re.fullmatch(r'round-(\d+)\.json', path.name)
            if match:
                rounds.append((int(match.group(1)), path))
    rounds.sort()
    return rounds


def _submitted_at(data):
    """这一轮的提交时刻。页面写在 `provenance.submitted_at`；兼容写在顶层的老形状。"""
    provenance = data.get('provenance') if isinstance(data.get('provenance'), dict) else {}
    return str(provenance.get('submitted_at') or data.get('submitted_at') or '')


def content_key(page, feedback='', annotations=None, assets=None):
    """一条意见的**内容身份**：哪一页 + 那句话说的是什么。"""
    canonical = json.dumps({
        'page': str(page),
        'feedback': str(feedback or '').strip(),
        'annotations': sorted(str(a.get('text') or '').strip() for a in (annotations or []) if isinstance(a, dict)),
        'assets': sorted((str(a.get('asset_key') or ''), str(a.get('operation') or ''), str(a.get('path') or ''))
                         for a in (assets or []) if isinstance(a, dict)),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:16]


def closed_keys(root):
    """已经**关闭**的意见（`resolve` 过）的内容身份集合：`{(page, content_key)}`。"""
    resolutions = read(Path(root)/REVIEW/'resolutions.json', {})
    closed = set()
    missing = []
    for resolution_id, record in (resolutions.items() if isinstance(resolutions, dict) else []):
        if not isinstance(record, dict):
            continue
        entries = [e for e in (record.get('closed') or []) if isinstance(e, dict) and e.get('page') is not None and e.get('key')]
        if not entries:
            missing.append(str(resolution_id))
        for entry in entries:
            closed.add((str(entry['page']), str(entry['key'])))
    if missing:
        wanted = set(missing)
        for item in _items_from_history(root):
            if str(item.get('id')) not in wanted:
                continue
            pages = item.get('pages') if isinstance(item.get('pages'), list) else []
            if len(pages) == 1:
                closed.add((str(pages[0]), content_key(pages[0], item.get('feedback'), item.get('annotations'), item.get('assets'))))
            elif pages:
                closed.add(('overall', content_key('overall', item.get('feedback'))))
    return closed


def _items_from_history(root):
    """历史归档（`history/*.json`）里出现过的条目原文。给 `closed_keys` 补老记录用。"""
    for path in sorted((Path(root)/REVIEW/HISTORY).glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('items'), list):
            for item in data['items']:
                if isinstance(item, dict) and item.get('id'):
                    yield item


def _item_id(scope, submitted_at):
    """反馈条目的 id：**由「哪一页 + 哪一轮」定出来**，不用随机 uuid。"""
    return hashlib.sha1((str(scope)+'|'+str(submitted_at)).encode('utf-8')).hexdigest()[:16]


def _serialize(data):
    return json.dumps(data, ensure_ascii=False, indent=2)+'\n'


def archive(root, serialized):
    """把一份反馈原文留档到 `_internal/05_review/history/round-NN.json`。"""
    history = root/REVIEW/HISTORY
    rounds = _round_paths(root)
    if rounds and rounds[-1][1].read_text(encoding='utf-8') == serialized:
        return None
    target = history/f'round-{(rounds[-1][0]+1 if rounds else 1):02d}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding='utf-8')
    return target


def archive_round(root):
    """旧写入口的留档：把**即将被覆盖**的 `feedback.json` 原文留档。"""
    current = root/REVIEW/'feedback.json'
    if not current.is_file():
        return None
    return archive(root, current.read_text(encoding='utf-8'))


def archive_consumed(root, document):
    """收件口的留档：一轮反馈被模型**读到**时留一份。同一提交时刻只留一次。"""
    rounds = _round_paths(root)
    if rounds:
        try:
            previous = json.loads(rounds[-1][1].read_text(encoding='utf-8'))
        except ValueError:
            previous = None
        if isinstance(previous, dict) and _submitted_at(previous) == _submitted_at(document):
            return None
    return archive(root, _serialize(document))


def _fmt_num(val):
    val = round(float(val), 2)
    return str(int(val)) if val.is_integer() else str(val)


def _find_by_tree_path(svg_root, tree_path):
    if not TREE_PATH_RE.match(str(tree_path or '')):
        return None
    parts = [int(x) for x in str(tree_path).split('.')]
    if parts[0] != 0:
        return None
    curr = svg_root
    for idx in parts[1:]:
        children = list(curr)
        if idx < 0 or idx >= len(children):
            return None
        curr = children[idx]
    return curr


def validate_svg_edits(svg_edits):
    """校验页面传回的 `svg_edits` 列表并返回规范化后的列表。"""
    if svg_edits is None:
        return []
    if not isinstance(svg_edits, list):
        raise ValueError('Invalid svg_edits: must be a list')
    normalized = []
    for raw in svg_edits:
        if not isinstance(raw, dict):
            raise ValueError('Invalid svg_edit item')
        rid = str(raw.get('review_id') or '').strip()
        if not TREE_PATH_RE.match(rid):
            raise ValueError(f'Invalid svg_edit review_id: {rid!r}')
        item = {'review_id': rid}
        if raw.get('tag'):
            item['tag'] = str(raw['tag'])
        if raw.get('deleted'):
            item['deleted'] = True
        if 'text' in raw and raw['text'] is not None:
            item['text'] = str(raw['text'])
        if 'lines' in raw and isinstance(raw['lines'], list):
            item['lines'] = [str(line) for line in raw['lines']]
        if raw.get('font_size') is not None:
            fs = raw['font_size']
            if not isinstance(fs, (int, float)) or not math.isfinite(fs) or not (6 <= float(fs) <= 360):
                raise ValueError('Invalid svg_edit font_size')
            item['font_size'] = round(float(fs), 1)
        dx = raw.get('dx', 0)
        dy = raw.get('dy', 0)
        if not isinstance(dx, (int, float)) or not isinstance(dy, (int, float)) or not (math.isfinite(dx) and math.isfinite(dy)):
            raise ValueError('Invalid svg_edit dx/dy')
        if abs(float(dx)) > 2400 or abs(float(dy)) > 1600:
            raise ValueError('svg_edit dx/dy out of canvas bounds')
        item['dx'] = round(float(dx), 2)
        item['dy'] = round(float(dy), 2)
        normalized.append(item)
    return normalized


def apply_svg_edits_to_file(svg_path, svg_edits):
    """将 `svg_edits`（改字、改字号、拖拽位移 Δx/Δy、删除元素）确定性应用到 `.svg` 文件。"""
    svg_path = Path(svg_path)
    if not svg_path.is_file() or not svg_edits:
        return False
    tree = ET.parse(svg_path)
    svg_root = tree.getroot()
    modified = False

    # Pre-resolve parent_map and target nodes by tree_path before removing any elements
    parent_map = {child: parent for parent in svg_root.iter() for child in parent}
    resolved_edits = [
        (edit, _find_by_tree_path(svg_root, edit.get('review_id')))
        for edit in svg_edits
    ]

    for edit, node in resolved_edits:
        if node is None:
            continue
        if edit.get('deleted'):
            parent = parent_map.get(node)
            if parent is not None and node in list(parent):
                parent.remove(node)
                modified = True
            continue
        tag = node.tag.split('}')[-1]

        # 1) Text modification (preserves <tspan> attributes if multi-line)
        tspans = [c for c in list(node) if c.tag.split('}')[-1] == 'tspan']
        if 'lines' in edit and isinstance(edit['lines'], list) and tspans:
            lines = edit['lines']
            for idx, tspan in enumerate(tspans):
                if idx < len(lines):
                    tspan.text = str(lines[idx])
            modified = True
        elif 'text' in edit and edit['text'] is not None:
            new_text = str(edit['text'])
            if tspans:
                split_lines = new_text.split('\n')
                if len(split_lines) == len(tspans):
                    for tspan, line_str in zip(tspans, split_lines):
                        tspan.text = line_str
                else:
                    tspans[0].text = new_text.replace('\n', ' ')
                    for extra in tspans[1:]:
                        extra.text = ''
            else:
                node.text = new_text
            modified = True

        # 2) Font size modification
        if edit.get('font_size') is not None:
            fs_str = _fmt_num(edit['font_size'])
            node.set('font-size', fs_str)
            style_attr = node.get('style')
            if style_attr and 'font-size' in style_attr:
                node.set('style', re.sub(r'font-size\s*:\s*[^;]+', f'font-size:{fs_str}px', style_attr))
            for tspan in tspans:
                if tspan.get('font-size'):
                    tspan.set('font-size', fs_str)
            modified = True

        # 3) Position delta (dx, dy)
        dx = float(edit.get('dx') or 0.0)
        dy = float(edit.get('dy') or 0.0)
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            can_shift_xy = (
                tag in ('text', 'rect', 'image', 'use')
                and node.get('x') is not None
                and node.get('y') is not None
            )
            shifted_xy = False
            if can_shift_xy:
                try:
                    ox = float(node.get('x'))
                    oy = float(node.get('y'))
                    node.set('x', _fmt_num(ox + dx))
                    node.set('y', _fmt_num(oy + dy))
                    if tag == 'text':
                        for tspan in tspans:
                            if tspan.get('x') is not None:
                                try:
                                    tspan.set('x', _fmt_num(float(tspan.get('x')) + dx))
                                except ValueError:
                                    pass
                            if tspan.get('y') is not None:
                                try:
                                    tspan.set('y', _fmt_num(float(tspan.get('y')) + dy))
                                except ValueError:
                                    pass
                    shifted_xy = True
                    modified = True
                except ValueError:
                    shifted_xy = False
            if not shifted_xy:
                existing_tf = (node.get('transform') or '').strip()
                tr = f'translate({_fmt_num(dx)}, {_fmt_num(dy)})'
                node.set('transform', f'{tr} {existing_tf}'.strip() if existing_tf else tr)
                modified = True

    if modified:
        xml_str = ET.tostring(svg_root, encoding='unicode')
        svg_path.write_text(xml_str + '\n', encoding='utf-8')
    return modified


def _rerender_png_if_possible(root, key, old_version=None):
    """尝试重渲微调后的 SVG 为 PNG，并保存修改前版本到 `_internal/05_review/versions/`。"""
    svg = root / SVG / f'{key}.svg'
    png = root / PNG / f'{key}.png'
    if png.is_file() and old_version:
        old_backup = root / REVIEW / 'versions' / f'{key}-{old_version}.png'
        old_backup.parent.mkdir(parents=True, exist_ok=True)
        if not old_backup.is_file():
            import shutil
            shutil.copy2(png, old_backup)
    try:
        from render_svg_png import PLAYWRIGHT_SNIPPET
        subprocess.run(
            [sys.executable, '-c', PLAYWRIGHT_SNIPPET, str(root / PNG), str(svg)],
            capture_output=True, text=True, timeout=25, check=True,
        )
        return True
    except Exception:
        return False


def apply_pending_svg_edits(root, data):
    """在收件（`consume`）时幂等执行每页的 `svg_edits`，并同步更新版本快照与校验戳。

    这样：
    - **纯微调直通（Path A）**：用户只改了文字/字号/位置并点「本页通过」，SVG 与 PNG 原地更新，
      版本戳与看图记录自动顺延，0 秒直接满足 `approved(root)` 进入 `EXPORT`，无需唤醒大模型重画。
    - **微调 + 批注（Path B）**：用户既微调了某处文字/位置，又写了 `feedback`/`annotations` 让模型改别处，
      微调先写入 `.svg`，模型在此基础上继续修改，绝不覆盖用户的手动微调。
    """
    root = Path(root)
    supplied = data.get('pages')
    if not isinstance(supplied, dict):
        return []
    review_id = str(data.get('review_id') or '')
    applied_ledger_path = root / REVIEW / APPLIED_EDITS_FILE
    ledger = read(applied_ledger_path, {})
    if not isinstance(ledger, dict):
        ledger = {}

    pages_by_key = {p['page_key']: p for p in content(root).get('pages', [])}
    snapshot = review_snapshot(root)
    inspections = read(root / VALIDATION / 'inspections.json', {})
    applied_keys = []

    for key, entry in supplied.items():
        if not isinstance(entry, dict) or key not in pages_by_key:
            continue
        edits = validate_svg_edits(entry.get('svg_edits'))
        if not edits:
            continue
        edits_hash = digest(edits)[:16]
        ledger_key = f'{review_id}:{key}:{edits_hash}'
        if ledger_key in ledger:
            continue

        old_ver = (snapshot.get('versions') or {}).get(key)
        svg_path = root / SVG / f'{key}.svg'
        if not apply_svg_edits_to_file(svg_path, edits):
            continue

        _rerender_png_if_possible(root, key, old_version=old_ver)
        new_ver = page_version(root, pages_by_key[key])
        png_path = root / PNG / f'{key}.png'
        new_png_sha = sha(png_path) if png_path.is_file() else ''

        # Update validation & inspection stamps if this page was previously rendered & inspected
        val_path = root / VALIDATION / f'{key}.json'
        val_rec = read(val_path, {})
        if isinstance(val_rec, dict) and val_rec:
            val_rec['version'] = new_ver
            val_rec['png_sha256'] = new_png_sha
            write(val_path, val_rec)
            if isinstance(inspections, dict) and key in inspections:
                inspections[key]['render_token'] = digest(val_rec)
                write(root / VALIDATION / 'inspections.json', inspections)

        if isinstance(snapshot.get('versions'), dict):
            snapshot['versions'][key] = new_ver
        if isinstance(snapshot.get('png_hashes'), dict):
            snapshot['png_hashes'][key] = new_png_sha

        entry['version'] = new_ver
        entry['png_sha256'] = new_png_sha
        entry['svg_edits_applied'] = edits_hash
        # 人改完那一版 SVG 单独留档。模型后来整份重写这一页时，这是唯一的还原底本 ——
        # PNG 早就有 versions/ 待遇，SVG（真正的源文件）反而没有，所以人被改掉的东西找不回来。
        svg_snapshot = root/REVIEW/VERSIONS/f'{key}-{new_ver[:12]}.svg'
        svg_snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(svg_path, svg_snapshot)
        ledger[ledger_key] = {
            'page': key,
            'edits_hash': edits_hash,
            # 逐笔内容，不只是哈希。账本原来只存 digest，连「人到底改了什么」都查不回来，
            # 模型想「以人为基版」也无从下手；一笔最多几条，存全文不值几个字节。
            'edits': edits,
            'old_version': old_ver,
            'new_version': new_ver,
            'svg_sha256': sha(svg_path),
            'svg_snapshot': str(svg_snapshot.relative_to(root)).replace('\\', '/'),
            'new_png_sha256': new_png_sha,
            'applied_at': datetime.now(timezone.utc).isoformat(),
        }
        applied_keys.append(key)

    if applied_keys:
        write(applied_ledger_path, ledger)
        # Also refresh 02_visual_review.html with the updated svgMarkup / versions while keeping review_id
        html_path = root / '02_visual_review.html'
        if html_path.is_file():
            try:
                from generate_review_html import prepare_inline_svg
                html_text = html_path.read_text(encoding='utf-8')
                m = re.search(r'const data=(\{.*?\});\n', html_text)
                if m:
                    embedded = json.loads(m.group(1))
                    for p_item in embedded.get('pages', []):
                        pk = p_item.get('key')
                        if pk in applied_keys:
                            p_item['version'] = snapshot['versions'][pk]
                            p_item['png_sha256'] = snapshot['png_hashes'][pk]
                            p_item['svgMarkup'] = prepare_inline_svg(root, pk)
                    new_json = json.dumps(embedded, ensure_ascii=False).replace('<', '\\u003c')
                    html_text = html_text[:m.start(1)] + new_json + html_text[m.end(1):]
                    html_path.write_text(html_text, encoding='utf-8')
                    snapshot['html_sha256'] = sha(html_path)
            except Exception:
                pass
        if snapshot:
            write(root / REVIEW / 'snapshot.json', snapshot)
        event(root, 'svg_edits_applied', pages=applied_keys)
    return applied_keys


def validate_document(root, data, strict=True, suppressed=None):
    """校验一份反馈，返回规范化后的文档（不改盘）。"""
    root = Path(root)
    snapshot = review_snapshot(root)
    if not isinstance(data, dict):
        raise ValueError('反馈不是一个对象')
    supplied = data.get('pages')
    if not isinstance(supplied, dict) or not supplied:
        raise ValueError('反馈里没有 pages')
    if strict:
        expected = snapshot.get('versions') or {}
        if str(data.get('review_id') or '') != str(snapshot.get('review_id') or ''):
            raise ValueError('Review is stale. Reload the current review; decisions were not saved.')
        if set(supplied) != set(expected):
            raise ValueError('Feedback must cover the exact page set')
    result = {}
    items = []
    submitted_at = _submitted_at(data)
    closed = closed_keys(root)
    overall = str(data.get('overall_feedback', '')).strip()
    incoming = data.get('items') if isinstance(data.get('items'), list) else []
    given = {}
    given_overall = None
    for item in incoming:
        if not isinstance(item, dict) or not str(item.get('id') or ''):
            continue
        pages = item.get('pages') if isinstance(item.get('pages'), list) else []
        if len(pages) == 1:
            given.setdefault(str(pages[0]), str(item['id']))
        elif given_overall is None:
            given_overall = str(item['id'])
    for key, entry in supplied.items():
        if not isinstance(entry, dict):
            raise ValueError('Invalid page feedback')
        decision = entry.get('decision')
        if decision not in {'pending', 'approved', 'revise'}:
            raise ValueError('Invalid decision')
        note = str(entry.get('feedback', '')).strip()
        annotations = entry.get('annotations', [])
        assets = entry.get('assets', [])
        svg_edits = validate_svg_edits(entry.get('svg_edits'))
        if not isinstance(annotations, list) or not isinstance(assets, list):
            raise ValueError('Invalid annotations/assets')
        for region in annotations:
            if not isinstance(region, dict):
                raise ValueError('Invalid region')
            numbers = [region.get(n) for n in ('x', 'y', 'w', 'h')]
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in numbers):
                raise ValueError('Invalid region coordinates')
            x, y, w, h = numbers
            if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00001 or y+h > 1.00001 or not str(region.get('text', '')).strip():
                raise ValueError('Region must be inside page and have feedback')
        declared = {a['asset_key'] for a in (snapshot.get('assets', {}).get(key) or [])}
        permitted = {a['path'] for a in (snapshot.get('assets', {}).get(key) or [])}
        upload_base = root/REVIEW/'uploads'/key
        used = set()
        for asset in assets:
            asset_key = asset.get('asset_key', '')
            operation = asset.get('operation')
            if not asset_key or asset_key in used or operation not in {'add', 'replace', 'crop'}:
                raise ValueError('Unique asset keys and valid operations required')
            used.add(asset_key)
            if declared and (operation == 'add' and asset_key in declared or operation != 'add' and asset_key not in declared):
                raise ValueError('Asset operation does not match displayed image')
            path = local(root, asset.get('path', ''))
            if permitted and str(path.relative_to(root)) not in permitted and upload_base not in path.parents:
                raise ValueError('Asset must be displayed or uploaded for this page')
            if not path.is_file() or asset.get('fit') not in {'contain', 'cover'}:
                raise ValueError('Missing image or invalid fit')
            if upload_base in path.parents and not _is_image(path):
                raise ValueError('Invalid image bytes: '+str(path))
            if not re.fullmatch(r'(original|[1-9]\d*:[1-9]\d*)', str(asset.get('ratio', ''))):
                raise ValueError('Use original or W:H ratio')
            if asset.get('anchor') not in {'center', 'top', 'bottom', 'left', 'right'}:
                raise ValueError('Invalid anchor')
            asset['sha256'] = sha(path)
        # Note: svg_edits alone do NOT force decision='revise' — if user only made direct SVG tweaks,
        # they can approve the page directly without needing a model redraw!
        if note or annotations or assets:
            decision = 'revise'
        if decision == 'revise' and not (note or annotations or assets or overall):
            raise ValueError('Describe the requested change')
        extra_fields = {}
        if svg_edits:
            extra_fields['svg_edits'] = svg_edits
        if entry.get('svg_edits_applied'):
            extra_fields['svg_edits_applied'] = entry['svg_edits_applied']
        if strict:
            result[key] = {
                'decision': decision,
                'feedback': note,
                'annotations': annotations,
                'assets': assets,
                **extra_fields,
                'version': (snapshot.get('versions') or {})[key],
                'png_sha256': (snapshot.get('png_hashes') or {})[key],
            }
        else:
            result[key] = {
                **entry,
                'decision': decision,
                'feedback': note,
                'annotations': annotations,
                'assets': assets,
                **extra_fields,
            }
        if decision == 'revise':
            fingerprint = content_key(key, note, annotations, assets)
            if (str(key), fingerprint) in closed:
                if suppressed is not None:
                    suppressed.append({'page': key, 'content_key': fingerprint, 'reason': 'already_resolved'})
                result[key]['already_resolved'] = True
            else:
                item_obj = {
                    'id': given.get(str(key)) or _item_id(key, submitted_at),
                    'pages': [key],
                    'feedback': note,
                    'annotations': annotations,
                    'assets': assets,
                }
                if svg_edits:
                    item_obj['svg_edits'] = svg_edits
                items.append(item_obj)
    if overall and ('overall', content_key('overall', overall)) not in closed:
        items.append({'id': given_overall or _item_id('overall', submitted_at), 'pages': list(result), 'feedback': overall})
    normalized = {**data, 'pages': result, 'overall_feedback': overall, 'items': items}
    return normalized


def _is_image(path):
    """落地的上传件必须真的是图片。"""
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def consume(root):
    """模型这一侧的收件口：读页面写下的反馈 → 应用 `svg_edits` → 校验 → 这一轮留档。幂等。"""
    root = Path(root)
    path = root/REVIEW/'feedback.json'
    data = read(path, None)
    if not isinstance(data, dict) or not data:
        return None
    snapshot = review_snapshot(root)
    same_review_id = str(data.get('review_id') or '') == str(snapshot.get('review_id') or '')
    applied_svg_pages = []
    if same_review_id:
        try:
            applied_svg_pages = apply_pending_svg_edits(root, data)
            if applied_svg_pages:
                snapshot = review_snapshot(root)
        except Exception:
            applied_svg_pages = []
    try:
        current = review_current(root)
    except (OSError, ValueError):
        current = False
    stale = (str(data.get('review_id') or '') != str(snapshot.get('review_id') or '')) or not current
    suppressed = []
    document = validate_document(root, data, strict=not stale, suppressed=suppressed)
    if document != data or applied_svg_pages:
        write(path, document)
    archived = archive_consumed(root, document)
    return {
        'document': document,
        'stale': stale,
        'path': str(path),
        'suppressed': suppressed,
        'svg_edits_applied': applied_svg_pages,
        'archived': str(archived.relative_to(root)) if archived else '',
    }


def _human_edit_index(root):
    """账本里「每一页最近一次人工改动」，返回 `(整本账, {页: (账目键, 记录)})`。

    同一页可以被改很多次，每次一条；取 `applied_at` 最新的那条当这一页的当前状态。
    """
    ledger = read(Path(root)/REVIEW/APPLIED_EDITS_FILE, {})
    latest = {}
    for key, record in (ledger.items() if isinstance(ledger, dict) else []):
        if not isinstance(record, dict):
            continue
        page = str(record.get('page') or '')
        if not page:
            continue
        previous = latest.get(page)
        if previous is None or str(record.get('applied_at') or '') > str(previous[1].get('applied_at') or ''):
            latest[page] = (key, record)
    return ledger, latest


def human_edits(root):
    """每一页最近一次「人手动改过」的记录。没人改过的页不在里面。"""
    latest = _human_edit_index(root)[1]
    return {page: record for page, (_key, record) in latest.items()}


def human_edit_state(root, page, version):
    """人改的那一笔现在还算不算数。没人改过的页返回 `None`。

    · `carried` —— 当前这一版**就是**人改完那一版，人的改动还在；
    · `acknowledged` —— 不是那一版了，但模型已经就当前这一版交代过怎么处理的；
    · 两个都假 —— 人改过这一页，后来它被整份重写了，而没人交代过。**这就是「白改了」。**
    """
    record = human_edits(root).get(page)
    if not record:
        return None
    ack = record.get('ack') if isinstance(record.get('ack'), dict) else {}
    return {
        'applied_at': record.get('applied_at'),
        'version': record.get('new_version'),
        'edits': record.get('edits') or [],
        'svg_snapshot': record.get('svg_snapshot') or '',
        'carried': str(record.get('new_version') or '') == str(version or ''),
        'acknowledged': str(ack.get('version') or '') == str(version or ''),
        'ack': ack,
    }


def ack_human_edit(root, page, note):
    """就当前这一版记下「人那一笔怎么处理的」，闸门随之放行。

    和 `resolve` 同一条规矩：要写清实际做法（带进新版／被新版替掉／恢复），空话不算 ——
    这条闸门存在的唯一意义就是**不许人的改动被静默丢掉**，一句"已处理"糊过去等于没修。
    """
    root = Path(root)
    text = str(note or '').strip()
    if not text:
        raise ValueError('写下你实际怎么处理人那一笔的（带进新版／被新版替掉／恢复），空话不算')
    pages = {p['page_key']: p for p in content(root)['pages']}
    if page not in pages:
        raise ValueError(f'项目里没有这一页：{page}')
    ledger, latest = _human_edit_index(root)
    if page not in latest:
        raise ValueError(f'{page} 没有人工改动记录，无需确认')
    key, record = latest[page]
    record = dict(record)
    record['ack'] = {
        'version': page_version(root, pages[page]),
        'note': text,
        'at': datetime.now(timezone.utc).isoformat(),
    }
    ledger[key] = record
    write(root/REVIEW/APPLIED_EDITS_FILE, ledger)
    return {'page': page, 'version': record['ack']['version'], 'note': text,
            'svg_snapshot': record.get('svg_snapshot') or '', 'edits': record.get('edits') or []}
