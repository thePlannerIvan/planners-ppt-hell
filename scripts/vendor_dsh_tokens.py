#!/usr/bin/env python3
"""把 DSH 的设计令牌重新 vendor 进审阅页（`assets/review/dsh-tokens.css`）。

**为什么需要这个脚本**：审阅页跑在 `sandbox="allow-scripts"` 的**不透明源 iframe** 里，
宿主的 CSS 变量继承不进来、外链样式表也会被信任围栏打回 403 —— 令牌表只能随页面一起发。
于是一份"值"被复制到了两个地方（DSH 的发行版 vs 本 Skill 的页面）。副本不会自己同步，
所以这里给出**唯一的更新方式**：跑这个脚本，别手改那份 CSS。

**版本必须钉在"你机器上跑的那一版"上。** 这里踩过一个坑，写下来：一开始用
`npm view @deepseek-ai/dsh-client-ui-theme version` 取包，而它跟的是 `latest` 标签 ——
那个包的 `latest` **卡在 `0.0.1-rc.1`**（31 个版本里最老那个，8-10），照它抄就会抄到比运行
版本老七周的一套值，**而且没有任何报错**。后来又发现 0.2.0 起 npm 上根本没有这份表了
（`dsh-client-ui-theme` 只剩品牌字体，`dsh-web-frontend` 的构建产物里也只带 2 个 token）。

所以现在**只认一个来源：本机已装的发行版**，从它的 `app.asar` 里读：

  · `lib/welcome/welcome.css` —— 结构完整的令牌表（明暗分块、还带 darwin 变体），
    77 个 static / 101 个 alias / 180 个 font；这是唯一带着这份表的文件。
  · 发行版里其余位置 —— 只补 `--dsw-radius-*`（那几个更上游，连 welcome.css 也没有）。
  · `Contents/Info.plist` 的 `CFBundleShortVersionString` —— 版本号的唯一依据，写进文件头。
  · `node_modules/@deepseek-ai/dsh-client-ui-theme/LICENSE` —— MIT（Copyright (c) 2026 DeepSeek），
    随文件一起保留。

用法：

    python3 scripts/vendor_dsh_tokens.py                      # 默认找 /Applications 下那个 App
    python3 scripts/vendor_dsh_tokens.py --app "/path/to/DeepSeek Harness.app"

跑完打印并写进文件头：App 版本、源文件与其 sha256、抽到多少条、补了多少条、
以及与"整个发行版里出现过的 token"的比对结果（多数"不同"只是 rgba 与 #RRGGBBAA 的写法差异）。
缺任何一样就报错退出，**不写半份文件**。
"""
import argparse
import hashlib
import json
import plistlib
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_CSS = HERE.parent/'assets/review/dsh-tokens.css'
OUT_LICENSE = HERE.parent/'assets/review/dsh-tokens.LICENSE.txt'
DEFAULT_APP = Path('/Applications/DeepSeek Harness.app')
SHEET = '/lib/welcome/welcome.css'
# 运动：welcome.css 没带，但发行版里有。页面靠它们做过渡 —— 缺了 transition 整条会失效。
MOTION = ['--ds-ease-in-out', '--ds-transition-duration',
          '--ds-transition-duration-fast', '--ds-transition-duration-slow']
# 底座：被表内其它 token 引用、但 welcome.css 里没定义的那几个（字体栈）。
# 少了 `--dsw-font-family`，所有 `font: var(--dsw-font-xs-13)` 会在计算期失效 ——
# 页面没有报错，只是字族悄悄退回浏览器默认（Times）。
BASE = ['--dsw-font-family', '--ds-font-family-code']
LICENSE_IN_ASAR = '/dsh/node_modules/@deepseek-ai/dsh-client-ui-theme/LICENSE'
TOKEN = r'--dsw-[a-zA-Z0-9-]+'

