import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


INTERNAL = "_internal"
STATE_PATH = f"{INTERNAL}/00_project/flow_state.json"
EVENTS_PATH = f"{INTERNAL}/00_project/flow_events.jsonl"

BLOCKING_WARNING_CODES = {
    "TEXT_OVERFLOW_MAJOR",
    "FOOTER_ZONE_INVASION",
}


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(root, event_type, details):
    event_path = root / EVENTS_PATH
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "details": details,
    }
    with event_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def sha256_file(path):
    path = Path(path)
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root):
    return load_json(root / INTERNAL / "00_project" / "page_manifest.json", {"pages": [], "batch_config": {}})


def page_keys(data):
    return [p.get("page_key") for p in data.get("pages", []) if isinstance(p, dict) and p.get("page_key")]


def batches(manifest_data):
    config = manifest_data.get("batch_config", {})
    return [(k, config[k].get("pages", [])) for k in sorted(config)]


def future_pages(manifest_data, batch_id):
    ids = [bid for bid, _ in batches(manifest_data)]
    if batch_id not in ids:
        return []
    future = []
    config = dict(batches(manifest_data))
    for bid in ids[ids.index(batch_id) + 1:]:
        future.extend(config.get(bid, []))
    return future


def first_open_batch(manifest_data):
    by_key = {p.get("page_key"): p for p in manifest_data.get("pages", []) if isinstance(p, dict)}
    for batch_id, keys in batches(manifest_data):
        if not keys:
            continue
        if not all(by_key.get(k, {}).get("visual_approved") for k in keys):
            return batch_id, keys
    return "", []


def has_review_server_provenance(data, expected_route):
    provenance = data.get("provenance", {})
    return (
        provenance.get("source") == "review_server"
        and provenance.get("route") == expected_route
        and bool(provenance.get("session_id"))
        and bool(provenance.get("submitted_at"))
        and provenance.get("approval_key_verified") is True
        and provenance.get("approval_key_required") is True
    )


def load_visual_feedback_for_batch(root, batch_id):
    internal = root / INTERNAL
    candidates = []
    if batch_id:
        candidates.append(internal / "05_review" / "batches" / f"{batch_id}.json")
    candidates.append(internal / "05_review" / "feedback.json")
    for path in candidates:
        data = load_json(path, {})
        if not data:
            continue
        if batch_id and data.get("batch_id") != batch_id:
            continue
        return data
    return {}


def validation_report_by_page(root, keys):
    validation = load_json(root / INTERNAL / "04_validation" / "validation_summary.json", {})
    reports = validation.get("reports", [])
    by_page = {}
    for report in reports:
        stem = Path(report.get("file", "")).stem
        for key in keys:
            if stem == key or stem.startswith(key):
                by_page[key] = report
                break
    return validation, by_page


def report_has_error(report):
    if report.get("status") == "fail":
        return True
    summary = report.get("summary", {})
    if isinstance(summary, dict) and summary.get("errors", 0):
        return True
    return any(isinstance(i, dict) and i.get("severity") == "error" for i in report.get("issues", []))


def report_has_blocking_warning(report):
    for issue in report.get("issues", []):
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") == "warning" and issue.get("code") in BLOCKING_WARNING_CODES:
            return True
    return False


