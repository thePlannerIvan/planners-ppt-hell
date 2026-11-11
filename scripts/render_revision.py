#!/usr/bin/env python3
"""保存之后异步重渲一页的位图：只有当这一版还是当前版时才写回预览位。

保存只落 SVG；位图（`_internal/03_png_preview/pages/<key>.png`）要等模型跑 `check` 才更新。
人改完字、看缩略图或回到位图态时就会以为「我改的被改回去了」。
这里由保存操作在后台拉起：渲染这一版；若期间又存了新版本，旧版只归档（`renders/<rev>/`），
绝不覆盖当前预览图。

用法（store 内部调用，不供人直接跑）：
    python3 scripts/render_revision.py <project_root> <page_key> <revision>
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workbench_store as store  # noqa: E402


def current_revision(root, key):
    with store.locked(root):
        head = store.initialize(root)
        return head.get('pages', {}).get(key, {}).get('revision')


def main(argv):
    if len(argv) != 4:
        print('usage: render_revision.py <project_root> <page_key> <revision>', file=sys.stderr)
        return 2
    root, key, revision = Path(argv[1]).resolve(), argv[2], argv[3]
    if current_revision(root, key) != revision:
        print(json.dumps({'ok': True, 'skipped': 'stale_revision', 'revision': revision}))
        return 0
    svg = store.revision_dir(root, revision) / 'page.svg'
    if not svg.is_file():
        print(json.dumps({'ok': False, 'error': 'missing_revision_svg'}))
        return 0
    from render_svg_png import PLAYWRIGHT_SNIPPET

    with tempfile.TemporaryDirectory(prefix='ppt-render-') as temporary:
        temp = Path(temporary)
        completed = store.subprocess.run([sys.executable, '-c', PLAYWRIGHT_SNIPPET, str(temp), str(svg)],
                                         capture_output=True, text=True)
        png = temp / (svg.stem + '.png')
        if completed.returncode != 0 or not png.is_file():
            print(json.dumps({'ok': False, 'error': (completed.stderr or 'render produced no png')[-400:]}))
            return 0
        try:
            renderer = 'render_svg_png.py:sha256:' + store.digest(
                (Path(store.__file__).resolve().parent / 'render_svg_png.py').read_bytes())
            result = store.record_render(root, key, revision, png, renderer)
        except Exception as error:  # 后台任务：失败只报告，不打断保存
            print(json.dumps({'ok': False, 'error': str(error)[:400]}))
            return 0
    print(json.dumps({'ok': True, 'revision': revision, 'png_sha256': result['png_sha256']}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
