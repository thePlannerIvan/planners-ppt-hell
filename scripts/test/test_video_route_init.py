#!/usr/bin/env python3
"""Video route init: a flat folder of loose images plus the upstream visual-plan.json, no source document."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_source_material import index_file_names  # noqa: E402
from project_state import (CONTENT, DIRECTION, PROJECT, SVG, content, page_version, sync,  # noqa: E402
                           versions)
from test_source_assets import png_bytes  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]


def init(project_dir, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "init_svg_project.py"), str(project_dir), *map(str, args)],
        capture_output=True,
        text=True,
    )


def source_manifest(root):
    return json.loads((root / PROJECT / "source" / "source_assets.json").read_text(encoding="utf-8"))


def name_to_asset_id(manifest):
    """File name → asset ID, read back from the registered occurrences."""
    return {
        occurrence["original_ref"]: asset["asset_id"]
        for asset in manifest["assets"]
        for occurrence in asset["occurrences"]
    }


class VideoRouteFixtures:
    """夹具与辅助：一平铺图片文件夹、按上游形状造契约、跑 init。不是测试类。"""

    """夹具与辅助：建图片文件夹、造契约、跑 init。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.folder = self.tmp_path / "images"
        self.folder.mkdir()
        (self.folder / "图1.png").write_bytes(png_bytes())
        (self.folder / "cover.png").write_bytes(png_bytes(60, 30))
        (self.folder / "spare.png").write_bytes(png_bytes(12, 12))
        (self.folder / ".DS_Store").write_bytes(b"not an image")

    def tearDown(self):
        self.tmp.cleanup()

    # ---- visual-plan.json fixtures, shaped like the upstream contract ----

    def asset(self, path, kind="image", **extra):
        return {"kind": kind, "path": path, "label": extra.pop("label", Path(path).stem), **extra}

    def screen(self, screen_id, assets, captions=None, note=None, **fields):
        sample = {"layout": "grid", "cols": 2, "assets": assets}
        if captions is not None:
            sample["captions"] = captions
        if note is not None:
            sample["note"] = note
        screen = {
            "screen_id": screen_id,
            "beat_id": "beat-" + screen_id.rsplit("-", 1)[-1],
            "title": screen_id,
            "question": "为什么" + screen_id + "？",
            "must_show": ["画面上要有 " + screen_id],
            "must_express": ["必须表达的语义 " + screen_id],
            "exact_labels": ["标签" + screen_id],
            "evidence": ["SRC-01#p2"],
            "sample": sample,
        }
        screen.update(fields)
        return screen

    def plan(self, screens, version="5.0", title="视频标题", **extra):
        data = {
            "contract_version": version,
            "title": title,
            "script_hash": "a" * 64,
            "screens": screens,
            **extra,
        }
        path = self.tmp_path / "visual-plan.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path