HEADER = '''/* ============================================================================
 * DSH 设计令牌（vendored，勿手改）
 *
 * 抄的是**你机器上正在跑的那一版**：DeepSeek Harness 桌面端 {app_version}。
 * 来源：该发行版里的 {sheet}（sha256 {sheet_sha}）——
 *       它是整个发行版里唯一带这份表的文件，明暗分块、含 darwin 变体；
 *       下面两节按选择器把 `--dsw-*` 声明抽出来，**值原样保留**。
 * 补丁：`--dsw-radius-*`（{n_radius} 条）、四个运动变量（{n_motion} 条）与字体栈底座
 *      在同一发行版里另取，
 *       welcome.css 里没有 —— 缺了运动变量，页面里整条 transition 会失效（变成瞬变）。
 * 许可：DeepSeek，MIT（Copyright (c) 2026 DeepSeek）—— 全文见 dsh-tokens.LICENSE.txt。
 *
 * 为什么是"带进来"而不是"引进来"：审阅页跑在 sandbox="allow-scripts" 的**不透明源
 * iframe** 里 —— 宿主的 CSS 变量不会继承进来，外链样式表也会被信任围栏打回 403。
 * 这份表只能随页面一起发。
 *
 * **别手改这个文件。** 它是副本；更新方式只有一条：
 *     python3 scripts/vendor_dsh_tokens.py
 * 手改就会漂移，而漂移两边都不会报错。**升级 DSH 之后要重跑一次** ——
 * 这一版是从 {app_version} 抄的，装了新版它就该变。
 *
 * 与整个发行版的比对：{cross_check}
 * ========================================================================== */

/* ===== 明色（默认）—— 抽自 {sheet} 里非暗色选择器下的声明 ===== */
body {{
{light}
}}

/* ===== 暗色 —— 抽自同一文件里带 data-ds-dark-theme 的选择器 ===== */
body[data-ds-dark-theme] {{
{dark}
}}

/* ===== 补丁块：welcome.css 里也没有的那几组（更上游的 deepsuite 主题 / 运动曲线） =====
 * 值由本脚本从同一发行版的其它位置取出，一个都没有猜。
 */
body {{
{base}
{radius}
{motion}
}}
'''


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_asar(asar):
    """把 app.asar 的文件表读出来，返回 {路径: 取内容的函数}。"""
    raw = Path(asar).read_bytes()
    json_size = struct.unpack('<I', raw[12:16])[0]
    tree = json.loads(raw[16:16+json_size].decode('utf-8'))
    base = 16 + json_size
    files = {}

    def walk(node, path=''):
        for name, meta in (node.get('files') or {}).items():
            here = f'{path}/{name}'
            if 'files' in meta:
                walk(meta, here)
            else:
                files[here] = meta

    walk(tree)

    def blob(path, cap=4_000_000):
        meta = files.get(path)
        if meta is None:
            return None
        offset, size = meta.get('offset'), meta.get('size')
        if offset is None or not size:
            return None                      # unpacked / 链接项：不在 asar 体内
        return raw[int(offset)+base:int(offset)+base+min(int(size), cap)].decode('utf-8', 'replace')

    return blob, files, raw


def app_version(app_dir):
    plist = Path(app_dir)/'Contents/Info.plist'
    if not plist.is_file():
        raise SystemExit(f'找不到 {plist} —— --app 要指向 DeepSeek Harness.app 本体')
    with plist.open('rb') as handle:
        version = plistlib.load(handle).get('CFBundleShortVersionString')
    if not version:
        raise SystemExit('Info.plist 里没有 CFBundleShortVersionString；这个包结构不对')
    return version


def split_tokens(css_text):
    """抽出 `--dsw-*: value`，按选择器分到明/暗两个保序去重的表里。"""
    light, dark = {}, {}
    for selector, body in re.findall(r'([^{}]*)\{([^{}]*)\}', css_text):
        target = dark if 'data-ds-dark-theme' in selector else light
        # **值不设长度上限**：截断会切出没闭合的括号，而一个未闭合的 ( 会让 CSS 解析器
        # 一路吞到文件尾 —— 整段样式失效，页面变成裸 HTML（这次就是这么坏的）。
        # 值里可以有引号（'Segoe UI'、\"SF Mono\"）—— 排除引号会把字体栈截成半截。
        for name, value in re.findall(rf'({TOKEN})\s*:\s*([^;}}]*)', body):
            value = value.replace('\\"', '"').strip()
            if value:
                target.setdefault(name, value)
    return light, dark


def all_tokens(blob):
    """整个发行版里出现过的 `--dsw-*`（用来做一次独立比对）。"""
    seen = 0
    found = {}
    for path in ('/lib/welcome/welcome.css',):
        text = blob(path) or ''
        for name, value in re.findall(rf'({TOKEN})\s*:\s*([^;}}"\']*)', text):
            found.setdefault(name, value.strip())
    return found


