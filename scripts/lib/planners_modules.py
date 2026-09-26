"""公共模组的解析适配器（本 Skill 一份，约 50 行）。

「公共模组单独发布成条目」意味着：发布后它们与本 Skill **平铺在同一个 skills 根下**，
所以按名字找兄弟目录即可，不需要任何 runtime 专属路径。开发时它们还在 monorepo 里。

找的顺序（与 bypage 的 `scripts/lib/planners-modules.mjs` 同一套约定）：
  ① $PLANNERS_MODULES_HOME/<name>
  ② 本 Skill 目录的兄弟：<skills-root>/<name>          ← 发布后的主路径
  ③ monorepo：<repo>/<任意 00-… 分类>/<name>
  ④ 都没有 → 报错并给安装提示（**不许静默降级成"跳过校验"**）

`node_binary()` 已搬进 `planners-review-core/scripts/lib/review_host.py`（只有那一份，
本适配器只管**找模组**）。

自检：python3 scripts/lib/planners_modules.py --check
"""
import glob
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent          # <skill>/scripts/lib
SKILL_ROOT = HERE.parent.parent                 # <skill>
SKILLS_ROOT = SKILL_ROOT.parent                 # 发布后的 skills 根（monorepo 里是分类目录）
REPO_ROOT = SKILLS_ROOT.parent


def repo_categories():
    """monorepo 里所有分类目录（00-system、01-data-analysis、…）。公共模组可以住在任何一类。"""
    try:
        return sorted(p for p in REPO_ROOT.iterdir() if p.is_dir() and p.name[:2].isdigit() and p.name[2:3] == '-')
    except OSError:
        return []


def module_candidates(name):
    home = os.environ.get('PLANNERS_MODULES_HOME')
    paths = [
        Path(home)/name if home else None,
        SKILLS_ROOT/name,                                   # 发布后：兄弟目录
        *[category/name for category in repo_categories()],  # monorepo：任意分类下
    ]
    return [path for path in paths if path is not None]


def resolve_module(name):
    for candidate in module_candidates(name):
        if candidate.exists():
            return candidate
    raise ValueError(
        '找不到公共模组 ' + name + '。找过：\n  '
        + '\n  '.join(str(path) for path in module_candidates(name))
        + '\n装法：把 ' + name + ' 放进同一个 skills 根目录，或设 PLANNERS_MODULES_HOME 指向它所在目录。')


def module_script(name, rel_path):
    path = resolve_module(name)/rel_path
    if not path.exists():
        raise ValueError('公共模组 ' + name + ' 里没有这个脚本：' + rel_path)
    return path




if __name__ == '__main__':
    import sys
    if '--check' in sys.argv:
        for module in ('planners-review-core', 'planners-source-index', 'planners-fact-check'):
            try:
                print('✓ ' + module + ' → ' + str(resolve_module(module)))
            except ValueError as error:
                print('✗ ' + module + '：' + str(error).splitlines()[0])
        print('\n候选路径（planners-review-core）：')
        for path in module_candidates('planners-review-core'):
            print('  ' + str(path))
        print('\n（node 不在本适配器里找：见 planners-review-core/scripts/lib/review_host.py）')