class VideoRouteInitTests(VideoRouteFixtures, unittest.TestCase):
    """视频入口本身：路径、屏号、图片账本、空屏、以及 `next` 不会吐 errno。"""

    def test_pack_becomes_a_valid_project_with_upstream_identity(self):
        # Upstream paths are relative to its own asset root and nested; the pack is flattened.
        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("deliverable/assets/图1.png")],
                        captions=["花字一"], note="样张说明一"),
            self.screen("screen-beat-02", [self.asset("deliverable/assets/shots/cover.png")],
                        captions=["花字二"]),
            self.screen("screen-beat-03", [self.asset("deliverable/assets/spare.png")]),
        ])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((root / PROJECT / "source" / "source.md").exists())

        written = json.loads((root / CONTENT).read_text(encoding="utf-8"))
        self.assertEqual(written["source_path"], "")
        self.assertEqual(written["unused_assets"], {})
        self.assertEqual(written["project"], "视频标题")
        # screen_id → page_key, unchanged, in upstream order.
        self.assertEqual([p["page_key"] for p in written["pages"]],
                         ["screen-beat-01", "screen-beat-02", "screen-beat-03"])

        names = name_to_asset_id(source_manifest(root))
        first = written["pages"][0]
        self.assertEqual(first["source_assets"], [names["图1.png"]])
        self.assertEqual(written["pages"][1]["source_assets"], [names["cover.png"]])
        # On-screen material only, grouped by where it came from.
        self.assertEqual(first["content"],
                         "【必须出现的内容】\n画面上要有 screen-beat-01\n"
                         "【原样标签】\n标签screen-beat-01\n"
                         "【花字】\n花字一")
        # Rationale lives in notes: question, must_express, evidence, beat_id and the sample.
        self.assertIn("beat_id：beat-01", first["notes"])
        for rationale in ("为什么screen-beat-01？", "必须表达的语义 screen-beat-01",
                          "SRC-01#p2", "样张说明一", "layout=grid"):
            self.assertIn(rationale, first["notes"])
            self.assertNotIn(rationale, first["content"])
        self.assertEqual(content(root)["pages"][0]["page_key"], "screen-beat-01")

    def test_unknown_asset_path_fails_cleanly(self):
        plan = self.plan([self.screen("screen-beat-01", [self.asset("deliverable/assets/missing.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not in the --assets folder: deliverable/assets/missing.png", result.stderr)
        self.assertIn("图1.png", result.stderr)
        self.assertFalse(root.exists())

    def test_text_free_screen_is_accepted_when_it_carries_a_picture(self):
        """一屏可以就是一张纯画面：没有上屏文字也成立，只要这屏有图。"""
        picture_only = self.screen(
            "screen-beat-01",
            [self.asset("图1.png"), self.asset("cover.png"), self.asset("spare.png")],
            must_show=[], exact_labels=[],
        )
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", self.plan([picture_only]))
        self.assertEqual(result.returncode, 0, result.stderr)
        page = content(root)["pages"][0]
        self.assertEqual(page["content"], "")
        self.assertEqual(len(page["source_assets"]), 3)
        self.assertEqual(sync(root)["pages"][0]["page_key"], "screen-beat-01")

    def test_screen_with_neither_text_nor_image_is_refused(self):
        """既无文字也无图的空屏仍然不成立——那才是真正没有任何东西可看。"""
        blank = self.screen("screen-beat-01", [], must_show=[], exact_labels=[])
        pictures = self.screen("screen-beat-02",
                               [self.asset("图1.png"), self.asset("cover.png"), self.asset("spare.png")])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", self.plan([blank, pictures]))
        self.assertEqual(result.returncode, 2)
        self.assertIn("neither on-screen text", result.stderr)
        self.assertIn("screen-beat-01", result.stderr)
        self.assertFalse(root.exists())

    def test_unreferenced_loose_image_fails_cleanly_naming_the_file(self):
        plan = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no screen in visual-plan.json references them", result.stderr)
        self.assertIn("cover.png", result.stderr)
        self.assertIn("spare.png", result.stderr)
        self.assertNotIn(".DS_Store", result.stderr)
        self.assertFalse(root.exists())

    def test_non_image_assets_go_to_notes_not_source_assets(self):
        plan = self.plan([
            self.screen("screen-beat-01", [
                self.asset("deliverable/assets/图1.png"),
                self.asset("data/users.csv", kind="csv", columns=["nickname"], lines=6),
            ], captions=["花字"]),
            self.screen("screen-beat-02", [self.asset("cover.png")]),
            self.screen("screen-beat-03", [self.asset("spare.png")]),
        ])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        first = json.loads((root / CONTENT).read_text(encoding="utf-8"))["pages"][0]
        self.assertEqual(first["source_assets"], [name_to_asset_id(source_manifest(root))["图1.png"]])
        self.assertIn("data/users.csv", first["notes"])
        self.assertIn("csv", first["notes"])
        self.assertIn('"lines": 6', first["notes"])
        self.assertNotIn("users.csv", first["content"])

    def test_two_paths_flattened_onto_one_file_are_refused(self):
        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("deliverable/a/图1.png")]),
            self.screen("screen-beat-02", [self.asset("deliverable/b/图1.png")]),
            self.screen("screen-beat-03", [self.asset("cover.png"), self.asset("spare.png")]),
        ])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("resolve to the same file", result.stderr)
        self.assertIn("图1.png", result.stderr)

    def test_legacy_contract_is_refused(self):
        plan = self.tmp_path / "visual-plan.json"
        plan.write_text(json.dumps({"contract_version": "4.0", "title": "旧", "blueprints": []},
                                   ensure_ascii=False), encoding="utf-8")
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("contract_version '5.0'", result.stderr)

    def test_screen_id_outside_the_page_key_grammar_is_refused_not_renamed(self):
        plan = self.plan([self.screen("1屏", [self.asset("图1.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("page_key unchanged", result.stderr)
        self.assertIn("1屏", result.stderr)

    def test_lookalike_images_are_accounted_per_file_name(self):
        folder = self.tmp_path / "lookalike"
        folder.mkdir()
        (folder / "shot.png").write_bytes(png_bytes(20, 20))
        (folder / "shot copy.png").write_bytes(png_bytes(20, 20))
        plan = self.plan([self.screen("screen-beat-01", [self.asset("shot.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("shot copy.png", result.stderr)

        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("shot.png")]),
            self.screen("screen-beat-02", [self.asset("shot copy.png")]),
        ])
        result = init(root, "--assets", folder, "--plan", plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = source_manifest(root)
        self.assertEqual(manifest["image_count"], 1)
        names = name_to_asset_id(manifest)
        self.assertEqual(names["shot.png"], names["shot copy.png"])
        pages = json.loads((root / CONTENT).read_text(encoding="utf-8"))["pages"]
        self.assertEqual(pages[0]["source_assets"], pages[1]["source_assets"])

    def test_subdirectory_is_an_error_not_a_silent_skip(self):
        (self.folder / "nested").mkdir()
        (self.folder / "nested" / "hidden.png").write_bytes(png_bytes(8, 8))
        plan = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be flat", result.stderr)
        self.assertIn("nested", result.stderr)

    def test_video_project_gets_past_create_without_a_source_document(self):
        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("图1.png"), self.asset("cover.png"),
                                           self.asset("spare.png")]),
        ])
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", self.folder, "--plan", plan).returncode, 0)
        self.assertFalse((root / PROJECT / "source" / "source.md").exists())

        # 真状态一：一页都没写，方向文件也还没有 —— `next` 先要方向，不是 errno。
        unwritten = self.next_payload(root)
        self.assertEqual(unwritten["state"], "CONTENT")
        self.assertIn(str(root / "_internal/01_content/design_direction.md"), unwritten["missing"][0])
        self.assertNotIn("No such file", json.dumps(unwritten, ensure_ascii=False))

        # 真状态二：方向写了，页面还没画 —— 给动作指令，仍然不是 errno。
        (root / DIRECTION).write_text("# 这套画面的秩序\n", encoding="utf-8")
        payload = self.next_payload(root)
        self.assertNotIn("No such file", payload.get("instruction", ""))
        self.assertNotIn("Errno", payload.get("instruction", ""))
        self.assertIn("还没有画出这些页面", payload["instruction"])
        self.assertEqual(payload["state"], "CREATE")
        self.assertEqual(payload["pages"], ["screen-beat-01"])

        (root / SVG / "screen-beat-01.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">'
            '<rect width="1920" height="1080" fill="#FFFFFF"/>'
            '<text x="120" y="180" font-size="48" font-family="Arial" fill="#111111">Evidence</text></svg>',
            encoding="utf-8",
        )

        # A page without source.md must still version: the plan is the material.
        page = content(root)["pages"][0]
        self.assertRegex(page_version(root, page), r"^[0-9a-f]{64}$")
        self.assertEqual(versions(root), {"screen-beat-01": page_version(root, page)})

    def next_payload(self, root):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_source_and_assets_together_is_a_clean_error(self):
        markdown = self.tmp_path / "brief.md"
        markdown.write_text("# Brief\n", encoding="utf-8")
        plan = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--source", markdown, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not allowed with argument --source", result.stderr)
        self.assertFalse(root.exists())

    def test_plan_without_assets_is_a_clean_error(self):
        plan = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        result = init(self.tmp_path / "project", "--plan", plan)
        self.assertEqual(result.returncode, 2)
        self.assertIn("one of the arguments --source --assets is required", result.stderr)

    def test_assets_without_plan_is_a_clean_error(self):
        markdown = self.tmp_path / "brief.md"
        markdown.write_text("# Brief\n", encoding="utf-8")
        result = init(self.tmp_path / "project", "--assets", self.folder)
        self.assertEqual(result.returncode, 2)
        self.assertIn("needs --plan <visual-plan.json>", result.stderr)
        result = init(self.tmp_path / "project", "--source", markdown, "--plan", "x.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--plan belongs to the --assets route", result.stderr)

    def test_video_manifest_shape_matches_markdown_route(self):
        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("图1.png"), self.asset("cover.png"),
                                           self.asset("spare.png")]),
        ])
        video_root = self.tmp_path / "video"
        self.assertEqual(init(video_root, "--assets", self.folder, "--plan", plan).returncode, 0)

        source_dir = self.tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "hero.png").write_bytes(png_bytes(30, 10))
        markdown = source_dir / "brief.md"
        markdown.write_text("# Brief\n\n![主图](hero.png)\n", encoding="utf-8")
        doc_root = self.tmp_path / "document"
        result = init(doc_root, "--source", markdown)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Registered", result.stdout)

        video = source_manifest(video_root)
        document = source_manifest(doc_root)
        self.assertEqual(sorted(video), sorted(document))
        asset_keys = sorted(video["assets"][0])
        self.assertTrue(asset_keys)
        for asset in video["assets"] + document["assets"]:
            self.assertEqual(sorted(asset), asset_keys)
        # Same keys, same types: only the intake-specific values differ.
        for key in asset_keys:
            self.assertEqual(type(video["assets"][0][key]), type(document["assets"][0][key]))

    def test_source_route_still_writes_source_md_and_the_stub(self):
        source_dir = self.tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "hero.png").write_bytes(png_bytes(30, 10))
        markdown = source_dir / "brief.md"
        markdown.write_text("# Brief\n\n![主图](hero.png)\n", encoding="utf-8")
        root = self.tmp_path / "document"
        result = init(root, "--source", markdown)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("![主图](assets/asset_001.png)", (root / PROJECT / "source" / "source.md").read_text(encoding="utf-8"))
        self.assertEqual(
            json.loads((root / CONTENT).read_text(encoding="utf-8")),
            {
                "project": "",
                "source_path": "_internal/00_project/source/source.md",
                "source_assets_path": "_internal/00_project/source/source_assets.json",
                "pages": [],
            },
        )

    def test_ambiguous_file_names_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            index_file_names(["图1.png", "图1.PNG"])
        self.assertEqual(index_file_names(["图1.png", "图2.png"]), {"图1.png": "图1.png", "图2.png": "图2.png"})


