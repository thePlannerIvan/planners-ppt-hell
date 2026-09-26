#!/usr/bin/env python3
"""视频路线与幻灯片路线是两个终态：一个有 PPTX，一个到 SVG 为止。

用户拿到这套页面的方式不同（做 PPT 还是录视频），所以「完成」的定义也不同：

- 幻灯片：`final_deck.pptx` 存在、hash 对得上、导出后复核过。
- 视频画面：全部页面 `check` 无 error + **作者提交过整套审阅**；`final_deck.pptx`、
  `EXPORT`、`EXPORT_VERIFY` 都不出现在这条路上，审阅是门不是可选项。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "orchestrate"))
sys.path.insert(0, str(SCRIPTS / "test"))
from canvas_frame import FRAME_H_INT, FRAME_VIEWBOX, FRAME_W_INT  # noqa: E402
from project_state import (CONTENT, DIRECTION, PNG, PROJECT, REVIEW, SVG, VALIDATION,  # noqa: E402
                           content, digest, page_version, read, sha, versions, write)
from ppt_pipeline import check, export, inspect, next_action  # noqa: E402
from review_feedback import consume  # noqa: E402
from test_source_assets import png_bytes  # noqa: E402

PIPELINE = SCRIPTS / "orchestrate" / "ppt_pipeline.py"


def svg_markup(text="Evidence"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" '
            f'viewBox="{FRAME_VIEWBOX}"><rect width="{FRAME_W_INT}" height="{FRAME_H_INT}" fill="#FFFFFF"/>'
            f'<text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">{text}</text></svg>')


class RouteTerminalStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.folder = self.tmp_path / "pack" / "assets"
        self.folder.mkdir(parents=True)
        self.plan = self.tmp_path / "pack" / "visual-plan.json"
        self.script = self.tmp_path / "pack" / "script.md"
        self.script.write_text("这一屏讲证据。\n", encoding="utf-8")
        self.keys = ["beat-01", "beat-02"]

    def tearDown(self):
        self.tmp.cleanup()

    # ---- 建项目 ----

    def build_video_project(self, with_direction=True):
        for index, key in enumerate(self.keys, 1):
            (self.folder / f"{key}.png").write_bytes(png_bytes(40 + index, 20))
        import hashlib
        screens = [{"screen_id": key, "beat_id": key, "title": key, "question": "为什么？",
                    "must_show": ["文字：正文 " + key], "must_express": ["语义"], "exact_labels": [key],
                    "evidence": ["SRC-1"], "sample": {"layout": "grid", "assets": [
                        {"kind": "image", "path": f"assets/{key}.png", "label": "图注 " + key}]}}
                   for key in self.keys]
        self.plan.write_text(json.dumps({
            "contract_version": "5.0", "title": "视频标题",
            "script_hash": hashlib.sha256(self.script.read_bytes()).hexdigest(),
            "screens": screens}, ensure_ascii=False), encoding="utf-8")
        self.root = self.tmp_path / "video"
        result = subprocess.run([sys.executable, str(SCRIPTS / "init_svg_project.py"), str(self.root),
                                 "--assets", str(self.folder), "--plan", str(self.plan)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in self.keys:
            (self.root / SVG / f"{key}.svg").write_text(svg_markup(), encoding="utf-8")
        if with_direction:
            self.write_direction()
        return result

    def build_slides_project(self):
        source = self.tmp_path / "brief.md"
        source.write_text("# Brief\nEvidence 42%.\n", encoding="utf-8")
        self.root = self.tmp_path / "slides"
        result = subprocess.run([sys.executable, str(SCRIPTS / "init_svg_project.py"), str(self.root),
                                 "--source", str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        write(self.root / CONTENT, {"project": "Deck", "pages": [
            {"page_key": key, "title": key, "content": "Evidence", "source_assets": []} for key in self.keys]})
        (self.root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        from project_state import sync
        sync(self.root)
        for key in self.keys:
            (self.root / SVG / f"{key}.svg").write_text(svg_markup(), encoding="utf-8")
        return result

    def write_direction(self):
        (self.root / DIRECTION).write_text(
            "# 这套画面的秩序\n\n字幕安全区、人物位置、不透明与透明、强调动画余量。\n", encoding="utf-8")

    def seal(self, verdict="clean"):
        """造出「check 过、也看过图」的状态：这是夹具，不是流程。"""
        records = {}
        for key, version in versions(self.root).items():
            png = self.root / PNG / f"{key}.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (192, 108), "white").save(png)
            rec = {"version": version, "errors": 0, "png_sha256": sha(png), "validator": {}}
            write(self.root / VALIDATION / f"{key}.json", rec)
            records[key] = {"render_token": digest(rec), "note": "看过了", "first_glance": "左上标题",
                            "design_check": "规则 4／10", "position": "x=120,y=150,w=400,h=80",
                            "verdict": verdict, "must_fix": verdict == "must_fix"}
        write(self.root / VALIDATION / "inspections.json", records)

    def submit_review(self):
        """按**新接缝**交一套审阅：页面经宿主写整份状态（宿主原样落盘）→ Skill 收件。

        以前这里调 `save_feedback`（旧服务器的写入口）。写入口退役了，但这条用例要证的事
        一个字没变：整套批准之后视频路线才算过关。
        """
        from ppt_pipeline import make_review
        snapshot = make_review(self.root)
        payload = {"review_id": snapshot["review_id"],
                   "pages": {key: {"decision": "approved", "feedback": "", "annotations": [], "assets": []}
                             for key in snapshot["versions"]},
                   "overall_feedback": ""}
        write(self.root / REVIEW / "feedback.json",
              {**payload, "provenance": {"source": "review_page", "transport": "http",
                                         "submitted_at": "2026-09-26T00:00:00+00:00"}})
        consume(self.root)
        return snapshot

    # ---- E：design_direction.md 在视频路线上是前置 ----

    def test_next_asks_for_design_direction_first(self):
        self.build_video_project(with_direction=False)
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "CONTENT")
        self.assertIn(str(self.root / DIRECTION), payload["missing"][0])
        self.assertIn("03_video_route.md", payload["stage"])
        self.assertIn("字幕安全区", payload["instruction"])

    def test_check_refuses_a_video_project_without_design_direction(self):
        self.build_video_project(with_direction=False)
        with self.assertRaisesRegex(ValueError, "design_direction.md"):
            check(self.root, None)

    def test_slides_route_does_not_require_design_direction(self):
        self.build_slides_project()
        (self.root / DIRECTION).unlink()
        # 幻灯片路线保持现状：方向文件是推荐的前置，不是门。
        self.assertEqual(next_action(self.root)["state"], "CREATE")

    # ---- B4：next 给动作，不给 errno ----

    def test_next_gives_an_action_not_an_errno_when_no_page_is_written(self):
        self.build_video_project()
        for key in self.keys:
            (self.root / SVG / f"{key}.svg").unlink()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "CREATE")
        self.assertEqual(payload["pages"], self.keys)
        self.assertNotIn("No such file", payload["instruction"])
        self.assertNotIn("Errno", payload["instruction"])
        self.assertIn("beat-01", payload["instruction"])
        self.assertIn("还没有画出这些页面", payload["instruction"])
        # 原始异常仍然留痕，只是不当指令用。
        self.assertIn("No such file", payload.get("detail", ""))

    def test_next_names_only_the_pages_that_are_missing(self):
        self.build_video_project()
        (self.root / SVG / "beat-02.svg").unlink()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "CREATE")
        self.assertEqual(payload["pages"], ["beat-02"])
        self.assertIn("check --pages beat-02", payload["instruction"])

    # ---- B2／B3：终态与审阅是门 ----

    def test_review_is_a_gate_and_no_export_option_is_offered(self):
        self.build_video_project()
        self.seal()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "VISUAL_REVIEW")
        self.assertFalse(payload["export_available"])
        self.assertIn("02_svg_source", payload["deliverable"])
        self.assertNotIn("go straight to export", payload["instruction"])
        # 这条路上不出现 PPTX 交付物，也不出现导出状态。
        self.assertNotIn("final_deck.pptx", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(payload["state"], {"EXPORT", "EXPORT_VERIFY"})

    def test_must_fix_pushes_the_page_back_to_create(self):
        self.build_video_project()
        self.seal(verdict="must_fix")
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "CREATE")
        self.assertEqual(payload["pages"], self.keys)

    def test_complete_needs_the_review_record_and_no_pptx(self):
        self.build_video_project()
        self.seal()
        self.submit_review()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "COMPLETE")
        self.assertIn("02_svg_source", payload["deliverable"])
        self.assertNotIn("pptx", payload)
        self.assertFalse((self.root / "final_deck.pptx").exists())
        self.assertEqual(payload["pages"], self.keys)
        # 终态里没有一个字在说 PPTX。
        self.assertNotIn("final_deck.pptx", json.dumps(payload, ensure_ascii=False))

    def test_page_changed_after_review_sends_it_back_to_review(self):
        self.build_video_project()
        self.seal()
        self.submit_review()
        self.assertEqual(next_action(self.root)["state"], "COMPLETE")
        (self.root / SVG / "beat-01.svg").write_text(svg_markup("Changed"), encoding="utf-8")
        self.seal()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "VISUAL_REVIEW")

    def test_export_and_export_inspect_are_refused_on_the_video_route(self):
        self.build_video_project()
        self.seal()
        with self.assertRaisesRegex(ValueError, "不导出 PPTX"):
            export(self.root)
        from ppt_pipeline import export_inspect
        with self.assertRaisesRegex(ValueError, "不导出 PPTX"):
            export_inspect(self.root, "note", [])

    def test_cli_reports_the_video_route_without_pptx(self):
        """命令行这一层也要看得出两个出口：视频项目的 check 输出带 route。"""
        self.build_video_project()
        self.seal()
        result = subprocess.run([sys.executable, str(PIPELINE), str(self.root), "next", "--json"],
                                capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["route"], "video")
        self.assertEqual(payload["state"], "VISUAL_REVIEW")

    def test_slides_route_still_ends_at_the_pptx(self):
        self.build_slides_project()
        self.seal()
        self.submit_review()
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "EXPORT")
        self.assertEqual(payload["route"], "slides")

    # ---- B1：inspect 的牙齿 ----

    def inspect_argv(self, *extra):
        return [sys.executable, str(PIPELINE), str(self.root), "inspect",
                "--page", "beat-01", "--render-token", "x", "--note", "n",
                "--first-glance", "g", "--design-check", "d", *extra]

    def test_inspect_needs_a_position(self):
        self.build_video_project()
        result = subprocess.run(self.inspect_argv("--clean"), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--position", result.stderr)

    def test_inspect_needs_exactly_one_verdict(self):
        # 这两个反馈都在 argparse 这一层就被拒，项目还没被碰过。
        self.root = self.tmp_path / "no-such-project"
        result = subprocess.run(self.inspect_argv("--position", "x=10,y=10"),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--clean", result.stderr)
        result = subprocess.run(self.inspect_argv("--position", "x=10,y=10", "--clean", "--must-fix"),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not allowed with argument", result.stderr)

    def test_position_must_land_inside_the_canvas(self):
        self.build_video_project()
        self.seal()
        record = read(self.root / VALIDATION / "beat-01.json")
        token = digest(record)
        with self.assertRaisesRegex(ValueError, "落在画布外"):
            inspect(self.root, "beat-01", token, "note", "glance", "design", "x=1700,y=0,w=400,h=100",
                    "clean")

    def test_filling_ok_is_not_enough(self):
        """三个自由文本字段填满不算数——这正是这道闸门以前被绕过去的方式。"""
        self.build_video_project()
        self.seal()
        record = read(self.root / VALIDATION / "beat-01.json")
        token = digest(record)
        with self.assertRaisesRegex(ValueError, "位置"):
            inspect(self.root, "beat-01", token, "ok", "ok", "ok", "", "clean")

    def test_a_good_record_marks_the_page_inspected(self):
        self.build_video_project()
        self.seal()
        record = read(self.root / VALIDATION / "beat-01.json")
        token = digest(record)
        result = inspect(self.root, "beat-01", token, "标题可读", "左上标题", "规则 4 无违规",
                         "x=120,y=150,w=400,h=80", "clean")
        self.assertTrue(result["inspected"])
        self.assertEqual(result["verdict"], "clean")
        stored = read(self.root / VALIDATION / "inspections.json")["beat-01"]
        self.assertEqual(stored["position"], "x=120,y=150,w=400,h=80")
        self.assertFalse(stored["must_fix"])
        from project_state import inspected
        self.assertTrue(inspected(self.root, "beat-01", page_version(self.root, content(self.root)["pages"][0])))

    def test_old_records_without_a_position_stop_counting(self):
        self.build_video_project()
        self.seal()
        records = read(self.root / VALIDATION / "inspections.json")
        records["beat-01"].pop("position")
        records["beat-01"].pop("verdict")
        write(self.root / VALIDATION / "inspections.json", records)
        payload = next_action(self.root)
        self.assertEqual(payload["state"], "CREATE")
        self.assertIn("beat-01", payload["pages"])


if __name__ == "__main__":
    unittest.main()