def derive(root):
    internal = root / INTERNAL
    content = load_json(internal / "01_content" / "page_content.json", {})
    plan = load_json(internal / "01_layout_plan" / "layout_plan.json", {})
    manifest_data = manifest(root)

    content_keys = page_keys(content)
    manifest_keys = page_keys(manifest_data)
    content_ready = bool(content_keys) and content_keys == manifest_keys

    layout_html = root / "01_layout_direction.html"
    capacity_report = internal / "01_layout_plan" / "layout_capacity_report.json"
    plan_ready = content_ready and bool(page_keys(plan)) and capacity_report.exists() and layout_html.exists()

    layout_feedback = load_json(internal / "01_layout_plan" / "layout_feedback.json", {})
    layout_approved = (
        plan_ready
        and layout_feedback.get("all_approved") is True
        and has_review_server_provenance(layout_feedback, "/layout-feedback")
    )

    batch_id, keys = first_open_batch(manifest_data)
    future_keys = future_pages(manifest_data, batch_id) if batch_id else []
    by_key = {p.get("page_key"): p for p in manifest_data.get("pages", []) if isinstance(p, dict)}

    svg_ready = bool(keys) and all((root / by_key.get(k, {}).get("svg_path", "")).exists() for k in keys)
    png_ready = bool(keys) and all((root / by_key.get(k, {}).get("png_path", "")).exists() for k in keys)

    validation, reports = validation_report_by_page(root, keys)
    validation_ready = bool(keys) and all(k in reports for k in keys)
    validation_blocked = any(report_has_error(r) or report_has_blocking_warning(r) for r in reports.values())
    validation_passed = validation_ready and not validation_blocked
    self_review = load_json(internal / "04_validation" / "self_review.json", {})
    self_review_ready = bool(keys) and (
        self_review.get("vision_available") is False
        or all(k in self_review.get("pages", {}) for k in keys)
    )
    preview_ready = validation_passed and png_ready and self_review_ready

    review_html = root / "02_visual_review.html"
    review_ready = preview_ready and review_html.exists()

    feedback = load_visual_feedback_for_batch(root, batch_id) if batch_id else {}
    pages_feedback = feedback.get("pages", {})
    visual_feedback_has_provenance = (
        feedback.get("all_approved") is True
        and (not batch_id or feedback.get("batch_id") == batch_id)
        and has_review_server_provenance(feedback, "/review-feedback")
    )
    current_batch_feedback_approved = (
        review_ready
        and visual_feedback_has_provenance
        and all(pages_feedback.get(k, {}).get("approved") for k in keys)
    )
    current_batch_manifest_approved = (
        bool(keys)
        and all(
            by_key.get(k, {}).get("visual_approved")
            and by_key.get(k, {}).get("export_allowed")
            for k in keys
        )
        and manifest_data.get("batch_config", {}).get(batch_id, {}).get("status") == "visual_approved"
    )

    all_pages = manifest_data.get("pages", [])
    all_pages_visual_approved = bool(all_pages) and all(
        p.get("visual_approved") and p.get("export_allowed")
        for p in all_pages
    )
    all_svg_ready = bool(all_pages) and all((root / p.get("svg_path", "")).exists() for p in all_pages)
    all_png_ready = bool(all_pages) and all((root / p.get("png_path", "")).exists() for p in all_pages)
    all_validation_ready = bool(all_pages) and all(
        p.get("validation_status") not in ("fail", "not_validated", "", None)
        for p in all_pages
    )
    all_batch_feedback_approved = True
    for bid, batch_keys in batches(manifest_data):
        batch_feedback = load_visual_feedback_for_batch(root, bid)
        batch_pages_feedback = batch_feedback.get("pages", {})
        if not (
            batch_feedback.get("all_approved") is True
            and batch_feedback.get("batch_id") == bid
            and has_review_server_provenance(batch_feedback, "/review-feedback")
            and all(batch_pages_feedback.get(k, {}).get("approved") for k in batch_keys)
        ):
            all_batch_feedback_approved = False
            break

    export_ready = layout_approved and all_batch_feedback_approved and bool(all_pages) and all(
        p.get("layout_approved")
        and p.get("visual_approved")
        and p.get("export_allowed")
        and p.get("validation_status") not in ("fail", "not_validated", "", None)
        and (root / p.get("svg_path", "")).exists()
        and (root / p.get("png_path", "")).exists()
        for p in all_pages
    )

    no_open_batch = bool(all_pages) and not batch_id and not keys

    if export_ready:
        state = "EXPORT"
        next_action = "所有页面已通过审阅。只能运行 pptflow.py export 导出 PPT，不要直接运行 native_svg_to_ppt.py。"
    elif no_open_batch:
        state = "EXPORT_FIX"
        next_action = "所有批次已结束，但仍未满足导出条件；运行 pipeline_gate.py export-ready 查看阻断项。"
    elif not content_ready:
        state = "CONTENT"
        next_action = "整理源文案，写入 _internal/01_content/page_content.json，并建立 page_manifest.json 页面清单。"
    elif not plan_ready:
        state = "PLAN"
        next_action = "生成 _internal/01_layout_plan/layout_plan.json，运行 estimate_layout_capacity.py 生成容量预检，再运行 generate_layout_html.py 生成 01_layout_direction.html。"
    elif not layout_approved:
        state = "PLAN_REVIEW"
        next_action = "启动 review_server.py，让用户通过浏览器提交版式反馈；不要手写 layout_feedback.json。"
    elif not svg_ready:
        state = "DRAFT"
        next_action = (
            f"当前批次：{batch_id}\n"
            f"允许生成 SVG 的页面：{', '.join(keys)}\n"
            f"禁止提前生成的后续页面：{', '.join(future_keys) if future_keys else '无'}\n"
            "只生成当前批次 SVG。提前生成后续批次不是加速，而是流程违规。"
        )
    elif not preview_ready:
        if not png_ready:
            state = "DRAFT_RENDER"
            next_action = (
                f"当前批次：{batch_id}\n"
                f"允许渲染 PNG 的页面：{', '.join(keys)}\n"
                f"禁止提前渲染的后续页面：{', '.join(future_keys) if future_keys else '无'}\n"
                f"先运行 render_svg_png.py 渲染当前批次 PNG：--manifest _internal/00_project/page_manifest.json --batch {batch_id}。\n"
                f"随后运行 validate_svg_layout.py，并结合 PNG 写入/更新 self_review.json。"
            )
        else:
            state = "DRAFT_FIX"
            next_action = (
                f"当前批次：{batch_id}\n"
                f"结合当前批次 PNG、validate_svg_layout.py 输出和 self_review.json 修正页面：{', '.join(keys)}。\n"
                f"修到没有 validation error / blocker-class warning，且 self_review 无 required_fixes 后，运行 pipeline_gate.py preview-ready --batch {batch_id}。"
            )
    elif not review_ready:
        state = "REVIEW"
        next_action = f"运行 generate_review_html.py --batch {batch_id} 生成视觉审阅页。"
    elif not current_batch_feedback_approved:
        state = "VISUAL_REVIEW"
        next_action = "让用户通过 review_server.py 的 /review 提交视觉反馈；未批准则回到 DRAFT 修正。"
    elif not current_batch_manifest_approved:
        state = "VISUAL_GATE"
        next_action = (
            f"当前批次 {batch_id} 已收到可信视觉反馈，但 manifest 尚未更新。\n"
            f"必须运行 pipeline_gate.py <project_dir> visual-approved --batch {batch_id}，"
            "由 gate 写入 visual_approved/export_allowed 后，才能开始下一批。"
        )
    elif not export_ready:
        state = "NEXT_BATCH"
        next_action = "当前批次已批准。运行 pptflow.py next 确认下一批；不要手动改 manifest 状态。"
    else:
        state = "EXPORT_FIX"
        next_action = "流程状态不一致；运行 pipeline_gate.py export-ready 查看阻断项。"

    display_svg_ready = svg_ready if keys else all_svg_ready
    display_png_ready = png_ready if keys else all_png_ready
    display_validation_ready = validation_ready if keys else all_validation_ready
    display_validation_passed = validation_passed if keys else all_validation_ready and not validation_blocked
    display_self_review_ready = self_review_ready if keys else all_pages_visual_approved
    display_preview_ready = preview_ready if keys else export_ready
    display_review_ready = review_ready if keys else export_ready

    return {
        "state": state,
        "next_action": next_action,
        "current_batch": batch_id,
        "current_pages": keys,
        "future_pages_forbidden": future_keys,
        "checks": {
            "content_ready": content_ready,
            "plan_ready": plan_ready,
            "layout_approved_by_server": layout_approved,
            "svg_ready": display_svg_ready,
            "png_ready": display_png_ready,
            "validation_ready": display_validation_ready,
            "all_svg_ready": all_svg_ready,
            "all_png_ready": all_png_ready,
            "all_validation_ready": all_validation_ready,
            "validation_blocked": validation_blocked,
            "validation_passed": display_validation_passed,
            "self_review_ready": display_self_review_ready,
            "preview_ready": display_preview_ready,
            "review_ready": display_review_ready,
            "visual_approved_by_server": (
                current_batch_manifest_approved
                if keys
                else all_pages_visual_approved and all_batch_feedback_approved
            ),
            "all_pages_visual_approved": all_pages_visual_approved,
            "visual_feedback_has_provenance": visual_feedback_has_provenance,
            "all_batch_feedback_approved": all_batch_feedback_approved,
            "export_ready": export_ready,
            "validation_status": validation.get("status", ""),
        },
    }