class ContentSourceTests(VideoRouteFixtures, unittest.TestCase):
    """上屏内容按来源分组：标记剥掉、图注不进、重复去掉。"""

    def test_text_marker_is_stripped_and_the_entry_becomes_body_copy(self):
        screen = self.screen(
            "screen-beat-01", [self.asset("图1.png")],
            must_show=["文字：1966 年 3 月 16 日 · 加州安纳海姆东百老汇 704 号", "开业第一天 12 位顾客"],
            exact_labels=["704"],
        )
        plan = self.plan([screen, self.screen("screen-beat-02", [self.asset("cover.png")]),
                          self.screen("screen-beat-03", [self.asset("spare.png")])])
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", self.folder, "--plan", plan).returncode, 0)
        body = content(root)["pages"][0]["content"]
        # 「文字：」是契约的标记，不是正文。
        self.assertNotIn("文字：", body)
        self.assertIn("1966 年 3 月 16 日 · 加州安纳海姆东百老汇 704 号", body)
        # 按来源分组，做画面看得出哪条来自哪一类。
        self.assertIn("【正文】", body)
        self.assertIn("【必须出现的内容】", body)
        self.assertIn("【原样标签】", body)
        # 正文与「必须出现的内容」被分到两边，标记之外的文字两边都在。
        self.assertIn("开业第一天 12 位顾客", body)
        parts = body.split("【原样标签】")
        self.assertIn("1966 年 3 月 16 日 · 加州安纳海姆东百老汇 704 号", parts[0])
        self.assertIn("704", parts[1])

    def test_asset_label_never_reaches_content(self):
        """`sample.assets[].label` 是审阅页的图注，不是上屏文字（P-07）。"""
        screen = self.screen("screen-beat-01", [self.asset("图1.png", label="棋盘格 Slip-On 实拍（画面里没有字）")])
        plan = self.plan([screen, self.screen("screen-beat-02", [self.asset("cover.png")]),
                          self.screen("screen-beat-03", [self.asset("spare.png")])])
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", self.folder, "--plan", plan).returncode, 0)
        page = content(root)["pages"][0]
        self.assertNotIn("棋盘格 Slip-On 实拍", page["content"])
        # 它仍然在 notes 里，作为这一屏的图注说明。
        self.assertIn("审阅页图注：棋盘格 Slip-On 实拍", page["notes"])

    def test_duplicate_entries_appear_once(self):
        screen = self.screen(
            "screen-beat-01", [self.asset("图1.png")],
            must_show=["1966", "开业"], exact_labels=["1966", "704"], captions=["1966", "花字"],
        )
        plan = self.plan([screen, self.screen("screen-beat-02", [self.asset("cover.png")]),
                          self.screen("screen-beat-03", [self.asset("spare.png")])])
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", self.folder, "--plan", plan).returncode, 0)
        lines = content(root)["pages"][0]["content"].splitlines()
        self.assertEqual(lines.count("1966"), 1)
        self.assertEqual(lines.count("704"), 1)
        self.assertEqual(lines.count("花字"), 1)
        # 去重不等于强制子集：exact_labels 独有的条目照样留着。
        self.assertIn("704", lines)
        # 每个分组只出现一次。
        self.assertEqual(lines.count("【原样标签】"), 1)

    def test_exact_labels_is_not_forced_to_be_a_subset_of_must_show(self):
        screen = self.screen("screen-beat-01", [self.asset("图1.png")],
                             must_show=["只有这一条"], exact_labels=["另一条独立标签"])
        plan = self.plan([screen, self.screen("screen-beat-02", [self.asset("cover.png")]),
                          self.screen("screen-beat-03", [self.asset("spare.png")])])
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", self.folder, "--plan", plan).returncode, 0)
        body = content(root)["pages"][0]["content"]
        self.assertIn("只有这一条", body)
        self.assertIn("另一条独立标签", body)