def as_block(table, indent='  '):
    return '\n'.join(f'{indent}{name}: {value};' for name, value in table.items())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--app', default=str(DEFAULT_APP), help='DeepSeek Harness.app 路径')
    args = ap.parse_args()

    app_dir = Path(args.app).expanduser()
    version = app_version(app_dir)
    asar = app_dir/'Contents/Resources/app.asar'
    if not asar.is_file():
        raise SystemExit(f'找不到 {asar}')
    blob, files, _raw = read_asar(asar)

    sheet_text = blob(SHEET)
    if not sheet_text or len(sheet_text) < 5000:
        raise SystemExit(f'发行版里读不到 {SHEET}（或它太小）—— 结构变了，先看新版把它放哪了')
    light, dark = split_tokens(sheet_text)
    if len(light) < 150 or len(dark) < 50:
        raise SystemExit(f'从 {SHEET} 只抽到 明 {len(light)} / 暗 {len(dark)} 条，预期 300+/150+；结构变了')

    # 圆角：welcome.css 没有，从发行版其它位置取
    radius = {}
    for name, value in re.findall(r'(--dsw-radius-[a-zA-Z0-9-]+)\s*:\s*([^;}"\'\\]*)',
                                  _raw.decode('utf-8', 'replace')):
        radius.setdefault(name, value.strip())
    if not radius:
        raise SystemExit('发行版里一个 --dsw-radius-* 都没抽到；结构变了')

    decoded = _raw.decode('utf-8', 'replace')
    motion = {}
    for name in MOTION:
        found = re.search(re.escape(name)+r'\s*:\s*([^;}"\']*)', decoded)
        if found:
            motion[name] = found.group(1).strip()
    if len(motion) != len(MOTION):
        raise SystemExit(f'发行版里缺运动变量：{[n for n in MOTION if n not in motion]}；'
                         '缺了页面里 transition 会整条失效，拒绝写半份')
    base = {}
    for name in BASE:
        found = re.search(re.escape(name)+r'\s*:\s*([^;}]*);', decoded)
        if found:
            base[name] = found.group(1).strip().replace('\\"', '"')
    if len(base) != len(BASE):
        raise SystemExit(f'发行版里缺底座变量：{[n for n in BASE if n not in base]}；'
                         '字体栈缺了字族会静默退回浏览器默认，拒绝写半份')

    license_text = blob(LICENSE_IN_ASAR)
    if not license_text:
        raise SystemExit(f'发行版里读不到 {LICENSE_IN_ASAR} —— 许可声明必须随副本一起保留，拒绝继续')

    # 独立比对：拿"整个发行版里出现过的 token"跟这份表对一遍。**写法差异不是值差异**
    # （rgba vs #RRGGBBAA），所以只报计数与样例，不假装是零、也不因为它喊失败。
    app_tokens = all_tokens(blob)
    same = sum(1 for k, v in light.items() if app_tokens.get(k) == v)
    differing = [k for k, v in light.items() if k in app_tokens and app_tokens[k] != v]
    cross = (f'明色 {len(light)} 条里 {same} 条与发行版逐字一致，{len(differing)} 条写法不同'
             f'（多为 rgba 与 #RRGGBBAA）')

    # 自检：写盘前把"能不能被 CSS 解析器吃下去"验一遍。这次踩的坑就是抽值截断留下未闭合的
    # 括号 —— 页面没有报错，只是整段样式被丢掉，看起来像"没上样式"。
    blocks = {'明色': light, '暗色': dark, '圆角': radius, '运动': motion}
    for label, table in blocks.items():
        for name, value in table.items():
            if value.count('(') != value.count(')'):
                raise SystemExit(f'{label} 的 {name} 括号不配对：{value!r}（抽值时被截断了？）')
            if not name.startswith('--') or not value.strip():
                raise SystemExit(f'{label} 的声明不合法：{name!r}: {value!r}')

    # 表内自洽：整个表引用到的变量，要么自己定义了，要么本来就带 fallback（`--dsh-content-font-*`
    # 在表里都是 `var(--x, 默认值)` 形式）。这一条能拦住"表看着齐全、引用却悬空"那类静默失效。
    sheet_defs = set(light) | set(dark) | set(radius) | set(motion) | set(base)
    ALLOWED_FALLBACK = {'--dsh-content-font-size', '--dsh-content-font-delta',
                        '--dsh-content-font-size-secondary', '--dsh-content-font-delta-secondary'}
    dangling = sorted({n for n in (light.values()) for n in re.findall(r'var\(\s*(--[\w-]+)', ' '.join(light.values()))}
                      - sheet_defs - ALLOWED_FALLBACK)
    if dangling:
        raise SystemExit(f'表内引用了没定义的变量：{dangling}；这会静默失效，拒绝写半份')

    body = HEADER.format(
        app_version=version, sheet=SHEET, sheet_sha=sha(sheet_text)[:32], n_radius=len(radius),
        n_motion=len(motion), cross_check=cross, light=as_block(light), dark=as_block(dark),
        radius=as_block(radius), motion=as_block(motion), base=as_block(base),
    )
    OUT_CSS.write_text(body, encoding='utf-8')
    OUT_LICENSE.write_text(license_text.rstrip()+'\n', encoding='utf-8')

    print(f'桌面端 {version} ← {SHEET}')
    print(f'  源文件 sha256 {sha(sheet_text)[:16]}…')
    print(f'  抽到：明色 {len(light)} 条、暗色覆写 {len(dark)} 条；'
          f'补 --dsw-radius-* {len(radius)} 条、运动 {len(motion)} 条、底座 {len(base)} 条')
    print(f'  比对：{cross}')
    if differing[:6]:
        print('  写法不同样例：', '、'.join(sorted(differing)[:6]))
    print(f'  许可：{LICENSE_IN_ASAR}（已另存 dsh-tokens.LICENSE.txt）')
    print(f'写出 {OUT_CSS.relative_to(HERE.parent)}（{OUT_CSS.stat().st_size} 字节）')


if __name__ == '__main__':
    sys.exit(main())
