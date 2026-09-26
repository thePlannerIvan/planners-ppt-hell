"""公共模组的解析适配器（本 Skill 一份，约 50 行）。

「公共模组单独发布成条目」意味着：发布后它们与本 Skill **平铺在同一个 skills 根下**，
所以按名字找兄弟目录即可，不需要任何 runtime 专属路径。开发时它们还在 monorepo 里。

找的顺序（与 bypage 的 `scripts/lib/planners-modules.mjs` 同一套约定）：
  ① $PLANNERS_MODULES_HOME/<name>
  ② 本 Skill 目录的兄弟：<skills-root>/<name>          ← 发布后的主路径
  ③ monorepo：<repo>/<任意 00-… 分类>/<name>
  ④ 用户级兜底：<安装根>/<name>（$PLANNERS_MODULES_INSTALL_DIR → $PLANNERS_MODULES_HOME
     → 默认 ~/.planners-modules；库外，绝不写进 02-skills-library）
  ⑤ 都没有 → **自动装**进安装根，装完复验再重解析；装不成才报错到 ⑥
     （PLANNERS_NO_AUTO_INSTALL=1 → 只报不装；契约见 planners_modules_install.py）
  ⑥ 装不成 → 报错并给安装提示（**不许静默降级成"跳过校验"**）

`node_binary()` 已搬进 `planners-review-core/scripts/lib/review_host.py`（只有那一份，
本适配器只管**找模组**）。

自检：python3 scripts/lib/planners_modules.py --check
"""
import glob
import importlib.util
import os
import re
import sys
from pathlib import Path


def _load_installer():
    """把同目录的 planners_modules_install.py 按**文件路径**载进来。

    这里刻意不走 `import planners_modules_install`：本适配器被 `lib.planners_modules`
    这种包路径导入时（video-craft 与 ppt-hell 的测试都这么导），`lib/` 目录本身不在
    sys.path 上，绝对导入会炸。按文件路径加载，两种导入方式都能活。
    """
    path = Path(__file__).resolve().parent / 'planners_modules_install.py'
    spec = importlib.util.spec_from_file_location('_planners_modules_install', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['_planners_modules_install'] = module
    spec.loader.exec_module(module)
    return module


_installer = _load_installer()
ensure_module = _installer.ensure_module
find_library_root = _installer.find_library_root
install_root_for = _installer.install_root_for
module_not_found = _installer.module_not_found


HERE = Path(__file__).resolve().parent          # <skill>/scripts/lib
SKILL_ROOT = HERE.parent.parent                 # <skill>
SKILLS_ROOT = SKILL_ROOT.parent                 # 发布后的 skills 根（monorepo 里是分类目录）
REPO_ROOT = SKILLS_ROOT.parent


def _install_root_for(name):
    """给候选列表用的安装根（默认 <home>/.planners-modules，即「库外用户级」）。"""
    root, _source, _configured = install_root_for(name)
    return Path(root)


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
        # ⑤ 兜底（最后一条，绝不遮蔽上面任何一条）：缺依赖时自动装到「库外用户级」安装根。
        _install_root_for(name)/name,
    ]
    return [path for path in paths if path is not None]


def _adapter_can_resolve(probe):
    """回验钩子：装完之后让**本适配器自己**再解析一次（治「装完还是找不到」）。"""
    return resolve_module(probe) if any(c.exists() for c in module_candidates(probe)) else None


def resolve_module(name):
    for candidate in module_candidates(name):
        if candidate.exists():
            return candidate
    return _install_module_then_resolve(name)


def _install_module_then_resolve(name):
    """本地一条都没命中 → 自动装（契约见 planners_modules_install.py）。

    装失败时错误信息里带着「缺哪个、找过哪些路径、手动怎么装（可复制）」。
    """
    candidates = module_candidates(name)
    try:
        ensure_module(
            name,
            candidates=candidates,
            library_root=find_library_root(HERE),
            verify_path=_adapter_can_resolve,
        )
    except Exception as error:  # noqa: BLE001 - 任何安装失败都要变成可读的「找不到模组」
        # 安装器的错误信息本身已经说清了「缺哪个、找过哪些路径、手动怎么装」，
        # 再套一层只会把它埋掉 —— 保留原类型与信息，只加一句上下文。
        raise type(error)(
            '公共模组 ' + name + ' 不在本地，自动安装也没成功。\n' + str(error)
        ) from error
    for candidate in module_candidates(name):
        if candidate.exists():
            return candidate
    raise module_not_found(name, candidates)


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