class BoundaryReportingTests(VideoRouteFixtures, unittest.TestCase):
    """认不出的字段、素材库口径、相对路径 —— 三条边界要说得出口。"""

    def test_unknown_fields_are_named_on_the_spot_not_buried_in_notes(self):
        screen = self.screen("screen-beat-01", [self.asset("图1.png")],
                             transition="wipe", hold=1200)
        screen["sample"]["crop_focus"] = "left"
        plan = self.plan([screen, self.screen("screen-beat-02", [self.asset("cover.png")]),
                          self.screen("screen-beat-03", [self.asset("spare.png")])],
                         storyboard_revision=7)
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout + result.stderr
        # 字段名 + 值，当场能裁决。
        for field, value in (("transition", '"wipe"'), ("hold", "1200"),
                             ("sample.crop_focus", '"left"'), ("storyboard_revision", "7")):
            self.assertIn(field, output, field)
            self.assertIn(value, output, field)
        # 契约根部的字段只报一次，不跟着每一屏重复。
        self.assertEqual(output.count("storyboard_revision"), 1)
        # 不再有一个没人读的「待裁决」收集器藏在 notes 里。
        self.assertNotIn("待裁决", content(root)["pages"][0]["notes"])
        self.assertNotIn("transition", content(root)["pages"][0]["notes"])
        # 认不出字段不是硬失败：契约升级加字段不该把这条路打死。
        self.assertNotIn("transition", content(root)["pages"][0]["content"])

    def test_unreferenced_image_error_says_pack_not_library_and_forbids_deleting(self):
        plan = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        root = self.tmp_path / "project"
        result = init(root, "--assets", self.folder, "--plan", plan)
        self.assertEqual(result.returncode, 2)
        message = result.stderr
        # 全等检查还在（它防的是静默丢图），但它现在说清了两件事。
        self.assertIn("no screen in visual-plan.json references them", message)
        self.assertIn("cover.png", message)
        self.assertIn("交付包是 <包>/assets/", message)
        self.assertIn("禁止为了通过这道检查去删除源素材", message)
        self.assertFalse(root.exists())

    def test_relative_path_errors_say_which_directory_they_used(self):
        plan_file = self.plan([self.screen("screen-beat-01", [self.asset("图1.png")])])
        for args in ([str(self.tmp_path / "project"), "--assets", "no-such-images", "--plan", str(plan_file)],
                     [str(self.tmp_path / "project"), "--assets", str(self.folder), "--plan", "no-such-plan.json"]):
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "init_svg_project.py"), *args],
                capture_output=True, text=True, cwd=str(self.tmp_path))
            self.assertEqual(result.returncode, 2, args)
            self.assertIn("相对路径按当前工作目录解析", result.stderr, args)
            # 报错里那个路径是相对哪个目录拼出来的，写清楚。
            self.assertIn(str(self.tmp_path), result.stderr, args)
            self.assertIn("三个路径都给绝对路径最省事", result.stderr, args)
            self.assertFalse((self.tmp_path / "project").exists())


