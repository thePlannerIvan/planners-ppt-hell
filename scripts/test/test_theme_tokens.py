#!/usr/bin/env python3
"""风格库读法：list / show、var() 展开、以及解析不掉的 token 必须被报出来。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "style"))
import theme_tokens  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
THEMES_CLI = SCRIPTS / "style" / "theme_tokens.py"

# 一个刻意有缺陷的主题：--card 引用了一个库里没有的圆角刻度。
BROKEN_TOKENS = """:root {
  /* palette */
  --ink:        #111111;
  --paper:      #ffffff;
  --text:       var(--ink);
  --deep:       var(--text);
  --card:       var(--r-flat);
  --shadow:     0 2px 4px rgba(0, 0, 0, 0.2);
  --font-body:  "Inter", sans-serif;
}
"""


def theme_json(theme_id="demo-theme", **overrides):
    data = {"id": theme_id, "name": "Demo Theme", "nameZh": "示例主题",
            "preview": {"shell": "#f0eee8", "surface": "#fafaf7", "text": "#0a0a0a", "accent": "#1a4cdb"}}
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class ThemeTokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.theme = self.dir / "demo-theme"
        self.theme.mkdir()
        (self.theme / "theme.json").write_text(theme_json(), encoding="utf-8")
        (self.theme / "tokens.css").write_text(BROKEN_TOKENS, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, env=None):
        import os
        merged = dict(os.environ, **(env or {}))
        result = subprocess.run([sys.executable, str(THEMES_CLI), *args],
                                capture_output=True, text=True, env=merged)
        return result.returncode, json.loads(result.stdout)

    # ---- list ----

    def test_list_reports_identity_and_preview(self):
        code, payload = self.run_cli("list", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        item = payload["themes"][0]
        self.assertEqual(item["id"], "demo-theme")
        self.assertEqual(item["name"], "Demo Theme")
        self.assertEqual(item["nameZh"], "示例主题")
        self.assertEqual(item["preview"], {"shell": "#f0eee8", "surface": "#fafaf7",
                                           "text": "#0a0a0a", "accent": "#1a4cdb"})
        self.assertEqual(payload["problems"], [])

    def test_broken_theme_json_is_reported_not_swallowed(self):
        other = self.dir / "half-baked"
        other.mkdir()
        (other / "theme.json").write_text(json.dumps({"id": "half-baked", "name": "Half"}),
                                          encoding="utf-8")
        (other / "tokens.css").write_text(":root {\n  --ink: #111;\n}\n", encoding="utf-8")
        code, payload = self.run_cli("list", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(payload["count"], 1)
        problems = {item["id"]: item["problem"] for item in payload["problems"]}
        self.assertIn("half-baked", problems)
        self.assertIn("nameZh", problems["half-baked"])
        self.assertIn("preview", problems["half-baked"])

    def test_theme_json_id_must_match_the_directory_name(self):
        (self.theme / "theme.json").write_text(theme_json(theme_id="something-else"), encoding="utf-8")
        code, payload = self.run_cli("list", "--themes-dir", str(self.dir))
        self.assertIn("与目录名不一致", payload["problems"][0]["problem"])

    # ---- show ----

    def test_show_expands_var_references_to_actual_values(self):
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(payload["tokens"]["--ink"], "#111111")
        self.assertEqual(payload["tokens"]["--text"], "#111111")
        # 间接引用也要展开到底，不是只展开一层。
        self.assertEqual(payload["tokens"]["--deep"], "#111111")
        self.assertEqual(payload["tokens"]["--paper"], "#ffffff")
        self.assertNotIn("var(", payload["tokens"]["--deep"])

    def test_show_reports_tokens_it_cannot_resolve(self):
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        unresolved = {item["token"]: item for item in payload["unresolved"]}
        self.assertIn("--card", unresolved)
        self.assertEqual(unresolved["--card"]["missing"], ["--r-flat"])
        self.assertEqual(unresolved["--card"]["declared"], "var(--r-flat)")
        self.assertNotIn("--card", payload["tokens"])
        self.assertEqual(payload["summary"]["unresolved"], 1)
        self.assertEqual(payload["summary"]["resolved"], len(payload["tokens"]))

    def test_indirect_reference_to_a_broken_token_is_also_reported(self):
        (self.theme / "tokens.css").write_text(
            ":root {\n  --ink: #111;\n  --card: var(--r-flat);\n  --panel: var(--card);\n}\n",
            encoding="utf-8")
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        unresolved = {item["token"]: item for item in payload["unresolved"]}
        self.assertEqual(sorted(unresolved), ["--card", "--panel"])
        # 传递依赖：面板缺的是同一个没定义的名字，不是一个模糊的「上游出错」。
        self.assertEqual(unresolved["--panel"]["missing"], ["--r-flat"])

    def test_var_fallback_value_is_kept_verbatim(self):
        (self.theme / "tokens.css").write_text(
            ":root {\n  --gap: var(--r-sm, 8px);\n}\n", encoding="utf-8")
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        unresolved = {item["token"]: item for item in payload["unresolved"]}
        self.assertIn("--gap", unresolved)
        self.assertIn("--r-sm", unresolved["--gap"]["missing"])

    def test_cycle_is_reported_as_unresolved_not_a_crash(self):
        (self.theme / "tokens.css").write_text(
            ":root {\n  --a: var(--b);\n  --b: var(--a);\n}\n", encoding="utf-8")
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(payload["summary"]["resolved"], 0)
        self.assertTrue(all("循环引用" in "".join(item["missing"]) for item in payload["unresolved"]))

    def test_unknown_theme_lists_what_exists(self):
        code, payload = self.run_cli("show", "nope", "--themes-dir", str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("demo-theme", payload["error"])

    def test_theme_id_cannot_walk_out_of_the_library(self):
        code, payload = self.run_cli("show", "../demo-theme", "--themes-dir", str(self.dir))
        self.assertEqual(code, 2)
        self.assertIn("主题 id 只能是目录名", payload["error"])

    # ---- 目录定位：不写死 ----

    def test_env_var_points_at_the_library(self):
        code, payload = self.run_cli("list", env={theme_tokens.THEMES_DIR_ENV: str(self.dir)})
        self.assertEqual(code, 0)
        self.assertEqual(Path(payload["themes_dir"]), self.dir.resolve())
        self.assertIn(theme_tokens.THEMES_DIR_ENV, payload["themes_dir_source"])

    def test_cli_flag_beats_the_env_var(self):
        other = self.dir / "elsewhere"
        other.mkdir()
        code, payload = self.run_cli("list", "--themes-dir", str(other),
                                     env={theme_tokens.THEMES_DIR_ENV: str(self.dir)})
        self.assertEqual(Path(payload["themes_dir"]), other.resolve())
        self.assertEqual(payload["themes_dir_source"], "--themes-dir")

    def test_themes_dir_also_works_after_the_subcommand(self):
        code, payload = self.run_cli("show", "demo-theme", "--themes-dir", str(self.dir))
        self.assertEqual(code, 0)
        self.assertEqual(payload["tokens"]["--ink"], "#111111")

    def test_missing_library_says_where_it_looked_and_how_to_override(self):
        """一个默认位置都不存在时：报错要说清找过哪里、可以用什么覆盖。"""
        from unittest import mock
        looked_at = Path(self.tmp.name) / "not-here" / "themes"
        with mock.patch.object(theme_tokens, "default_theme_dirs", return_value=[looked_at]):
            with self.assertRaises(ValueError) as caught:
                theme_tokens.resolve_themes_dir("", {})
        error = str(caught.exception)
        self.assertIn(str(looked_at), error)
        self.assertIn("--themes-dir", error)
        self.assertIn(theme_tokens.THEMES_DIR_ENV, error)

    def test_new_location_when_the_library_moved(self):
        # 默认按 Skill 根的相对位置找；这里验证「相对位置」这一条真的指向兄弟 Skill。
        candidates = theme_tokens.default_theme_dirs()
        self.assertEqual(candidates[0].name, "themes")
        self.assertEqual(candidates[0].parent.name, "visual")
        self.assertEqual(candidates[0].parent.parent.name, "video-craft")

    def test_real_library_is_found_and_every_theme_loads(self):
        """默认位置找得到本仓的风格库时，23 套都要能读出来。"""
        try:
            themes_dir, source = theme_tokens.resolve_themes_dir()
        except ValueError as exc:
            self.skipTest(f"本机没有风格库：{exc}")
        payload = theme_tokens.list_themes(themes_dir, source)
        self.assertGreater(payload["count"], 0)
        self.assertEqual(payload["problems"], [])
        for item in payload["themes"]:
            shown = theme_tokens.show_theme(themes_dir, item["id"])
            self.assertIn("--text", shown["tokens"])
            # 展开过的东西里不该还剩下 var()。
            resolved_with_var = [name for name, value in shown["tokens"].items() if "var(" in value]
            self.assertEqual(resolved_with_var, [])


if __name__ == "__main__":
    unittest.main()