def cmd_status(root):
    state = derive(root)
    write_json(root / STATE_PATH, state)
    append_event(root, "status", {"state": state["state"], "current_batch": state["current_batch"]})
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_next(root):
    state = derive(root)
    write_json(root / STATE_PATH, state)
    append_event(root, "next", {"state": state["state"], "next_action": state["next_action"]})
    print(state["next_action"])


def cmd_hash(root):
    files = {
        "layout_html": root / "01_layout_direction.html",
        "review_html": root / "02_visual_review.html",
        "page_manifest": root / INTERNAL / "00_project" / "page_manifest.json",
        "validation": root / INTERNAL / "04_validation" / "validation_summary.json",
    }
    data = {name: sha256_file(path) for name, path in files.items()}
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_export(root):
    state = derive(root)
    if not state.get("checks", {}).get("export_ready"):
        print("EXPORT BLOCKED: current flow state is not export-ready.", file=sys.stderr)
        print(state.get("next_action", "Run pptflow.py status for details."), file=sys.stderr)
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    gate_script = script_dir / "pipeline_gate.py"
    convert_script = script_dir / "native_svg_to_ppt.py"

    subprocess.run(
        [sys.executable, str(gate_script), str(root), "export-ready"],
        check=True,
    )

    manifest_data = manifest(root)
    svg_files = []
    for page in manifest_data.get("pages", []):
        svg_path = page.get("svg_path", "")
        if svg_path:
            svg_files.append(str(root / svg_path))

    if not svg_files:
        print("EXPORT BLOCKED: no SVG files listed in page_manifest.json.", file=sys.stderr)
        sys.exit(1)

    output_dir = root / INTERNAL / "06_ppt_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Final user-facing deliverable belongs at project root; _internal keeps
    # conversion reports and process artifacts only.
    output_path = root / "final_deck.pptx"
    report_path = output_dir / "ppt_conversion_report.json"

    env = os.environ.copy()
    env["SMART_SVG_EXPORT_APPROVED_BY_PPTFLOW"] = "1"
    cmd = [
        sys.executable,
        str(convert_script),
        *svg_files,
        "-o",
        str(output_path),
        "--report",
        str(report_path),
        "--auto-size",
        "--match-aspect",
    ]
    notes_path = root / INTERNAL / "00_project" / "notes.json"
    if notes_path.exists():
        cmd.extend(["--notes", str(notes_path)])

    subprocess.run(cmd, check=True, env=env)
    append_event(root, "export", {"output": str(output_path.relative_to(root)), "pages": len(svg_files)})
    print(f"EXPORT COMPLETE: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="可信状态控制器：查看 Planner's PPT Hell 当前状态、下一步与受控导出。")
    parser.add_argument("project_dir")
    parser.add_argument("command", choices=["status", "next", "hash", "export"])
    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    if args.command == "status":
        cmd_status(root)
    elif args.command == "next":
        cmd_next(root)
    elif args.command == "hash":
        cmd_hash(root)
    elif args.command == "export":
        cmd_export(root)


if __name__ == "__main__":
    main()