class ProjectStateTests(VideoRouteFixtures, unittest.TestCase):
    """路线与契约绑定写在项目状态里：该跑哪一半检查、画面还算不算数。"""

    def pack(self, script_text=None, declared_hash=None):
        pack = self.tmp_path / "pack"
        (pack / "assets").mkdir(parents=True, exist_ok=True)
        for name in ("图1.png", "cover.png", "spare.png"):
            (pack / "assets" / name).write_bytes(png_bytes(20, 10))
        if script_text is not None:
            (pack / "script.md").write_text(script_text, encoding="utf-8")
        plan = self.plan([
            self.screen("screen-beat-01", [self.asset("图1.png")]),
            self.screen("screen-beat-02", [self.asset("cover.png")]),
            self.screen("screen-beat-03", [self.asset("spare.png")]),
        ], script_hash=declared_hash if declared_hash is not None else "a" * 64)
        (pack / "visual-plan.json").write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
        return pack

    def test_the_route_and_the_contract_are_recorded(self):
        pack = self.pack()
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        state = json.loads((root / PROJECT / "page_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(state["route"], "video")
        recorded = state["visual_plan"]
        self.assertEqual(Path(recorded["path"]), (pack / "visual-plan.json").resolve())
        self.assertEqual(recorded["sha256"], hashlib.sha256((pack / "visual-plan.json").read_bytes()).hexdigest())
        self.assertEqual(recorded["script_hash"], "a" * 64)
        self.assertEqual(recorded["contract_version"], "5.0")
        # 稿子的位置不另记一份：从契约所在的目录找（多一份地址就多一处会过期的说法）。
        self.assertNotIn("script_path", recorded)

    def test_a_slides_project_records_the_slides_route(self):
        source = self.tmp_path / "brief.md"
        source.write_text("# Brief\n", encoding="utf-8")
        root = self.tmp_path / "deck"
        self.assertEqual(init(root, "--source", source).returncode, 0)
        state = json.loads((root / PROJECT / "page_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(state["route"], "slides")
        self.assertNotIn("visual_plan", state)

    def test_changed_plan_is_a_warning(self):
        pack = self.pack()
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        data = json.loads((pack / "visual-plan.json").read_text(encoding="utf-8"))
        data["screens"][0]["must_show"] = ["改过的上屏文字"]
        (pack / "visual-plan.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        payload = json.loads(result.stdout)
        record = self.record(payload, "visual_plan_sha256")
        self.assertEqual(record["level"], "warning")
        self.assertIn("变了", record["message"])
        # warning 不拦路：状态仍然是「去画页面」。
        self.assertEqual(payload["state"], "CREATE")

    def test_script_hash_mismatch_is_an_error(self):
        pack = self.pack(script_text="改过的口播稿\n", declared_hash="a" * 64)
        root = self.tmp_path / "project"
        # 契约声明的 hash 与包内 script.md 的实际内容不符：画面可能要重画。
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "CONTENT")
        record = self.record(payload, "script_hash")
        self.assertEqual(record["level"], "error")
        self.assertEqual(record["declared"], "a" * 64)
        self.assertNotEqual(record["actual"], record["declared"])
        self.assertIn("口播稿改过", payload["instruction"])

    def test_matching_script_hash_is_not_reported_as_a_problem(self):
        text = "这一屏讲证据。\n"
        pack = self.pack(script_text=text, declared_hash=hashlib.sha256(text.encode()).hexdigest())
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        payload = json.loads(result.stdout)
        # 正常状态不是空数组：每一项都有一条正面记录。
        levels = {item["check"]: item["level"] for item in payload["contract"]}
        self.assertEqual(levels, {"visual_plan_sha256": "ok", "contract_version": "ok",
                                  "script_hash": "ok"})
        self.assertEqual(self.record(payload, "script_hash")["actual"],
                         self.record(payload, "script_hash")["declared"])

    def test_contract_always_reports_the_checks_it_ran(self):
        """「核过没问题」必须是正面记录，否则与「压根没核」在输出上一样。"""
        pack = self.pack()
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        for stage in ("before-direction", "after-direction"):
            if stage == "after-direction":
                (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
                capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertIn("contract", payload, stage)
            self.assertTrue(payload["contract"], stage)
            for item in payload["contract"]:
                self.assertIn(item["level"], {"ok", "warning", "error", "unchecked"}, item)
                self.assertTrue(item.get("message"), item)
                if item["level"] == "unchecked":
                    self.assertTrue(item.get("reason"), item)

    def test_contract_records_why_it_could_not_check(self):
        """核不成也要留一条 unchecked 记录，并说清为什么。"""
        pack = self.pack()          # 包里没有 script.md
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        record = self.record(json.loads(result.stdout), "script_hash")
        self.assertEqual(record["level"], "unchecked")
        self.assertIn("script.md", record["reason"])
        # 契约不在原处时，三项都要报 unchecked，不能变成空数组。
        (pack / "visual-plan.json").rename(pack / "moved-away.json")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        records = json.loads(result.stdout)["contract"]
        self.assertEqual({item["check"] for item in records},
                         {"visual_plan_sha256", "contract_version", "script_hash"})
        self.assertTrue(all(item["level"] == "unchecked" for item in records))

    def record(self, payload, check):
        found = [item for item in payload["contract"] if item["check"] == check]
        self.assertEqual(len(found), 1, payload["contract"])
        return found[0]

    def test_missing_script_md_says_it_cannot_be_checked(self):
        pack = self.pack()  # 包里没有 script.md
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        payload = json.loads(result.stdout)
        record = self.record(payload, "script_hash")
        self.assertEqual(record["level"], "unchecked")
        self.assertIn("无法核对", record["message"])
        self.assertIn("不是核对通过", record["message"])
        # 找的是**契约旁边**那份稿子（上游交过来的包就是这个形状），不是本项目目录里。
        self.assertIn(str((pack / "visual-plan.json").parent / "script.md"), record["reason"])
        self.assertNotIn(str(root / "script.md"), record["reason"])

    def test_the_script_is_looked_for_next_to_the_contract_not_in_the_project(self):
        import hashlib
        text = "这一屏讲证据。\n"
        pack = self.pack(declared_hash=hashlib.sha256(text.encode()).hexdigest())
        root = self.tmp_path / "project"
        self.assertEqual(init(root, "--assets", pack / "assets",
                              "--plan", pack / "visual-plan.json").returncode, 0)
        (root / DIRECTION).write_text("# 秩序\n", encoding="utf-8")
        # 只把稿子放进项目自己的目录：那不是契约旁边，核对不该通过。
        (root / "script.md").write_text(text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        self.assertEqual(self.record(json.loads(result.stdout), "script_hash")["level"], "unchecked")
        # 放到契约旁边（上游包的位置）之后，同一个 hash 就核对通过了。
        (pack / "script.md").write_text(text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate" / "ppt_pipeline.py"), str(root), "next", "--json"],
            capture_output=True, text=True)
        record = self.record(json.loads(result.stdout), "script_hash")
        self.assertEqual(record["level"], "ok")
        self.assertEqual(record["declared"], record["actual"])

    def test_video_route_prints_svg_as_the_deliverable_not_pptx(self):
        pack = self.pack()
        root = self.tmp_path / "video"
        result = init(root, "--assets", pack / "assets", "--plan", pack / "visual-plan.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("02_svg_source/<page_key>.svg", result.stdout)
        self.assertIn("这条路的出口", result.stdout)
        self.assertNotIn("final_deck.pptx", result.stdout)

        source = self.tmp_path / "brief.md"
        source.write_text("# Brief\n", encoding="utf-8")
        deck = self.tmp_path / "deck"
        slides = init(deck, "--source", source)
        self.assertIn("final_deck.pptx", slides.stdout)
        self.assertNotIn("这条路的出口", slides.stdout)


if __name__ == "__main__":
    unittest.main()
