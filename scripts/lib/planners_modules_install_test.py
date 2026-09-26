#!/usr/bin/env python3
"""共享安装器的不变量测试（Python 侧）。**与 JS 侧的 planners-modules-install.test.mjs
断言同一套规则**：
  ① 安装根优先级（install_dir → home 目录）
  ② 禁地断言（库工作树内 / runtime 技能目录 / 系统目录）
  ③ 用户级候选**永远排在最后**（绝不遮蔽已发布副本）
  ④ 装完的验证（空目录 / 缺锚点 / 缺 SKILL.md 都算失败）
  ⑤ 幂等（第二次不重装、不 clone）
  ⑥ 失败路径不留 staging、报错里带可复制手动命令
  ⑦ PLANNERS_NO_AUTO_INSTALL=1 → 只报不装

真·联网安装不在这里测（单测不许碰网）：见适配器的验收脚本。
跑法：python3 lib/planners_modules_install_test.py
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import planners_modules_install as installer  # noqa: E402
from planners_modules import module_candidates  # noqa: E402

MODULE = 'planners-source-index'


def library_root():
    current = HERE
    for _ in range(12):
        if current.name == installer.LIBRARY_DIR_NAME:
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


LIBRARY_ROOT = library_root()


class FakeResult:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ScratchTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='pm-py-install-test-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def fake_module(self, name=MODULE, root=None):
        root = root or self.root
        directory = root / name
        for anchor in installer.MODULE_SPECS[name]:
            target = directory / anchor
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('# fixture\n', encoding='utf-8')
        return directory

    def fake_runner(self, fixture, clone_status=0, clone_stderr=''):
        calls = []

        def run(command, args, cwd=None, env=None):
            calls.append(' '.join([command] + list(args)))
            if command == 'git' and args and args[0] == 'clone':
                if clone_status != 0:
                    return FakeResult(clone_status, '', clone_stderr)
                shutil.copytree(str(fixture), args[-1])
                return FakeResult(0)
            if command == 'git' and 'rev-parse' in args:
                return FakeResult(0, 'deadbeef\n')
            if command == 'git' and 'tag' in args:
                return FakeResult(0, '')
            if command in ('git', 'npx'):
                return FakeResult(0, 'v1\n')
            return FakeResult(1, '', 'not found')

        run.calls = calls
        return run


class InstallRootTest(ScratchTestCase):
    def test_precedence(self):
        home = self.root / 'home'
        home.mkdir(parents=True, exist_ok=True)
        root, source, _ = installer.install_root_for(
            MODULE, env={'PLANNERS_MODULES_INSTALL_DIR': '/tmp/explicit'}, home=home)
        self.assertEqual(str(root), '/tmp/explicit')
        self.assertEqual(source, 'PLANNERS_MODULES_INSTALL_DIR')

        root, source, _ = installer.install_root_for(
            MODULE, env={'PLANNERS_MODULES_HOME': '/tmp/not-there-yet'}, home=home)
        self.assertEqual(str(root), '/tmp/not-there-yet')

        root, _source, _ = installer.install_root_for(MODULE, env={}, home=home)
        self.assertEqual(root, home / '.planners-modules')

        # PLANNERS_MODULES_HOME 指向「存在但里面没有这个模组」的目录 → 不许往里塞
        foreign = home / 'somewhere-else'
        foreign.mkdir()
        root, _source, _ = installer.install_root_for(MODULE, env={'PLANNERS_MODULES_HOME': str(foreign)}, home=home)
        self.assertEqual(root, home / '.planners-modules')


class ForbiddenTargetTest(ScratchTestCase):
    def test_rejects(self):
        self.assertIsNotNone(LIBRARY_ROOT, '测试没找到库根')
        home = '/tmp/pm-home'
        with self.assertRaisesRegex(ValueError, '工作树内'):
            installer.assert_install_target_allowed(
                LIBRARY_ROOT / '00-system' / MODULE, home=home, library_root=LIBRARY_ROOT)
        for runtime in ('.claude/skills', '.codex/skills', '.gemini/config/skills'):
            with self.assertRaisesRegex(ValueError, 'runtime 技能目录'):
                installer.assert_install_target_allowed(Path(home) / runtime / MODULE, home=home)
        with self.assertRaisesRegex(ValueError, '系统目录'):
            installer.assert_install_target_allowed('/usr/lib/' + MODULE, home=home)
        # macOS 的临时区（/var/folders/…）是合法落点，不许被 /var 误杀
        installer.assert_install_target_allowed('/var/folders/xx/yy/' + MODULE, home=home)
        installer.assert_install_target_allowed(
            Path(home) / '.planners-modules' / MODULE, home=home, library_root=LIBRARY_ROOT)


class CandidateOrderTest(unittest.TestCase):
    def test_user_level_candidate_is_last(self):
        candidates = module_candidates(MODULE)
        self.assertGreater(len(candidates), 1)
        root, _source, _configured = installer.install_root_for(MODULE)
        self.assertEqual(candidates[-1], root / MODULE)
        repo_copies = [c for c in candidates[:-1] if '02-skills-library' in str(c)]
        self.assertTrue(repo_copies, '原有候选被弄丢了')
        for candidate in repo_copies:
            self.assertLess(candidates.index(candidate), len(candidates) - 1)


class VerifyInstallTest(ScratchTestCase):
    def test_empty_git_only_and_missing_anchors_fail(self):
        empty = self.root / 'empty'
        empty.mkdir()
        self.assertFalse(installer.verify_install(empty, MODULE)['ok'])

        git_only = self.root / 'gitonly'
        (git_only / '.git').mkdir(parents=True)
        result = installer.verify_install(git_only, MODULE)
        self.assertFalse(result['ok'])
        self.assertIn('空的', result['reason'])

        partial = self.root / 'partial'
        partial.mkdir()
        (partial / 'SKILL.md').write_text('# partial\n', encoding='utf-8')
        result = installer.verify_install(partial, MODULE)
        self.assertFalse(result['ok'])
        self.assertIn('contracts/source-index.schema.json', result['missing'])

        self.assertTrue(installer.verify_install(self.fake_module(), MODULE)['ok'])


class EnsureModuleTest(ScratchTestCase):
    def options(self, install_dir, runner, logs=None):
        return dict(
            env={'PLANNERS_MODULES_INSTALL_DIR': str(install_dir)},
            home=self.root,
            runner=runner,
            library_root=LIBRARY_ROOT,
            log=(logs.append if logs is not None else (lambda _message: None)),
        )

    def test_idempotent(self):
        install_dir = self.root / 'modules'
        fixture = self.fake_module(root=self.root / 'fixture')
        runner = self.fake_runner(fixture)
        logs = []
        options = self.options(install_dir, runner, logs)

        first = installer.ensure_module(MODULE, **options)
        self.assertEqual(first['action'], 'installed')
        self.assertEqual(first['commit'], 'deadbeef')
        self.assertEqual(first['tags'], [])
        clones = [call for call in runner.calls if call.startswith('git clone')]
        self.assertEqual(len(clones), 1)

        second = installer.ensure_module(MODULE, **options)
        self.assertEqual(second['action'], 'reused')
        self.assertEqual(len([call for call in runner.calls if call.startswith('git clone')]), 1)
        self.assertTrue(any('已装好，不需要重装' in line for line in logs))
        self.assertFalse([p for p in install_dir.iterdir() if p.name.startswith('.pm-staging-')])

    def test_failure_cleans_staging_and_reports_manual_command(self):
        install_dir = self.root / 'modules'
        fixture = self.fake_module(root=self.root / 'fixture')
        runner = self.fake_runner(fixture, clone_status=128, clone_stderr='fatal: unable to access repository')
        with self.assertRaises(ValueError) as caught:
            installer.ensure_module(MODULE, **self.options(install_dir, runner))
        message = str(caught.exception)
        self.assertIn('自动安装', message)
        self.assertIn('unable to access repository', message)
        self.assertIn('git clone --depth 1 https://github.com/thePlannerIvan/', message)
        self.assertIn('npx skills add ', message)
        self.assertFalse((install_dir / MODULE).exists(), '失败后不该留下模组目录')
        self.assertFalse([p for p in install_dir.iterdir() if p.name.startswith('.pm-staging-')])

    def test_no_auto_install_reports_without_installing(self):
        install_dir = self.root / 'modules'
        fixture = self.fake_module(root=self.root / 'fixture')
        runner = self.fake_runner(fixture)
        logs = []
        candidates = [self.root / 'sibling' / MODULE, install_dir / MODULE]
        options = self.options(install_dir, runner, logs)
        options['env'] = dict(options['env'], PLANNERS_NO_AUTO_INSTALL='1')
        options['candidates'] = candidates

        with self.assertRaises(ValueError) as caught:
            installer.ensure_module(MODULE, **options)
        message = str(caught.exception)
        self.assertIn('找不到公共模组 ' + MODULE, message)
        for candidate in candidates:
            self.assertIn(str(candidate), message)
        self.assertIn('npx skills add https://github.com/thePlannerIvan/planners-source-index', message)
        self.assertIn('git clone --depth 1 ', message)
        self.assertFalse([call for call in runner.calls if call.startswith('git clone')])
        self.assertFalse(install_dir.exists(), '禁止安装时连安装根都不该建')
        self.assertTrue(any('只报不装' in line for line in logs))

    def test_existing_but_broken_target_is_not_overwritten(self):
        install_dir = self.root / 'modules'
        broken = install_dir / MODULE
        broken.mkdir(parents=True)
        (broken / 'README.md').write_text('not a module\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '没通过验证'):
            installer.ensure_module(MODULE, **self.options(
                install_dir, self.fake_runner(self.fake_module(root=self.root / 'fixture'))))
        self.assertEqual((broken / 'README.md').read_text(encoding='utf-8'), 'not a module\n')


class LibraryRootGuardTest(ScratchTestCase):
    def test_adapter_guard_is_blind_proof(self):
        """适配器必须自己认得出库根，否则「不许装进库里」的闸形同虚设。"""
        detected = installer.find_library_root(HERE)
        self.assertIsNotNone(detected, '适配器没认出库根，库内安装就拦不住了')
        self.assertTrue(str(LIBRARY_ROOT).startswith(detected))
        with self.assertRaisesRegex(ValueError, '工作树内'):
            installer.assert_install_target_allowed(
                Path(detected) / '00-system' / MODULE, library_root=detected)


class LibraryRootFalsePositiveTest(ScratchTestCase):
    def test_parent_holding_modules_is_not_library_root(self):
        """skill 的父目录里躺着模组目录 ≠ 库根；不许把合法安装根误判成库。"""
        home = self.root / 'home'
        install_dir = home / '.planners-modules'
        (install_dir / 'planners-review-core').mkdir(parents=True)
        (install_dir / 'planners-source-index').mkdir()
        detected = installer.find_library_root(self.root / 'planners-bypage' / 'scripts' / 'lib')
        self.assertIsNone(detected, f'把普通目录认成了库根：{detected}')
        installer.assert_install_target_allowed(install_dir / MODULE, home=home, library_root=detected)


class NoTagReportingTest(ScratchTestCase):
    def _options(self, install_dir, runner, logs):
        return dict(
            env={'PLANNERS_MODULES_INSTALL_DIR': str(install_dir)},
            home=self.root,
            runner=runner,
            library_root=LIBRARY_ROOT,
            log=logs.append,
        )

    def test_says_out_loud_when_there_is_no_tag(self):
        logs = []
        install_dir = self.root / 'a' / 'modules'
        fixture = self.fake_module(root=self.root / 'a' / 'fixture')
        result = installer.ensure_module(MODULE, **self._options(
            install_dir, self.fake_runner(fixture), logs))
        self.assertEqual(result['tags'], [])
        self.assertTrue(any('没有 tag 可钉' in line for line in logs))

        logs_tagged = []
        install_dir_b = self.root / 'b' / 'modules'
        fixture_b = self.fake_module(root=self.root / 'b' / 'fixture')
        runner_b = self.fake_runner(fixture_b)

        def tagged_runner(command, args, cwd=None, env=None):
            if command == 'git' and 'tag' in args:
                return FakeResult(0, 'v1.0.0\n')
            return runner_b(command, args, cwd=cwd, env=env)

        tagged = installer.ensure_module(MODULE, **self._options(install_dir_b, tagged_runner, logs_tagged))
        self.assertEqual(tagged['tags'], ['v1.0.0'])
        self.assertTrue(any('tag：v1.0.0' in line for line in logs_tagged))
        self.assertFalse(any('没有 tag 可钉' in line for line in logs_tagged))


class ModuleRefTest(ScratchTestCase):
    def _options(self, install_dir, runner, **extra):
        env = {'PLANNERS_MODULES_INSTALL_DIR': str(install_dir)}
        env.update(extra)
        return dict(env=env, home=self.root, runner=runner, library_root=LIBRARY_ROOT,
                    log=lambda _message: None)

    def test_ref_pins_and_default_follows_head(self):
        self.assertEqual(installer.module_ref({'PLANNERS_MODULES_REF': 'v1.0.0'}), 'v1.0.0')
        self.assertIsNone(installer.module_ref({}), '不设就得是 None（= 装默认分支 HEAD）')

        runner = self.fake_runner(self.fake_module(root=self.root / 'pinned' / 'fixture'))
        result = installer.ensure_module(MODULE, **self._options(
            self.root / 'pinned' / 'modules', runner, PLANNERS_MODULES_REF='v1.0.0'))
        clones = [call for call in runner.calls if call.startswith('git clone')]
        self.assertEqual(len(clones), 1)
        self.assertIn('--branch v1.0.0', clones[0])
        self.assertTrue(result['commit'], '钉了也要报 commit')

        runner_head = self.fake_runner(self.fake_module(root=self.root / 'head' / 'fixture'))
        installer.ensure_module(MODULE, **self._options(self.root / 'head' / 'modules', runner_head))
        head_clone = next(call for call in runner_head.calls if call.startswith('git clone'))
        self.assertNotIn('--branch', head_clone, '默认不许钉，跟着 HEAD 走')

    def test_bad_ref_fails_honestly(self):
        install_dir = self.root / 'bad'
        runner = self.fake_runner(
            self.fake_module(root=install_dir / 'fixture'),
            clone_status=128,
            clone_stderr='fatal: Remote branch v9.9.9 not found in upstream origin')
        with self.assertRaises(ValueError) as caught:
            installer.ensure_module(MODULE, **self._options(
                install_dir / 'modules', runner, PLANNERS_MODULES_REF='v9.9.9'))
        message = str(caught.exception)
        self.assertIn('not found in upstream origin', message)
        self.assertIn('--branch v9.9.9', message)
        self.assertFalse((install_dir / 'modules' / MODULE).exists())
        self.assertFalse([p for p in (install_dir / 'modules').iterdir() if p.name.startswith('.pm-staging-')])


class ManualCommandTest(unittest.TestCase):
    def test_commands_are_copy_pasteable(self):
        commands = installer.manual_commands(MODULE, env={}, home='/tmp/pm-home')
        self.assertEqual(commands['root'], '/tmp/pm-home/.planners-modules')
        self.assertEqual(
            commands['npx'],
            'npx skills add https://github.com/thePlannerIvan/planners-source-index --skill planners-source-index')
        self.assertEqual(
            commands['git'],
            'git clone --depth 1 https://github.com/thePlannerIvan/planners-source-index.git '
            '"/tmp/pm-home/.planners-modules/planners-source-index"')
        self.assertIn('/a', str(installer.module_not_found(MODULE, ['/a', '/b'])))


if __name__ == '__main__':
    unittest.main(verbosity=2)
