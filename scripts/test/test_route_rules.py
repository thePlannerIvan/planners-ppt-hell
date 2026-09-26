#!/usr/bin/env python3
"""两条路线各跑哪一半检查，以及「文字伸出画布」必须被拦。

实测起因（测试报告的 P-05）：一个 72px 的中文标题挪到 x=1700 时，文字伸出画布 640px，
校验器判 `pass, errors=0`——`<rect>` 与 `<image>` 都有出画布检查，文字只有一条 info 级的
安全区提示。安全区是美术方向（保持 info），画布不是。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canvas_frame import FRAME_H_INT, FRAME_VIEWBOX, FRAME_W_INT  # noqa: E402
from validate_svg_layout import validate_file  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{FRAME_W_INT}" height="{FRAME_H_INT}" '
        f'viewBox="{FRAME_VIEWBOX}">')
TITLE = "所有人都穿上理由就没了"


class RouteRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.svg = self.root / "page.svg"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, body):
        self.svg.write_text(HEAD + body + "</svg>", encoding="utf-8")
        return self.svg

    @staticmethod
    def codes(report):
        return [issue["code"] for issue in report["issues"]]

    # ---- A1 文字出画布 ----
    def test_text_outside_canvas_is_an_error(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   f'<text x="1700" y="300" font-size="72" font-family="Arial" fill="#111111">{TITLE}</text>')
        report = validate_file(self.svg)
        self.assertIn("TEXT_OUTSIDE_CANVAS", self.codes(report))
        self.assertEqual(report["summary"]["errors"], 1)
        self.assertEqual(report["status"], "fail")
        issue = next(i for i in report["issues"] if i["code"] == "TEXT_OUTSIDE_CANVAS")
        self.assertEqual(issue["severity"], "error")
        # 伸出画布多少，是框算出来的，不是猜的：终点 ≈ 2564，画布 1920。
        self.assertGreater(issue["detail"]["x"] + issue["detail"]["w"], FRAME_W_INT + 5)
        # 安全区提示仍然只是 info，不跟着升级。
        self.assertEqual([i["severity"] for i in report["issues"] if i["code"] == "OUTSIDE_SAFE_MARGIN"],
                         ["info"])

    def test_text_inside_canvas_is_not_flagged(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   f'<text x="180" y="300" font-size="72" font-family="Arial" fill="#111111">{TITLE}</text>')
        report = validate_file(self.svg)
        self.assertNotIn("TEXT_OUTSIDE_CANVAS", self.codes(report))
        self.assertEqual(report["summary"]["errors"], 0)

    def test_centered_text_is_measured_from_its_anchor(self):
        # text-anchor=middle 的框左移半个宽度：居中标题不能被算成越界。
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   f'<text x="960" y="300" font-size="72" font-family="Arial" fill="#111111" '
                   f'text-anchor="middle">{TITLE}</text>')
        self.assertNotIn("TEXT_OUTSIDE_CANVAS", self.codes(validate_file(self.svg)))

    def test_self_check_still_catches_text_outside_canvas(self):
        # `--self-check` 跳过的是重叠估算，不是出画布。
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   f'<text x="1700" y="300" font-size="72" font-family="Arial" fill="#111111">{TITLE}</text>')
        self.assertIn("TEXT_OUTSIDE_CANVAS", self.codes(validate_file(self.svg, quick_mode=True)))

    # ---- N-1：风格 token 经内联 <style> 落地，视频路线认这三种取法 ----

    THEMED = ('<style>'
              ':root { --text: #0a0a0a; --font-body: "Inter", sans-serif; --accent: #2541ee; }'
              '.title, .subtitle { fill: var(--text); font-family: var(--font-body); }'
              '.hero { font-weight: 900; }'
              '</style>'
              '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
              '<text id="headline" class="title hero" x="180" y="240" font-size="48">标题</text>'
              '<text id="sub" class="subtitle" x="180" y="320" font-size="24">副标题</text>')

    def test_class_rule_inside_the_page_stylesheet_satisfies_the_text_requirement(self):
        """照 03_video_route.md 做（:root + class 规则 + var()）必须能过。"""
        self.write(self.THEMED)
        report = validate_file(self.svg, route="video")
        self.assertEqual(self.codes(report), [])
        self.assertEqual(report["status"], "pass")

    def test_style_attribute_with_a_defined_token_satisfies_it(self):
        self.write('<style>:root { --accent: #2541ee; --font-body: Inter; }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" x="180" y="240" font-size="48" '
                   'style="fill: var(--accent); font-family: var(--font-body)">行内</text>')
        report = validate_file(self.svg, route="video")
        self.assertEqual(self.codes(report), [])
        self.assertEqual(report["status"], "pass")

    def test_a_descendant_class_selector_also_counts(self):
        self.write('<style>:root { --text: #0a0a0a; --font-body: Inter; }'
                   '.card .title { fill: var(--text); font-family: var(--font-body); }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<g class="card"><text id="t" class="title" x="180" y="240" font-size="48">标题</text></g>')
        self.assertEqual(self.codes(validate_file(self.svg, route="video")), [])

    def test_undefined_token_is_a_hard_error(self):
        """token 拼错了从「静默取不到颜色」变成硬错误，并说清哪个元素、哪个 token。"""
        self.write('<style>:root { --text: #0a0a0a; }'
                   '.title { fill: var(--text); font-family: var(--font-body); }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="headline" class="title" x="180" y="240" font-size="48">标题</text>')
        report = validate_file(self.svg, route="video")
        self.assertIn("UNDEFINED_CSS_VAR", self.codes(report))
        issue = next(i for i in report["issues"] if i["code"] == "UNDEFINED_CSS_VAR")
        self.assertEqual(issue["severity"], "error")
        self.assertIn("--font-body", issue["message"])
        self.assertIn("font-family", issue["message"])
        self.assertEqual(issue["target"], "text_1")
        self.assertIn(":root", issue["hint"])
        # 没有回退值：说清后果是「取不到颜色」。
        self.assertIn("没有回退值", issue["detail"])
        self.assertIn("取不到颜色", issue["detail"])

    def test_a_fallback_value_still_errors_and_says_what_it_costs(self):
        """写了回退值页面看起来正常，但代价是这一处不再跟着主题走——也要说清楚。"""
        self.write('<style>:root { --text: #0a0a0a; }'
                   '.caption { fill: var(--accent-typo, #ff0000); '
                   'font-family: var(--font-body, Inter); }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" class="caption" x="180" y="240" font-size="48">花字</text>')
        report = validate_file(self.svg, route="video")
        issues = [i for i in report["issues"] if i["code"] == "UNDEFINED_CSS_VAR"]
        self.assertEqual(len(issues), 2)          # fill 与 font-family 各一条
        self.assertTrue(all(i["severity"] == "error" for i in issues))
        detail = issues[0]["detail"]
        self.assertIn("--accent-typo", detail)
        self.assertIn("#ff0000", detail)
        # 后果要说出来：回退值让它看起来正常，但换主题时这一处不会跟着变。
        self.assertIn("看起来正常", detail)
        self.assertIn("换主题时这一处不会跟着变，风格库对它失效", detail)
        self.assertIn("class 命中的 <style> 规则", detail)

    def test_undefined_token_in_an_element_attribute_is_caught_too(self):
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" x="180" y="240" font-size="48" fill="var(--nope)" '
                   'font-family="Inter">标题</text>')
        report = validate_file(self.svg, route="video")
        codes = self.codes(report)
        self.assertIn("UNDEFINED_CSS_VAR", codes)
        # 值取到了（虽然取不到颜色），所以不算 MISSING_FILL。
        self.assertNotIn("MISSING_FILL", codes)

    def test_a_stylesheet_rule_that_matches_no_class_does_not_pass_the_text(self):
        """<style> 里有规则但 class 不匹配 —— 不能误放行。"""
        self.write('<style>:root { --text: #0a0a0a; }'
                   '.somewhere-else { fill: var(--text); font-family: Inter; }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" class="headline" x="180" y="240" font-size="48">标题</text>')
        report = validate_file(self.svg, route="video")
        self.assertIn("MISSING_FILL", self.codes(report))
        self.assertIn("MISSING_FONT_FAMILY", self.codes(report))

    def test_an_element_selector_is_not_treated_as_a_class_match(self):
        self.write('<style>:root { --text: #0a0a0a; }'
                   'text { fill: var(--text); font-family: Inter; }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" x="180" y="240" font-size="48">标题</text>')
        self.assertIn("MISSING_FILL", self.codes(validate_file(self.svg, route="video")))

    def test_a_stylesheet_inside_a_comment_does_not_count(self):
        self.write('<!-- <style>.title { fill: #000; font-family: Inter; }</style> -->'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" class="title" x="180" y="240" font-size="48">标题</text>')
        self.assertIn("MISSING_FILL", self.codes(validate_file(self.svg, route="video")))

    def test_invalid_font_weight_from_the_stylesheet_is_still_an_error(self):
        self.write('<style>:root { --text: #0a0a0a; --font-body: Inter; }'
                   '.title { fill: var(--text); font-family: var(--font-body); font-weight: heavy; }</style>'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="t" class="title" x="180" y="240" font-size="48">标题</text>')
        self.assertIn("INVALID_FONT_WEIGHT", self.codes(validate_file(self.svg, route="video")))

    def test_slides_route_still_demands_explicit_attributes(self):
        self.write(self.THEMED)
        report = validate_file(self.svg, route="slides")
        codes = self.codes(report)
        self.assertIn("MISSING_FILL", codes)
        self.assertIn("MISSING_FONT_FAMILY", codes)
        # 幻灯片出口连 <style> 本身都不允许。
        self.assertIn("PROHIBITED_STYLE", codes)
        self.assertNotIn("UNDEFINED_CSS_VAR", codes)

    # ---- A2 按路线选规则 ----

    def video_demo_page(self):
        # 视频出口上这些都合法：<style>、<animate>、rotate、10px 小字。
        # 幻灯片出口上它们每一条都是 error。
        return self.write('<style>.k { font-weight: 700; }</style>'
                          '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                          '<text id="caption-1" class="k" x="180" y="300" font-size="10" '
                          'font-family="Arial" fill="#111111">小字</text>'
                          '<animate id="pulse" attributeName="opacity" dur="1s"/>'
                          '<line id="rule-1" x1="0" y1="0" x2="10" y2="10" transform="rotate(3)"/>')

    def test_video_route_skips_the_ppt_only_half_and_says_why(self):
        self.video_demo_page()
        report = validate_file(self.svg, route="video")
        self.assertEqual(report["summary"]["errors"], 0, report["issues"])
        self.assertEqual(report["status"], "pass")
        skipped = {item["rule"]: item for item in report["skipped_rules"]}
        for rule in ("TEXT_BELOW_READABILITY_FLOOR", "PROHIBITED_ELEMENTS", "PROHIBITED_ATTRIBUTES",
                     "PROHIBITED_TRANSFORM", "TSPAN_LINEBREAK", "FIDELITY_TEMPLATE"):
            self.assertIn(rule, skipped)
            self.assertTrue(skipped[rule]["why"].strip(), rule)
        self.assertIn("animate", skipped["PROHIBITED_ELEMENTS"]["why"])

    def test_slides_route_runs_the_ppt_only_half(self):
        self.video_demo_page()
        report = validate_file(self.svg, route="slides")
        codes = self.codes(report)
        for code in ("PROHIBITED_STYLE", "PROHIBITED_ANIMATE", "PROHIBITED_TRANSFORM",
                     "TEXT_BELOW_READABILITY_FLOOR"):
            self.assertIn(code, codes)
        # 幻灯片路线不跑 PPT 专属检查（它就是 PPT 出口），只跳过视频出口独有的那两条。
        self.assertEqual({item["rule"] for item in report["skipped_rules"]},
                         {"MISSING_ELEMENT_ID", "DUPLICATE_ELEMENT_ID"})

    def test_skew_and_matrix_are_in_the_same_ppt_only_group(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<g transform="matrix(1 0 0 1 10 10)"><rect width="10" height="10" fill="#111111"/></g>')
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<g transform="matrix(1 0 0 1 10 10)"><rect width="10" height="10" fill="#111111"/></g>')
        self.assertIn("PROHIBITED_TRANSFORM", self.codes(validate_file(self.svg, route="slides")))
        self.assertEqual(validate_file(self.svg, route="video")["summary"]["errors"], 0)

    def test_tspan_linebreak_is_ppt_only(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<text x="180" y="300" font-size="48" font-family="Arial" fill="#111111">甲<tspan dy="10">乙</tspan></text>')
        self.assertIn("TSPAN_LINEBREAK", self.codes(validate_file(self.svg, route="slides")))
        self.assertNotIn("TSPAN_LINEBREAK", self.codes(validate_file(self.svg, route="video")))

    def test_shared_half_runs_on_both_routes(self):
        # 两条路都成立的那一半：文字压文字、出画布、空页、缺填色、font-weight、图片拉伸。
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<text x="100" y="200" font-size="48" font-family="Arial" fill="#111111">A</text>'
                   '<text x="110" y="205" font-size="48" font-family="Arial">B</text>')
        for route in ("slides", "video"):
            codes = self.codes(validate_file(self.svg, route=route))
            self.assertIn("MISSING_FILL", codes, route)
            self.assertIn("TEXT_OVERLAP", codes, route)

    def test_stretched_image_is_refused_on_both_routes(self):
        (self.root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        self.write('<image href="pic.png" x="0" y="0" width="100" height="100" preserveAspectRatio="none"/>')
        for route in ("slides", "video"):
            self.assertIn("IMAGE_ASPECT_DISTORTION", self.codes(validate_file(self.svg, route=route)))

    # ---- I：视频出口独有的一条 —— 这一页得能被按元素指名 ----

    def test_video_page_without_any_element_id_is_refused(self):
        """实测 44 张真实页面 0 个 id；出口契约说要带 id，产出侧必须有人核。"""
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<text x="180" y="300" font-size="48" font-family="Arial" fill="#111111">标题</text>')
        report = validate_file(self.svg, route="video")
        self.assertIn("MISSING_ELEMENT_ID", self.codes(report))
        issue = next(i for i in report["issues"] if i["code"] == "MISSING_ELEMENT_ID")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(report["status"], "fail")
        # 报错要能指导下一步：给 id，然后重渲这一页。
        self.assertIn("稳定 id", issue["hint"])
        self.assertIn("重渲这一页", issue["hint"])

    def test_the_root_svg_id_does_not_count(self):
        self.svg.write_text(HEAD.replace("<svg ", '<svg id="page-shell" ', 1)
                            + '<rect width="1920" height="1080" fill="#ffffff"/>'
                              '<text x="180" y="300" font-size="48" font-family="Arial" fill="#111111">标题</text>'
                              "</svg>", encoding="utf-8")
        self.assertIn("MISSING_ELEMENT_ID", self.codes(validate_file(self.svg, route="video")))

    def test_data_id_attributes_do_not_count(self):
        # data-layout-id / data-template-* 是别的语义，不是动画层能指名的元素 id。
        self.write('<g data-layout-id="content_base" data-template-canvas-version="1">'
                   '<rect data-template-component="bg_light" data-template-origin="built_in" '
                   'x="0" y="0" width="1920" height="1080" fill="#ffffff"/></g>')
        self.assertIn("MISSING_ELEMENT_ID", self.codes(validate_file(self.svg, route="video")))

    def test_an_id_inside_a_comment_does_not_count(self):
        self.write('<!-- <rect id="not-real" width="10" height="10"/> -->'
                   '<rect width="1920" height="1080" fill="#ffffff"/>')
        self.assertIn("MISSING_ELEMENT_ID", self.codes(validate_file(self.svg, route="video")))

    def test_one_element_with_an_id_is_enough(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="headline" x="180" y="300" font-size="48" font-family="Arial" '
                   'fill="#111111">标题</text>')
        report = validate_file(self.svg, route="video")
        self.assertNotIn("MISSING_ELEMENT_ID", self.codes(report))
        self.assertEqual(report["summary"]["errors"], 0)

    def test_slides_route_does_not_ask_for_element_ids(self):
        self.write('<rect width="1920" height="1080" fill="#ffffff"/>'
                   '<text x="180" y="300" font-size="48" font-family="Arial" fill="#111111">标题</text>')
        report = validate_file(self.svg, route="slides")
        self.assertNotIn("MISSING_ELEMENT_ID", self.codes(report))
        skipped = {item["rule"] for item in report["skipped_rules"]}
        self.assertIn("MISSING_ELEMENT_ID", skipped)

    def test_the_id_check_names_only_the_video_route_among_skipped_rules(self):
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>')
        video = {item["rule"] for item in validate_file(self.svg, route="video")["skipped_rules"]}
        slides = {item["rule"] for item in validate_file(self.svg, route="slides")["skipped_rules"]}
        self.assertNotIn("MISSING_ELEMENT_ID", video)
        self.assertNotIn("DUPLICATE_ELEMENT_ID", video)
        self.assertEqual(slides, {"MISSING_ELEMENT_ID", "DUPLICATE_ELEMENT_ID"})

    # ---- 页内 id 必须唯一（视频出口独有） ----

    def test_a_duplicate_id_in_one_page_is_refused(self):
        """同一份 SVG 里 id 重复是非法 HTML，也是动画层指错的根源。"""
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="caption-1" x="180" y="300" font-size="48" font-family="Arial" '
                   'fill="#111111">一</text>'
                   '<text id="caption-1" x="180" y="380" font-size="48" font-family="Arial" '
                   'fill="#111111">二</text>')
        report = validate_file(self.svg, route="video")
        issue = next(i for i in report["issues"] if i["code"] == "DUPLICATE_ELEMENT_ID")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(report["status"], "fail")
        # 哪个 id、重复几次，都要说清。
        self.assertIn("caption-1", issue["message"])
        self.assertIn("2 次", issue["message"])
        # 下一步：把 page_key 放进去。这里的文件名就是 page_key，所以提示里会出现它。
        self.assertIn("page-caption-1", issue["hint"])

    def test_three_occurrences_are_reported_with_their_count(self):
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   + "".join(f'<text id="same" x="180" y="{300 + n * 60}" font-size="32" '
                             f'font-family="Arial" fill="#111111">{n}</text>' for n in range(3)))
        issue = next(i for i in validate_file(self.svg, route="video")["issues"]
                     if i["code"] == "DUPLICATE_ELEMENT_ID")
        self.assertIn("same（3 次）", issue["message"])

    def test_ids_prefixed_with_the_page_key_are_accepted(self):
        """`beat-04-caption-1` 这样的写法是对的：它让每一页的 id 在全片唯一。"""
        self.write('<rect id="beat-04-stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="beat-04-caption-1" x="180" y="300" font-size="48" font-family="Arial" '
                   'fill="#111111">花字</text>'
                   '<text id="beat-04-model-stage" x="180" y="380" font-size="48" font-family="Arial" '
                   'fill="#111111">模型</text>')
        report = validate_file(self.svg, route="video")
        codes = self.codes(report)
        self.assertNotIn("DUPLICATE_ELEMENT_ID", codes)
        self.assertNotIn("MISSING_ELEMENT_ID", codes)
        self.assertEqual(report["status"], "pass")

    def test_the_root_svg_id_colliding_with_a_child_is_refused(self):
        """根与子元素撞车也要拦：`#page` 只命中第一个（根），那个子元素再也指不到。

        两条判据看的范围不同，是故意的：MISSING 问「有没有可指名的元素」（根不算），
        DUPLICATE 问「这份 id 合法且不歧义吗」（根也是 HTML 里的一个 id，所以算）。
        """
        self.svg.write_text(HEAD.replace("<svg ", '<svg id="page" ', 1)
                            + '<rect id="page" width="1920" height="1080" fill="#ffffff"/>'
                            + "</svg>", encoding="utf-8")
        codes = self.codes(validate_file(self.svg, route="video"))
        self.assertIn("DUPLICATE_ELEMENT_ID", codes)
        # 有子元素带着 id，所以「没有可指名的元素」那条不该响。
        self.assertNotIn("MISSING_ELEMENT_ID", codes)

    def test_the_root_svg_id_alone_is_not_a_duplicate(self):
        self.svg.write_text(HEAD.replace("<svg ", '<svg id="page" ', 1)
                            + '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                            + "</svg>", encoding="utf-8")
        self.assertNotIn("DUPLICATE_ELEMENT_ID", self.codes(validate_file(self.svg, route="video")))

    def test_data_ids_and_commented_ids_do_not_create_duplicates(self):
        self.write('<!-- <rect id="ghost"/> -->'
                   '<g data-layout-id="content_base" data-template-canvas-version="1">'
                   '<rect id="stage" width="1920" height="1080" fill="#ffffff"/></g>'
                   '<text id="only-one" x="180" y="300" font-size="48" font-family="Arial" '
                   'fill="#111111">唯一</text>')
        self.assertNotIn("DUPLICATE_ELEMENT_ID", self.codes(validate_file(self.svg, route="video")))

    def test_slides_route_does_not_check_duplicate_ids(self):
        self.write('<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                   '<text id="same" x="180" y="300" font-size="48" font-family="Arial" fill="#111111">一</text>'
                   '<text id="same" x="180" y="380" font-size="48" font-family="Arial" fill="#111111">二</text>')
        self.assertNotIn("DUPLICATE_ELEMENT_ID", self.codes(validate_file(self.svg, route="slides")))

    # ---- 路线从项目状态读 ----

    def project(self, route_value):
        root = self.root / f"proj-{route_value}"
        (root / "_internal" / "00_project").mkdir(parents=True)
        (root / "_internal" / "02_svg_source").mkdir(parents=True)
        (root / "_internal" / "00_project" / "page_manifest.json").write_text(
            json.dumps({"version": "5.0", "route": route_value, "pages": []}), encoding="utf-8")
        page = root / "_internal" / "02_svg_source" / "beat-01.svg"
        page.write_text(HEAD + '<rect id="stage" width="1920" height="1080" fill="#ffffff"/>'
                              '<style>.k{}</style>'
                              '<text id="caption-1" x="180" y="300" font-size="10" font-family="Arial" '
                              'fill="#111">小字</text>'
                              "</svg>", encoding="utf-8")
        return root, page

    def run_cli(self, page, extra=()):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_svg_layout.py"), str(page.parent),
             "--file", str(page), *extra], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_route_comes_from_the_project_state(self):
        root, page = self.project("video")
        code, payload = self.run_cli(page)
        self.assertEqual(payload["route"], "video")
        self.assertIn("page_manifest.json", payload["route_source"])
        self.assertEqual(payload["summary"]["errors"], 0)
        self.assertTrue(payload["skipped_rules"])

    def test_slides_project_keeps_every_check(self):
        root, page = self.project("slides")
        code, payload = self.run_cli(page)
        self.assertEqual(payload["route"], "slides")
        self.assertEqual({item["rule"] for item in payload["skipped_rules"]},
                         {"MISSING_ELEMENT_ID", "DUPLICATE_ELEMENT_ID"})
        self.assertGreater(payload["summary"]["errors"], 0)
        self.assertEqual(code, 1)

    def test_explicit_route_overrides_the_project_state(self):
        root, page = self.project("video")
        code, payload = self.run_cli(page, ("--route", "slides"))
        self.assertEqual(payload["route"], "slides")
        self.assertEqual(payload["route_source"], "--route slides")
        self.assertGreater(payload["summary"]["errors"], 0)

    def test_path_outside_any_project_defaults_to_slides_and_says_so(self):
        self.video_demo_page()
        code, payload = self.run_cli(self.svg)
        self.assertEqual(payload["route"], "slides")
        self.assertIn("默认", payload["route_source"])
        self.assertGreater(payload["summary"]["errors"], 0)

    def test_fidelity_template_is_not_applied_on_the_video_route(self):
        root, page = self.project("video")
        code, payload = self.run_cli(page, ("--fidelity-template", str(self.root / "nope.json")))
        self.assertEqual(payload["summary"]["errors"], 0)
        self.assertIn("FIDELITY_TEMPLATE_SKIPPED",
                      [issue["code"] for issue in payload["reports"][0]["issues"]])


if __name__ == "__main__":
    unittest.main()
