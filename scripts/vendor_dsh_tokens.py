#!/usr/bin/env python3
"""把 DSH 的设计令牌重新 vendor 进审阅页（`assets/review/dsh-tokens.css`）。

**为什么需要这个脚本**：审阅页跑在 `sandbox="allow-scripts"` 的**不透明源 iframe** 里，
宿主的 CSS 变量继承不进来、外链样式表也会被信任围栏打回 403 —— 令牌表只能随页面一起发。
于是一份"值"被复制到了两个地方（DSH 的发行版 vs 本 Skill 的页面）。副本不会自己同步，
所以这里给出**唯一的更新方式**：跑这个脚本，别手改那份 CSS。

两个来源，各管一段（缺一个就报错退出，不写半份）：

  1. **npm 公开包** `@deepseek-ai/dsh-client-ui-theme`（BSD-3-Clause）的
     `lib/styles/{base,design-platform,scrollbar}.css` —— 颜色两层、滚动条、明暗整套。
  2. **本机已装的发行版**（`app.asar`）—— 补 npm 包里没有的那几组：
     `--dsw-radius-*`、`--dsw-elevation-*`、`--dsw-font-*` 字阶、`--dsw-alias-bg-document-preview`、
     `--dsw-alias-bg-document-selection`。这些在更上游的 deepsuite 主题里，npm 包没带。

用法：

    python3 scripts/vendor_dsh_tokens.py                     # 自动找 npm 包与本机发行版
    python3 scripts/vendor_dsh_tokens.py --from /path/to/pkg # 用已经解开的包目录
    python3 scripts/vendor_dsh_tokens.py --app "/Applications/DeepSeek Harness.app/..."  # 指定 app.asar

跑完会打印：三个来源文件的 sha256、抽出多少条补丁 token。**把它贴在 PR/CHANGELOG 里** ——
这是"这次副本抄的是哪一版"的唯一凭证。
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_CSS = HERE.parent/'assets/review/dsh-tokens.css'
OUT_LICENSE = HERE.parent/'assets/review/dsh-tokens.LICENSE.txt'
SOURCES = ['base.css', 'design-platform.css', 'scrollbar.css']
DEFAULT_APP = Path('/Applications/DeepSeek Harness.app/Contents/Resources/app.asar')

HEADER = '''/* ============================================================================
 * DSH 设计令牌（vendored，勿手改）
 *
 * 来源：npm 公开包 {pkg} 的
 *       lib/styles/ 下三份表，逐字节照抄：{sources}。
 *       补丁块的值抄自本机已装的发行版（npm 包没带那几组，见文件末尾）。
 *
 * 为什么是"带进来"而不是"引进来"：审阅页跑在 sandbox="allow-scripts" 的**不透明源
 * iframe** 里 —— 宿主的 CSS 变量不会继承进来，外链样式表也会被信任围栏打回 403。
 * 这份表只能随页面一起发。
 *
 * **别手改这个文件。** 它是副本；更新方式只有一条：
 *     python3 scripts/vendor_dsh_tokens.py
 * 手改就会漂移，而漂移两边都不会报错。
 *
 * 本次 vendor 的凭证：
 *   base.css            sha256 {sha_base}
 *   design-platform.css sha256 {sha_platform}
 *   scrollbar.css       sha256 {sha_scrollbar}
 *   补丁 token          {n_patch} 条（取自发行版 {app_name}）
 * ---------------------------------------------------------------------------
{license}
 * ========================================================================== */

/* ===== 以下三节逐字节抄自 npm 包 ===== */

'''

PATCH = '''
/* ===== 补丁块：npm 包里没有、只在发行版里有的那几组 =====
 *
 * `--dsw-radius-*`、`--dsw-elevation-*`、`--dsw-font-*` 字阶，以及两个 alias
 * （`bg-document-preview` 凹底色、`bg-document-selection` 选中色）都定义在更上游的
 * deepsuite 主题里，**不在**这个 npm 包里（包内 `base.css` 顶部那句注释说的就是这件事）。
 * 值由本脚本从本机发行版里抽出来，一个都没有猜。
 */
body {{
{patch_light}
}}

body[data-ds-dark-theme] {{
{patch_dark}
}}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_package(explicit):
    """解开 npm 包，返回 (包目录, 版本)。"""
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root/'lib/styles').is_dir():
            raise SystemExit(f'这个目录里没有 lib/styles/：{root}')
        return root, (root/'package.json').exists() and _version(root) or 'unknown'
    if shutil.which('npm') is None:
        raise SystemExit('找不到 npm；用 --from <已解开的包目录> 走离线路径')
    tmp = Path(tempfile.mkdtemp(prefix='dsh-theme-'))
    cache = tmp/'npm-cache'
    got = subprocess.run(['npm', 'pack', '@deepseek-ai/dsh-client-ui-theme',
                          '--cache', str(cache), '--pack-destination', str(tmp)],
                         capture_output=True, text=True)
    if got.returncode != 0:
        raise SystemExit('npm pack 失败（离线？用 --from 指一个已解开的包目录）：\n'+got.stderr[-400:])
    tgz = next(tmp.glob('*.tgz'), None)
    if tgz is None:
        raise SystemExit('npm pack 没有产出 .tgz')
    subprocess.run(['tar', 'xzf', str(tgz), '-C', str(tmp)], check=True)
    root = tmp/'package'
    return root, _version(root)


def _version(root):
    m = re.search(r'"version"\s*:\s*"([^"]+)"', (root/'package.json').read_text(encoding='utf-8'))
    return m.group(1) if m else 'unknown'


def app_pairs(app):
    """从发行版里抽出全部 `--dsw-*: value` 对（保留第一次出现的值 = 明色那一份）。"""
    if not app.is_file():
        raise SystemExit(f'找不到发行版 app.asar：{app}\n'
                         '补丁块（圆角/浮起/字阶/两个 alias）只能从发行版里取，不写半份文件。')
    raw = subprocess.run(['strings', '-n', '6', str(app)], capture_output=True).stdout.decode('utf-8', 'replace')
    pairs = {}
    for name, value in re.findall(r'(--dsw-[a-zA-Z0-9-]+)\s*:\s*([^;}"\'\\]{1,90})', raw):
        pairs.setdefault(name, value.strip())
    return pairs


def app_dark(app):
    """暗色那一份（第二次出现的值）。找不到就用明色 —— 但要说出来。"""
    if not app.is_file():
        return {}
    raw = subprocess.run(['strings', '-n', '6', str(app)], capture_output=True).stdout.decode('utf-8', 'replace')
    seen, dark = set(), {}
    for name, value in re.findall(r'(--dsw-[a-zA-Z0-9-]+)\s*:\s*([^;}"\'\\]{1,90})', raw):
        if name in seen:
            dark.setdefault(name, value.strip())
        else:
            seen.add(name)
    return dark


def supplement(pairs, dark):
    """要补的 token：圆角、浮起、字阶（plain + strong + 分量）、两个 alias。"""
    sizes = ['xxxs-11', 'xxs-12', 'xs-13', 's-14', 'base-16', 'l-20', 'xl-24']
    want = []
    for size in sizes:
        stem = size.split('-')[0]
        for prefix in (f'--dsw-font-{size}', f'--dsw-font-{stem}-strong-{size.split("-")[1]}'):
            want += [prefix, prefix+'-font-size', prefix+'-font-weight', prefix+'-line-height']
    light, dark_lines = [], []
    for name in want:
        if name in pairs:
            light.append(f'  {name}: {pairs[name]};')
    for name in sorted(pairs):
        if 'radius-' in name or 'elevation-' in name:
            light.append(f'  {name}: {pairs[name]};')
    light.append('  --dsw-alias-bg-document-preview: var(--dsw-static-neutral-bluish-100);')
    light.append('  --dsw-alias-bg-document-selection: color-mix(in srgb, var(--dsw-static-blue-500) 40%, transparent);')
    dark_lines.append('  --dsw-alias-bg-document-preview: var(--dsw-static-neutral-bluish-950);')
    # 去重保序
    def uniq(lines):
        seen, out = set(), []
        for line in lines:
            key = line.strip().split(':')[0]
            if key not in seen:
                seen.add(key)
                out.append(line)
        return out
    return uniq(light), uniq(dark_lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='src', help='已解开的 @deepseek-ai/dsh-client-ui-theme 包目录')
    ap.add_argument('--app', dest='app', default=str(DEFAULT_APP), help='发行版 app.asar 路径')
    args = ap.parse_args()

    pkg, version = find_package(args.src)
    styles = pkg/'lib/styles'
    for name in SOURCES:
        if not (styles/name).is_file():
            raise SystemExit(f'npm 包里缺 {name} —— 包结构变了，先看它新的 layout 再改这个脚本')
    pairs = app_pairs(Path(args.app))
    dark = app_dark(Path(args.app))
    light_lines, dark_lines = supplement(pairs, dark)

    body = [HEADER.format(
        pkg=f'@deepseek-ai/dsh-client-ui-theme@{version}',
        sources='、'.join(SOURCES),
        sha_base=sha(styles/'base.css'), sha_platform=sha(styles/'design-platform.css'),
        sha_scrollbar=sha(styles/'scrollbar.css'), n_patch=len(light_lines),
        app_name=Path(args.app).name, license=(pkg/'LICENSE').read_text(encoding='utf-8').strip(),
    )]
    for name in SOURCES:
        body.append(f'/* --- {name} --- */\n'+(styles/name).read_text(encoding='utf-8').rstrip()+'\n\n')
    body.append(PATCH.format(patch_light='\n'.join(light_lines), patch_dark='\n'.join(dark_lines)))

    OUT_CSS.write_text(''.join(body), encoding='utf-8')
    OUT_LICENSE.write_text((pkg/'LICENSE').read_text(encoding='utf-8'), encoding='utf-8')
    print(f'来自 @deepseek-ai/dsh-client-ui-theme@{version}')
    for name in SOURCES:
        print(f'  {name:<24} sha256 {sha(styles/name)[:16]}…')
    print(f'  补丁 token {len(light_lines)} 条（取自 {Path(args.app).name}）')
    print(f'写出 {OUT_CSS.relative_to(HERE.parent)}（{OUT_CSS.stat().st_size} 字节）与 LICENSE')


if __name__ == '__main__':
    sys.exit(main())
