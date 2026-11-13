#!/usr/bin/env python3
"""把版式选择页的勾选落到 `layouts.json`。

选择页写 `_internal/00_project/layout_selection.json`；这里校验它绑定的 review_id/catalog
是否还是当前版本，然后把 `layouts.json` 收到只保留被选中的家族。未选中的 primitive 不会
被要求制作；previews/anchors 保留（不挡发布，只是不再引用）。
"""

import argparse
import json
from pathlib import Path

PROJECT = '_internal/00_project'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def apply_selection(project):
    project = Path(project).resolve()
    base = project / PROJECT
    selection = read_json(base / 'layout_selection.json', {})
    snapshot = read_json(base / 'template_select_snapshot.json', {})
    if not selection or not selection.get('selected'):
        raise ValueError('layout_selection.json is missing or has no selected families')
    if not snapshot:
        raise ValueError('template_select_snapshot.json is missing; regenerate template-select before applying')
    if selection.get('review_id') != snapshot.get('review_id'):
        raise ValueError('layout selection is stale: review_id differs from template_select_snapshot.json')
    selected = [str(item) for item in selection['selected']]
    document = read_json(base / 'template_pack' / 'layouts.json', {})
    layouts = document.get('layouts') if isinstance(document, dict) else None
    if not isinstance(layouts, list) or not layouts:
        raise ValueError('template_pack/layouts.json is missing or empty')
    chosen = set(selected)
    kept = [item for item in layouts if str(item.get('layout_id')) in chosen]
    missing = sorted(chosen - {str(item.get('layout_id')) for item in kept})
    if missing:
        raise ValueError(f'selection names unknown layouts: {missing}')
    if not kept:
        raise ValueError('selection leaves no layouts')
    document['layouts'] = kept
    document['selection'] = {
        'review_id': selection.get('review_id'),
        'submitted_at': selection.get('submitted_at'),
        'selected': selected,
    }
    pack = (base / 'template_pack').resolve()
    referenced = {str(item.get(key) or '') for item in kept for key in ('preview', 'anchor', 'primitive')}
    for item in layouts:
        if str(item.get('layout_id')) in chosen:
            continue
        for key in ('preview', 'anchor', 'primitive'):
            relative = str(item.get(key) or '')
            if not relative or relative in referenced:
                continue
            path = (pack / relative).resolve()
            if pack in path.parents and path.is_file():
                path.unlink()
    write_json(base / 'template_pack' / 'layouts.json', document)
    return {'ok': True, 'selected': selected, 'layouts': len(kept), 'path': str(base / 'template_pack' / 'layouts.json')}


def main():
    parser = argparse.ArgumentParser(description='Apply layout_selection.json to template_pack/layouts.json')
    parser.add_argument('project_dir')
    args = parser.parse_args()
    try:
        result = apply_selection(args.project_dir)
    except ValueError as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
