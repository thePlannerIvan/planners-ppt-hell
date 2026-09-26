"""公共模组「缺了就自动装」的唯一实现（Python 侧）。**每个用到它的 Skill 各带一份副本**
—— 与 JS 侧 `planners-modules-install.mjs` 是**同一套契约的两份镜像**，改一份必须改另一份。

============================ 契约（py 与 mjs 两份实现必须一致） ============================
① 安装根优先级（同一个环境变量语义，两份实现一字不差）：
     $PLANNERS_MODULES_INSTALL_DIR                                  ← 显式指定，最高优先
     $PLANNERS_MODULES_HOME（**仅当**它已含该模组，或那目录还不存在时）
     <home>/.planners-modules                                       ← 默认；库外、用户级
   解析顺序不变：env → 兄弟目录 → monorepo 分类 → 用户级兜底 → 才装。
② 禁止落点（两份实现同一套断言）：
     a. 目标 realpath（及其未解析形态）**不得位于 02-skills-library 工作树内**；
     b. 不得落进 /usr、/etc、/System、/Library、/bin、/sbin、/var、/opt；
     c. 不得写 ~/.codex/skills、~/.claude/skills、~/.gemini/config/skills（publish 的领地）。
   违反即 raise，**绝不**降级成「装到别处算了」。
③ staging → rename 原子就位：先在安装根下建 .pm-staging-<name>-<pid>（同一文件系统，
   rename 才原子），clone 进去，验过再改名。**任何失败都删 staging**（try/finally）。
④ 装完必须验：目录非空 + SKILL.md + 该模组声明的契约/校验器锚点文件都在；
   空目录 / 缺锚点 = 失败，且不留半成品。
⑤ 幂等：目标已存在且通过验证 → 直接复用并报「已装好」，不 clone、不覆盖。
⑥ 不静默：每条动作都往 stderr 打一行 [planners-modules] 日志（来源 / 目标 / candidate /
   command / commit）。失败时抛出**带可复制手动命令**的错误。
⑦ 可关掉：$PLANNERS_NO_AUTO_INSTALL=1 → 只报不装（仍给可复制手动命令）。
⑧ 永不往模组目录里写文件（不写 INSTALLED.json、不改模组一个字）——provenance 只出现在日志里。
===========================================================================================
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

LOG_PREFIX = '[planners-modules]'
REPO_OWNER = 'thePlannerIvan'
LIBRARY_DIR_NAME = '02-skills-library'

#: 每个公共模组的「装完怎么算装好了」锚点。contracts/ + scripts/ 里的文件是该模组
#: **声明过**的契约与校验器，缺一个就是这个模组装歪了。
MODULE_SPECS = {
    'planners-review-core': (
        'SKILL.md',
        'contracts/review-surface.schema.json',
        'scripts/validate-surface.mjs',
        'scripts/review-host.mjs',
    ),
    'planners-source-index': (
        'SKILL.md',
        'contracts/source-index.schema.json',
        'scripts/validate-source-index.mjs',
    ),
    'planners-fact-check': (
        'SKILL.md',
        'contracts/fact-audit.schema.json',
        'scripts/validate-fact-audit.mjs',
    ),
    'planners-report-kit': (
        'SKILL.md',
        'contracts/attribution.json',
        'scripts/render-report.mjs',
        'scripts/validate-report.mjs',
    ),
}

FORBIDDEN_SYSTEM_DIRS = ('/usr', '/etc', '/System', '/Library', '/bin', '/sbin', '/var', '/opt')


def repo_url(name):
    return 'https://github.com/' + REPO_OWNER + '/' + name + '.git'


def module_spec(name):
    try:
        return MODULE_SPECS[name]
    except KeyError:
        raise ValueError(
            '%s 不认识的公共模组：%s（已知：%s）。如果你新加了模组，请先在 '
            'planners_modules_install.py 的 MODULE_SPECS 里登记它的锚点文件。'
            % (LOG_PREFIX, name, '、'.join(MODULE_SPECS))
        ) from None


def _log(message):
    sys.stderr.write(LOG_PREFIX + ' ' + message + '\n')


def _normalize(path):
    text = str(path)
    while len(text) > 1 and text[-1] in ('/', '\\'):
        text = text[:-1]
    return text


def _is_inside(child, parent):
    """child 是否就在 parent 之下（或等于 parent）。**不对 parent 做 realpath**
    —— parent 可能还不存在，realpath 会把它字符串原样留下，行为与 JS 侧不一致。"""
    c = _normalize(os.path.abspath(str(child)))
    p = _normalize(os.path.abspath(str(parent)))
    return c == p or c.startswith(p + os.sep)


def assert_install_target_allowed(target, home=None, library_root=None):
    """目标目录的禁地断言（契约 ②）。realpath 与未解析形态都比一遍。"""
    raw = os.path.abspath(str(target))
    real = os.path.realpath(raw)
    variants = [raw] if real == raw else [raw, real]

    if library_root:
        for variant in variants:
            if _is_inside(variant, library_root):
                raise ValueError(
                    LOG_PREFIX + ' 拒绝安装：目标 ' + variant + ' 位于 ' + LIBRARY_DIR_NAME
                    + ' 工作树内（' + str(library_root) + '）。\n  那会再造一个嵌套仓库。'
                    '请把安装根指到库外，例如 PLANNERS_MODULES_INSTALL_DIR=$HOME/.planners-modules。'
                )

    home_dir = Path(home) if home else Path.home()
    runtime_dirs = (
        home_dir / '.codex' / 'skills',
        home_dir / '.claude' / 'skills',
        home_dir / '.gemini' / 'config' / 'skills',
    )
    for variant in variants:
        for runtime_dir in runtime_dirs:
            if _is_inside(variant, runtime_dir):
                raise ValueError(
                    LOG_PREFIX + ' 拒绝安装：目标 ' + variant + ' 位于 runtime 技能目录 '
                    + str(runtime_dir) + '。\n  那里是 publish_skills.py 的领地，'
                    '自动装进去会变成第二份漂移副本。请改用库外安装根。'
                )
        for system_dir in FORBIDDEN_SYSTEM_DIRS:
            if _is_inside(variant, system_dir):
                raise ValueError(
                    LOG_PREFIX + ' 拒绝安装：目标 ' + variant + ' 位于系统目录 ' + system_dir + ' 之下。'
                )
    return raw


def install_root_for(name, env=None, home=None):
    """安装根怎么定（契约 ①）。返回 (root, source, configured)。"""
    env = os.environ if env is None else env
    home_dir = Path(home) if home else Path.home()

    explicit = (env.get('PLANNERS_MODULES_INSTALL_DIR') or '').strip()
    if explicit:
        return Path(explicit), 'PLANNERS_MODULES_INSTALL_DIR', True

    home_env = (env.get('PLANNERS_MODULES_HOME') or '').strip()
    if home_env:
        # 只有当它「已经含这个模组」或「还不存在」时才拿它当安装根；否则落到默认根，
        # 避免往别人的目录里塞东西。
        if (Path(home_env) / name).exists() or not Path(home_env).exists():
            return Path(home_env), 'PLANNERS_MODULES_HOME', True

    return home_dir / '.planners-modules', '默认 ~/.planners-modules', False


def manual_commands(name, env=None, home=None):
    root, _source, _configured = install_root_for(name, env=env, home=home)
    return {
        'npx': 'npx skills add ' + repo_url(name)[:-4] + ' --skill ' + name,
        'git': 'git clone --depth 1 ' + repo_url(name) + ' "' + str(root / name) + '"',
        'root': str(root),
    }


def module_not_found(name, candidates, env=None, home=None):
    commands = manual_commands(name, env=env, home=home)
    return ValueError(
        '找不到公共模组 ' + name + '（自动安装已关闭或不可用）。找过：\n  '
        + '\n  '.join(str(path) for path in candidates) + '\n装法（任选一条，可复制）：\n  '
        + commands['npx'] + '\n  ' + commands['git']
        + '\n或设 PLANNERS_MODULES_HOME 指向已有模组的目录。'
    )


def verify_install(directory, name):
    """装完怎么算装好了（契约 ④）。空目录 / 缺锚点一律失败。"""
    anchors = module_spec(name)
    path = Path(directory)
    if not path.exists():
        return {'ok': False, 'missing': list(anchors), 'reason': '目录不存在'}
    entries = [entry.name for entry in path.iterdir()]
    visible = [entry for entry in entries if entry != '.git']
    if not visible:
        return {'ok': False, 'missing': list(anchors), 'reason': '目录是空的（只有 .git）'}
    missing = [anchor for anchor in anchors if not (path / anchor).exists()]
    if missing:
        return {
            'ok': False,
            'missing': missing,
            'reason': '缺声明的契约/校验器：' + '、'.join(missing),
        }
    return {'ok': True, 'missing': []}


def find_library_root(start):
    """从 start 往上找 02-skills-library 工作树根，找不到返回 None。
    适配器拿它喂 assert_install_target_allowed 的 library_root（硬约束：禁止装进库里）。"""
    current = Path(start).resolve()
    for _ in range(12):
        if current.name == LIBRARY_DIR_NAME:
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def describe_install(directory, runner=None):
    """provenance：装了哪个 commit（以及有没有 tag 可钉）。"""
    run = runner or default_runner
    commit = run('git', ['-C', str(directory), 'rev-parse', 'HEAD'])
    if commit.returncode != 0:
        return {'commit': None, 'tags': []}
    tags = run('git', ['-C', str(directory), 'tag', '--points-at', 'HEAD'])
    return {
        'commit': (commit.stdout or '').strip() or None,
        'tags': [tag for tag in (tags.stdout or '').split('\n') if tag.strip()] if tags.returncode == 0 else [],
    }


def default_runner(command, args, cwd=None, env=None):
    return subprocess.run(
        [command] + list(args),
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
    )


def _has_binary(command, runner):
    try:
        return runner(command, ['--version']).returncode == 0
    except OSError:
        return False


def ensure_module(name, env=None, home=None, runner=None, library_root=None,
                  candidates=None, verify_path=None, log=None):
    """主入口：缺模组时把它装到安装根，装完验，验完回验。"""
    module_spec(name)
    env = dict(os.environ if env is None else env)
    home_dir = Path(home) if home else Path.home()
    run = runner or default_runner
    log_fn = log or _log
    candidates = list(candidates or [])

    root, source, _configured = install_root_for(name, env=env, home=home_dir)
    target = root / name
    assert_install_target_allowed(target, home=home_dir, library_root=library_root)

    npx_available = _has_binary('npx', run)
    git_available = _has_binary('git', run)
    method = ('npx skills add（先试官方工具）→ 失败则 git clone --depth 1' if npx_available
              else 'npx 不可用 → git clone --depth 1')

    # ⑤ 幂等：已经在位且验过，就复用。
    if target.exists():
        check = verify_install(target, name)
        if check['ok']:
            info = describe_install(target, run)
            log_fn('已装好，不需要重装：' + name + ' → ' + str(target)
                   + ('（commit ' + info['commit'] + '）' if info['commit'] else ''))
            return dict(path=str(target), action='reused', root=str(root), rootSource=source,
                        method=method, npxAvailable=npx_available, verifyPath=verify_path, **info)
        raise ValueError(
            LOG_PREFIX + ' 目录 ' + str(target) + ' 已存在，但**没通过验证**（' + check['reason']
            + '）——不是自动装出来的完整模组，我不覆盖它。\n  请人工确认后删除，'
            '或改 PLANNERS_MODULES_INSTALL_DIR / PLANNERS_MODULES_HOME 换一个安装根。'
        )

    # ⑦ 可关掉：只报不装。
    if env.get('PLANNERS_NO_AUTO_INSTALL') == '1':
        log_fn('PLANNERS_NO_AUTO_INSTALL=1 → 只报不装：' + name + ' 不在 ' + str(target))
        raise module_not_found(name, candidates, env=env, home=home_dir)

    root.mkdir(parents=True, exist_ok=True)
    staging = root / ('.pm-staging-' + name + '-' + str(os.getpid()))
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    log_fn('缺少公共模组 ' + name + '；已找过：'
           + (' , '.join(str(path) for path in candidates) if candidates else '（候选列表未传）'))
    log_fn('正在安装：来源 ' + repo_url(name) + '（默认分支；该仓库当前**没有 tag 可钉**）→ 目标 ' + str(target))
    log_fn('安装命令：' + method)

    try:
        if not git_available:
            raise RuntimeError('本机没有 git，无法退化为 git clone')

        if npx_available:
            npx_env = dict(env)
            npx_env.setdefault('npm_config_cache', str(root / '.pm-npm-cache'))
            npx = run('npx', ['-y', 'skills@latest', 'add', repo_url(name)[:-4],
                              '--skill', name, '-y', '--copy'], cwd=root, env=npx_env)
            if npx.returncode != 0:
                combined = [line for line in ((npx.stderr or '') + (npx.stdout or '')).split('\n') if line.strip()]
                why = combined[-1] if combined else '退出码 ' + str(npx.returncode)
                log_fn('npx skills add 不可用 → 退化为 git clone --depth 1（原因：' + why + '）')
            else:
                log_fn('npx skills add 成功；但它不带 .git、也不能指定安装根，故仍以 git clone 的副本为准（可追溯 commit）')

        clone = run('git', ['clone', '--depth', '1', repo_url(name), str(staging)], cwd=root, env=env)
        if clone.returncode != 0:
            lines = [line for line in ((clone.stderr or '') + (clone.stdout or '')).split('\n') if line.strip()]
            reason = ' / '.join(lines[-3:]) if lines else '退出码 ' + str(clone.returncode)
            raise RuntimeError('git clone 失败：' + reason)

        check = verify_install(staging, name)
        if not check['ok']:
            raise RuntimeError('装下来的内容没通过验证：' + check['reason'])

        info = describe_install(staging, run)
        assert_install_target_allowed(target, home=home_dir, library_root=library_root)
        try:
            # ③ rename 原子就位；同目录同文件系统，不会出现半成品
            os.rename(str(staging), str(target))
        except OSError:
            if target.exists():
                # 并发：别的进程先装好了。用先到的，丢弃自己的 staging。
                shutil.rmtree(staging, ignore_errors=True)
                winner = describe_install(target, run)
                log_fn('并发：另一个进程先装好了 ' + name + ' → ' + str(target)
                       + '（commit ' + str(winner['commit']) + '），丢弃本次 staging')
                return dict(path=str(target), action='reused', root=str(root), rootSource=source,
                            method=method, npxAvailable=npx_available, verifyPath=verify_path, **winner)
            raise

        final = verify_install(target, name)
        if not final['ok']:
            raise RuntimeError('就位后复验失败：' + final['reason'])

        log_fn('已安装 ' + name + ' ✓ commit ' + str(info['commit'] or '未知') + '｜tag：'
               + ('、'.join(info['tags']) if info['tags'] else '（无，仓库没有 tag）'))
        log_fn('落点：' + str(target) + '（安装根来源：' + source + '）｜npx 可用性：'
               + ('可用' if npx_available else '不可用（已退化为 git clone）'))

        # ⑥ 回验：让**本适配器自己**再解析一次，确认下次一定找得到。
        if verify_path:
            resolved = verify_path(name)
            if not resolved:
                raise RuntimeError(
                    LOG_PREFIX + ' 装完了，但本 Skill 的适配器仍解析不到 ' + name + '。\n  已装到 '
                    + str(target) + '；请把它放到适配器的候选路径之一，或设 PLANNERS_MODULES_HOME='
                    + str(root) + '。'
                )
            log_fn('回验通过：本适配器现在解析到 ' + str(resolved))

        return dict(path=str(target), action='installed', root=str(root), rootSource=source,
                    method=method, npxAvailable=npx_available, verifyPath=verify_path, **info)
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        commands = manual_commands(name, env=env, home=home_dir)
        raise ValueError(
            LOG_PREFIX + ' 自动安装 ' + name + ' **失败**（真实原因：' + str(error)
            + '）。已清掉暂存目录 ' + staging.name + '，没有留下半成品。\n'
            '  手动装（任选一条，可复制）：\n    ' + commands['npx'] + '\n    ' + commands['git']
        ) from error
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
