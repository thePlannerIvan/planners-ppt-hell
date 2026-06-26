"""
Pipeline gate enforcer for Planner's PPT Hell.

Blocks phase transitions when preconditions are not met. Each gate checks
specific files and states; exits 0 on pass, 1 on failure with a clear message.

Usage:
  python pipeline_gate.py <project_dir> <gate> [--batch BATCH_ID]

Gates:
  layout-ready        Content, layout, manifest contracts are valid; layout HTML exists
  layout-approved     Layout feedback exists and all/batch pages approved
  batch-svg-ready     SVG exists for all pages in the specified batch
  validation-passed   Legacy/static check: validation_summary.json exists, no errors or blocker-class warnings (requires --batch)
  preview-ready       PNG previews exist, validation has no blockers, and visual self-review is complete (requires --batch)
  visual-approved     Visual review HTML exists, feedback submitted and approved (requires --batch)
  export-ready        All pages generated, validated, approved; no blockers remain
"""

import argparse
import json
import sys
from pathlib import Path

VALID_BATCH_STATUSES = {
    "planned",
    "layout_approved",
    "svg_generated",
    "validation_passed",
    "preview_ready",
    "visual_approved",
}

BLOCKING_WARNING_CODES = {
    "TEXT_OVERFLOW_MAJOR",
    "FOOTER_ZONE_INVASION",
}


def load_json(path):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None
    return None


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fail(msg):
    print(f"GATE FAILED: {msg}")
    sys.exit(1)


def ok(msg):
    print(f"GATE PASSED: {msg}")
    sys.exit(0)


def _manifest_path(internal):
    return internal / "00_project" / "page_manifest.json"


def _load_manifest(internal):
    manifest = load_json(_manifest_path(internal))
    if not manifest:
        fail("page_manifest.json not found or invalid")
    return manifest


def _manifest_by_key(manifest):
    return {
        p.get("page_key"): p
        for p in manifest.get("pages", [])
        if isinstance(p, dict) and p.get("page_key")
    }


def _get_batch_pages(manifest, batch_id):
    batch_config = manifest.get("batch_config", {})
    if not isinstance(batch_config, dict):
        fail("page_manifest.json batch_config must be an object")

    if batch_id not in batch_config:
        fail(f"batch '{batch_id}' not found in page_manifest.json")

    batch = batch_config.get(batch_id)
    if not isinstance(batch, dict):
        fail(
            f"page_manifest.json batch_config.{batch_id} must be an object with "
            "'status' and 'pages'. List-style batches are not supported."
        )

    status = batch.get("status")
    if status not in VALID_BATCH_STATUSES:
        fail(
            f"page_manifest.json batch_config.{batch_id}.status must be one of "
            f"{sorted(VALID_BATCH_STATUSES)}, got {status!r}"
        )

    pages = batch.get("pages")
    if not isinstance(pages, list) or not pages:
        fail(f"page_manifest.json batch_config.{batch_id}.pages must be a non-empty list")

    known_pages = set(_manifest_by_key(manifest))
    unknown = [pk for pk in pages if pk not in known_pages]
    if unknown:
        fail(f"page_manifest.json batch_config.{batch_id}.pages references unknown page(s): {unknown}")

    return pages


def _set_batch_status(manifest, batch_id, status):
    if batch_id and isinstance(manifest.get("batch_config"), dict):
        batch = manifest["batch_config"].get(batch_id)
        if isinstance(batch, dict):
            batch["status"] = status


def _save_manifest(internal, manifest):
    save_json(_manifest_path(internal), manifest)


def _batch_order(manifest):
    batch_config = manifest.get("batch_config", {})
    if not isinstance(batch_config, dict):
        return []
    return sorted(batch_config.keys())


def _future_batch_pages(manifest, batch_id):
    future = []
    ids = _batch_order(manifest)
    if batch_id not in ids:
        return future
    for bid in ids[ids.index(batch_id) + 1:]:
        future.extend(_get_batch_pages(manifest, bid))
    return future


def _validation_report_page_key(report, page_keys):
    stem = Path(report.get("file", "")).stem
    for pk in page_keys:
        if stem == pk or stem.startswith(pk):
            return pk
    return ""


def _fail_if_future_artifacts(root, internal, manifest, batch_id, artifact_types):
    """Block current-batch gates if future batch artifacts already exist.

    Future pages must wait for prior visual review, because later page design
    should incorporate feedback from the current batch.
    """
    future_pages = _future_batch_pages(manifest, batch_id)
    if not future_pages:
        return

    manifest_by_key = _manifest_by_key(manifest)
    found = []

    if "svg" in artifact_types:
        for pk in future_pages:
            svg_path = manifest_by_key.get(pk, {}).get("svg_path", "")
            if svg_path and (root / svg_path).exists():
                found.append(f"{pk}: future SVG exists at {svg_path}")

    if "png" in artifact_types:
        for pk in future_pages:
            png_path = manifest_by_key.get(pk, {}).get("png_path", "")
            if png_path and (root / png_path).exists():
                found.append(f"{pk}: future PNG exists at {png_path}")

    if "validation" in artifact_types:
        validation = load_json(internal / "04_validation" / "validation_summary.json") or {}
        for report in validation.get("reports", []):
            pk = _validation_report_page_key(report, future_pages)
            if pk:
                found.append(f"{pk}: future validation report exists")

    if "self_review" in artifact_types:
        sr = load_json(internal / "04_validation" / "self_review.json") or {}
        sr_pages = sr.get("pages", {}) if isinstance(sr, dict) else {}
        for pk in future_pages:
            if pk in sr_pages:
                found.append(f"{pk}: future self_review entry exists")

    if found:
        fail(
            f"Future batch artifacts found while processing '{batch_id}'. "
            "Only the current batch may be generated; later batches must wait "
            "until this batch is visually approved.\n  - " + "\n  - ".join(found)
        )


def _report_has_error(report):
    if report.get("status") == "fail":
        return True
    summary = report.get("summary", {})
    if isinstance(summary, dict) and summary.get("errors", 0):
        return True
    for issue in report.get("issues", []):
        if isinstance(issue, dict) and issue.get("severity") == "error":
            return True
    return False


def _report_has_blocking_warning(report):
    for issue in report.get("issues", []):
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") == "warning" and issue.get("code") in BLOCKING_WARNING_CODES:
            return True
    return False


def _report_warning_count(report):
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    try:
        return int(summary.get("warnings", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _require_review_server_provenance(data, route, label):
    provenance = data.get("provenance", {})
    missing = []
    if provenance.get("source") != "review_server":
        missing.append("provenance.source=review_server")
    if provenance.get("route") != route:
        missing.append(f"provenance.route={route}")
    if not provenance.get("session_id"):
        missing.append("provenance.session_id")
    if not provenance.get("submitted_at"):
        missing.append("provenance.submitted_at")
    if not provenance.get("html_sha256"):
        missing.append("provenance.html_sha256")
    if provenance.get("approval_key_verified") is not True:
        missing.append("provenance.approval_key_verified=true")
    if provenance.get("approval_key_required") is not True:
        missing.append("provenance.approval_key_required=true")
    if missing:
        fail(
            f"{label} was not submitted through review_server.py; missing "
            + ", ".join(missing)
        )


def _load_visual_feedback_for_batch(internal, batch_id):
    candidates = []
    if batch_id:
        candidates.append(internal / "05_review" / "batches" / f"{batch_id}.json")
    candidates.append(internal / "05_review" / "feedback.json")

    for path in candidates:
        if not path.exists():
            continue
        fb = load_json(path)
        if not fb:
            continue
        if batch_id and fb.get("batch_id") != batch_id:
            continue
        return fb, path
    return None, None


def _require_visual_feedback_for_batch(internal, batch_id):
    fb, path = _load_visual_feedback_for_batch(internal, batch_id)
    if not fb:
        expected = f"_internal/05_review/batches/{batch_id}.json"
        fail(f"{expected} not found — submit visual review feedback for batch '{batch_id}' via review server first")
    _require_review_server_provenance(fb, "/review-feedback", str(path))
    if fb.get("batch_id") != batch_id:
        fail(f"{path}: batch_id must be '{batch_id}', got {fb.get('batch_id')!r}")
    if fb.get("all_approved") is not True:
        fail(f"{path}: batch '{batch_id}' is not fully approved")
    return fb, path


def _prior_rejected_feedback_exists(internal, batch_id):
    fb, _ = _load_visual_feedback_for_batch(internal, batch_id)
    if not fb or fb.get("batch_id") != batch_id:
        return False
    if fb.get("all_approved") is True:
        return False
    pages = fb.get("pages", {})
    return any(isinstance(v, dict) and not v.get("approved") for v in pages.values())


def _require_revision_notes_for_rework(internal, batch_id, batch_pages):
    if not _prior_rejected_feedback_exists(internal, batch_id):
        return
    notes_path = internal / "05_review" / "revision_notes.json"
    notes = load_json(notes_path)
    if not notes:
        fail(
            "_internal/05_review/revision_notes.json is required after rejected visual feedback "
            f"before regenerating review for batch '{batch_id}'"
        )
    pages = notes.get("pages", {})
    missing = [pk for pk in batch_pages if pk not in pages]
    if missing:
        fail("revision_notes.json missing current batch page(s): " + ", ".join(missing))


def _require_integrated_review(internal, batch_id, batch_pages):
    review_path = internal / "04_validation" / "integrated_review.json"
    review = load_json(review_path)
    if not review:
        fail(
            "_internal/04_validation/integrated_review.json not found — combine validator findings "
            "and PNG visual review before deciding whether to revise SVG"
        )
    if review.get("batch_id") != batch_id:
        fail(f"integrated_review.json batch_id must be '{batch_id}', got {review.get('batch_id')!r}")
    pages = review.get("pages", {})
    if not isinstance(pages, dict):
        fail("integrated_review.json pages must be an object")
    missing = [pk for pk in batch_pages if pk not in pages]
    if missing:
        fail("integrated_review.json missing current batch page(s): " + ", ".join(missing))
    unresolved = []
    for pk in batch_pages:
        page = pages.get(pk, {})
        if not str(page.get("decision", "")).strip():
            unresolved.append(f"{pk}: decision is required")
        must_fix = page.get("must_fix", [])
        if must_fix:
            unresolved.append(f"{pk}: unresolved must_fix item(s) remain")
    if unresolved:
        fail("Integrated review is not clean:\n  - " + "\n  - ".join(unresolved))


def gate_layout_ready(root, internal):
    """Check that contracts are valid and layout HTML exists."""
    # 1. All three contract files must exist
    content_path = internal / "01_content" / "page_content.json"
    layout_path = internal / "01_layout_plan" / "layout_plan.json"
    capacity_path = internal / "01_layout_plan" / "layout_capacity_report.json"
    manifest_path = internal / "00_project" / "page_manifest.json"

    for label, p in [("page_content.json", content_path),
                      ("layout_plan.json", layout_path),
                      ("layout_capacity_report.json", capacity_path),
                      ("page_manifest.json", manifest_path)]:
        if not p.exists():
            fail(f"{label} not found at {p}")

    # 2. Contracts must be valid JSON and have pages
    content = load_json(content_path)
    layout = load_json(layout_path)
    capacity = load_json(capacity_path)
    manifest = load_json(manifest_path)

    if not content or "pages" not in content:
        fail("page_content.json is invalid or missing 'pages' array")
    if not layout or "pages" not in layout:
        fail("layout_plan.json is invalid or missing 'pages' array")
    if not capacity or "pages" not in capacity:
        fail("layout_capacity_report.json is invalid or missing 'pages' object")
    if not manifest or "pages" not in manifest:
        fail("page_manifest.json is invalid or missing 'pages' array")

    # 3. Cross-validate that every layout page_key exists in content
    content_keys = {p.get("page_key") for p in content["pages"] if isinstance(p, dict)}
    layout_keys = {p.get("page_key") for p in layout["pages"] if isinstance(p, dict)}
    capacity_keys = set(capacity.get("pages", {}).keys())
    orphan_layout = layout_keys - content_keys
    if orphan_layout:
        fail(f"layout_plan.json page_keys not in page_content.json: {sorted(orphan_layout)}")
    missing_capacity = layout_keys - capacity_keys
    if missing_capacity:
        fail(f"layout_capacity_report.json missing page_keys: {sorted(missing_capacity)}")

    # 4. Every page must have non-empty wireframe and copy_handling
    for p in layout["pages"]:
        pk = p.get("page_key", "?")
        if not p.get("wireframe"):
            fail(f"{pk}: wireframe is empty or missing")
        ch = p.get("copy_handling", {})
        if not isinstance(ch, dict) or not ch.get("kept_on_slide"):
            fail(f"{pk}: copy_handling.kept_on_slide is missing or empty")
        final_copy = ch.get("final_on_slide") if isinstance(ch, dict) else None
        if not isinstance(final_copy, dict):
            fail(f"{pk}: copy_handling.final_on_slide is missing")
        if not str(final_copy.get("title", "")).strip():
            fail(f"{pk}: copy_handling.final_on_slide.title is missing")
        body = final_copy.get("body", [])
        has_body = (isinstance(body, list) and any(str(x).strip() for x in body)) or (
            isinstance(body, str) and body.strip()
        )
        has_subtitle = bool(str(final_copy.get("subtitle", "")).strip())
        has_footer = bool(str(final_copy.get("footer_takeaway", "")).strip())
        if not (has_body or has_subtitle or has_footer):
            fail(f"{pk}: final_on_slide must include body, subtitle, or footer_takeaway")
        rationale = ch.get("compression_rationale", []) if isinstance(ch, dict) else []
        if not isinstance(rationale, list) or not any(str(x).strip() for x in rationale):
            fail(f"{pk}: copy_handling.compression_rationale is missing or empty")

    # 5. Every content page must have full copy
    for p in content["pages"]:
        pk = p.get("page_key", "?")
        if not p.get("action_title", "").strip():
            fail(f"{pk}: action_title is empty")
        if not p.get("core_message", "").strip():
            fail(f"{pk}: core_message is empty")
        if not p.get("body_blocks"):
            fail(f"{pk}: body_blocks is empty")

    # 6. 01_layout_direction.html must exist
    layout_html = root / "01_layout_direction.html"
    if not layout_html.exists():
        fail("01_layout_direction.html not found — run generate_layout_html.py first")

    ok("All contracts valid, layout direction HTML exists")


def gate_layout_approved(root, internal, batch_id=None):
    """Check that layout feedback exists and relevant pages are approved."""
    feedback_path = internal / "01_layout_plan" / "layout_feedback.json"
    if not feedback_path.exists():
        fail("layout_feedback.json not found — submit layout feedback via review server first")

    fb = load_json(feedback_path)
    if not fb:
        fail("layout_feedback.json is invalid")
    _require_review_server_provenance(fb, "/layout-feedback", "layout_feedback.json")

    pages_fb = fb.get("pages", {})
    if not pages_fb:
        fail("layout_feedback.json has no page feedback entries")

    # If batch specified, only check those pages
    if batch_id:
        manifest = _load_manifest(internal)
        batch_pages = _get_batch_pages(manifest, batch_id)
        manifest_by_key = _manifest_by_key(manifest)
        for pk in batch_pages:
            page_fb = pages_fb.get(pk, {})
            if not page_fb.get("approved"):
                fail(f"{pk}: not approved in layout feedback")
            manifest_by_key[pk]["layout_approved"] = True
        _set_batch_status(manifest, batch_id, "layout_approved")
        _save_manifest(internal, manifest)
        ok(f"Batch '{batch_id}' layout approved")
    else:
        # Check all pages
        if not fb.get("all_approved"):
            unapproved = [pk for pk, p in pages_fb.items() if not p.get("approved")]
            if unapproved:
                fail(f"Not all pages approved: {unapproved}")
        manifest = _load_manifest(internal)
        manifest_by_key = _manifest_by_key(manifest)
        for pk, page_fb in pages_fb.items():
            if page_fb.get("approved") and pk in manifest_by_key:
                manifest_by_key[pk]["layout_approved"] = True
        _save_manifest(internal, manifest)
        ok("All pages layout approved")


def _enforce_batch_discipline(manifest, batch_id):
    """Check batch size limits and sequential batch ordering."""
    batch_config = manifest.get("batch_config", {})
    configured_size = manifest.get("batch_size", 3)
    batch = batch_config.get(batch_id, {})
    override = batch.get("batch_size_override") if isinstance(batch, dict) else None
    if isinstance(override, int) and override > 0:
        configured_size = override
    batch_pages = _get_batch_pages(manifest, batch_id)

    # 1. Batch cannot exceed configured batch_size
    if len(batch_pages) > configured_size:
        fail(
            f"Batch '{batch_id}' has {len(batch_pages)} pages, "
            f"exceeding configured batch_size ({configured_size}). "
            f"Either reduce the batch, update batch_size, or set an explicit "
            f"batch_size_override for this batch in page_manifest.json."
        )

    # 2. Previous batch must be fully approved before starting next batch SVG gen
    batch_ids = sorted(batch_config.keys())
    if batch_id in batch_ids:
        idx = batch_ids.index(batch_id)
        if idx > 0:
            prev_batch_id = batch_ids[idx - 1]
            prev_pages = _get_batch_pages(manifest, prev_batch_id)

            pages_list = manifest.get("pages", [])
            manifest_by_key = {p.get("page_key"): p for p in pages_list if isinstance(p, dict)}

            # Check if all previous batch pages are visually approved
            prev_unapproved = []
            for pk in prev_pages:
                mp = manifest_by_key.get(pk, {})
                if not mp.get("visual_approved"):
                    prev_unapproved.append(pk)

            if prev_unapproved:
                fail(
                    f"Cannot start batch '{batch_id}' — previous batch '{prev_batch_id}' "
                    f"still has unapproved pages: {prev_unapproved}"
                )

    return batch_pages


def gate_batch_svg_ready(root, internal, batch_id):
    """Check that SVG files exist for all pages in the batch."""
    if not batch_id:
        fail("--batch is required for batch-svg-ready gate")

    manifest = _load_manifest(internal)

    batch_pages = _enforce_batch_discipline(manifest, batch_id)
    _fail_if_future_artifacts(root, internal, manifest, batch_id, {"svg", "png", "validation", "self_review"})
    if not batch_pages:
        fail(f"batch '{batch_id}' has no pages defined")

    pages_list = manifest.get("pages", [])
    manifest_by_key = {p.get("page_key"): p for p in pages_list if isinstance(p, dict)}

    unapproved_layout = [
        pk for pk in batch_pages
        if not manifest_by_key.get(pk, {}).get("layout_approved")
    ]
    if unapproved_layout:
        fail(
            f"Cannot mark batch '{batch_id}' SVG-ready — layout is not approved for: "
            f"{unapproved_layout}"
        )

    missing = []
    for pk in batch_pages:
        mp = manifest_by_key.get(pk, {})
        svg_path = mp.get("svg_path", "")
        if not svg_path:
            missing.append(f"{pk}: no svg_path in manifest")
            continue
        svg_file = root / svg_path
        if not svg_file.exists():
            missing.append(f"{pk}: SVG not found at {svg_path}")

    if missing:
        fail(f"Missing SVG files:\n  " + "\n  ".join(missing))

    _set_batch_status(manifest, batch_id, "svg_generated")
    _save_manifest(internal, manifest)
    ok(f"Batch '{batch_id}': all {len(batch_pages)} SVG(s) exist")


def gate_validation_passed(root, internal, batch_id=None):
    """Check that static SVG validation has been run and no blockers exist."""
    if not batch_id:
        fail("--batch is required for validation-passed gate")
    validation_path = internal / "04_validation" / "validation_summary.json"
    if not validation_path.exists():
        fail("validation_summary.json not found — run validate_svg_layout.py first")

    val = load_json(validation_path)
    if not val:
        fail("validation_summary.json is invalid")

    # Load manifest to determine which pages to check
    manifest = _load_manifest(internal)

    # Determine batch pages if --batch specified
    batch_pages = None
    if batch_id:
        batch_pages = _get_batch_pages(manifest, batch_id)
        _fail_if_future_artifacts(root, internal, manifest, batch_id, {"svg", "png", "validation", "self_review"})

    # Check aggregate validation status only when validating all pages.
    if not batch_pages and val.get("status") == "fail":
        summary = val.get("summary", {})
        fail(f"Validation has {summary.get('errors', '?')} error(s) — fix P0 blockers first")

    # Check per-report status — scope to batch if provided
    reports = val.get("reports", [])
    manifest_pages = manifest.get("pages", [])
    manifest_by_key = {p.get("page_key"): p for p in manifest_pages if isinstance(p, dict)}

    pages_to_check = batch_pages if batch_pages else [p.get("page_key") for p in manifest_pages]
    report_by_key = {}
    for r in reports:
        r_file = Path(r.get("file", "")).stem
        for pk in pages_to_check:
            if r_file == pk or r_file.startswith(pk):
                report_by_key[pk] = r
                break

    missing_reports = [pk for pk in pages_to_check if pk not in report_by_key]
    if missing_reports:
        fail("Missing validation report for page(s): " + ", ".join(missing_reports))

    for r in reports:
        if _report_has_error(r):
            r_file = Path(r.get("file", "")).stem
            if batch_pages:
                for pk in batch_pages:
                    if pk in r_file or r_file in pk:
                        fail(f"{r.get('file', '?')}: validation has error-level issue(s)")
                        break
                # Report not in batch — skip
            else:
                fail(f"{r.get('file', '?')}: validation has error-level issue(s)")

        if _report_has_blocking_warning(r):
            r_file = Path(r.get("file", "")).stem
            if batch_pages:
                for pk in batch_pages:
                    if pk in r_file or r_file in pk:
                        fail(f"{r.get('file', '?')}: validation has blocking warning(s)")
                        break
            else:
                fail(f"{r.get('file', '?')}: validation has blocking warning(s)")

    for pk in pages_to_check:
        svg_path = manifest_by_key.get(pk, {}).get("svg_path", "")
        if not svg_path:
            fail(f"{pk}: svg_path not set in manifest")
        if not (root / svg_path).exists():
            fail(f"{pk}: SVG not found at {svg_path}")

    for pk in pages_to_check:
        manifest_by_key[pk]["validation_status"] = report_by_key[pk].get("status", "pass")
    if batch_id:
        _set_batch_status(manifest, batch_id, "validation_passed")
    _save_manifest(internal, manifest)
    ok("Validation passed — static SVG checks have no blockers")


def gate_preview_ready(root, internal, batch_id=None, allow_vision_unavailable=False):
    """Check that PNG previews exist, validation has no blockers, and model self-review has no blockers."""
    if not batch_id:
        fail("--batch is required for preview-ready gate")

    manifest = _load_manifest(internal)
    batch_pages = _get_batch_pages(manifest, batch_id)
    _fail_if_future_artifacts(root, internal, manifest, batch_id, {"svg", "png", "validation", "self_review"})
    _require_revision_notes_for_rework(internal, batch_id, batch_pages)

    manifest_pages = manifest.get("pages", [])
    manifest_by_key = {p.get("page_key"): p for p in manifest_pages if isinstance(p, dict)}

    validation_path = internal / "04_validation" / "validation_summary.json"
    if not validation_path.exists():
        fail("validation_summary.json not found — run validate_svg_layout.py after rendering PNG previews")

    val = load_json(validation_path)
    if not val:
        fail("validation_summary.json is invalid")

    reports = val.get("reports", [])
    report_by_key = {}
    for r in reports:
        r_file = Path(r.get("file", "")).stem
        for pk in batch_pages:
            if r_file == pk or r_file.startswith(pk):
                report_by_key[pk] = r
                break

    missing_reports = [pk for pk in batch_pages if pk not in report_by_key]
    if missing_reports:
        fail("Missing validation report for page(s): " + ", ".join(missing_reports))

    validation_blockers = []
    for pk in batch_pages:
        report = report_by_key[pk]
        if _report_has_error(report):
            validation_blockers.append(f"{pk}: validation has error-level issue(s)")
        elif _report_has_blocking_warning(report):
            validation_blockers.append(f"{pk}: validation has blocker-class warning(s)")

    if validation_blockers:
        fail(
            "Validation blockers must be resolved before user visual review:\n  - "
            + "\n  - ".join(validation_blockers)
        )

    for pk in batch_pages:
        mp = manifest_by_key.get(pk, {})
        png_path = mp.get("png_path", "")
        if not png_path:
            fail(f"{pk}: png_path not set in manifest")
        png_file = root / png_path
        if not png_file.exists():
            fail(f"{pk}: PNG preview not found at {png_path}")

    _require_integrated_review(internal, batch_id, batch_pages)

    # Check self-review exists. Vision-unavailable mode is an explicit exception,
    # not the default path for multimodal models.
    self_review_path = internal / "04_validation" / "self_review.json"
    if not self_review_path.exists():
        fail("self_review.json not found — model visual self-review is required before user visual review")

    sr = load_json(self_review_path)
    if not sr:
        fail("self_review.json is invalid")

    vision_available = sr.get("vision_available", True)
    if not vision_available:
        if not allow_vision_unavailable:
            fail(
                "vision_available is false, but preview-ready requires real PNG visual self-review by default. "
                "If the runtime truly cannot inspect images, rerun with --allow-vision-unavailable; do not use this for multimodal models."
            )
        if sr.get("human_review_required") is not True:
            fail("vision_available is false, so self_review.human_review_required must be true")
        if not str(sr.get("vision_unavailable_reason", "")).strip():
            fail("vision_available is false, so self_review.vision_unavailable_reason is required")
        if sr.get("pages"):
            fail("vision_available is false, so self_review.pages must be empty; do not write visual verdicts without vision")
        print("NOTE: vision_available is false — visual checks deferred to human review")

    # Check for pages with visual_status 'blocked' or required_fixes — scope to batch.
    # If vision is unavailable, self-review is advisory only; human review becomes the visual gate.
    if vision_available:
        if not str(sr.get("vision_check_method", "")).strip():
            fail("self_review.vision_check_method is required when vision_available is true")
        sr_pages = sr.get("pages", {})
        blocking = []
        pages_with_fixes = []
        validator_pages_missing = []
        png_review_missing = []
        warnings_need_revision_pass = []

        for pk in batch_pages:
            if pk not in sr_pages:
                blocking.append(f"{pk}: not found in self_review.json")
                continue

            sp = sr_pages[pk]
            if sp.get("png_reviewed") is not True:
                png_review_missing.append(f"{pk}: png_reviewed must be true")
            if _report_warning_count(report_by_key.get(pk, {})) > 0:
                warnings_need_revision_pass.append(pk)
                va = sp.get("validator_assessment")
                if not isinstance(va, dict) or not str(va.get("action_taken", "")).strip():
                    validator_pages_missing.append(f"{pk}: validator_assessment.action_taken is required because validation has warnings")
            vs = sp.get("visual_status", sp.get("status", ""))
            if vs == "blocked":
                blocking.append(f"{pk}: visual_status is 'blocked'")

            fixes = sp.get("required_fixes", [])
            if fixes:
                pages_with_fixes.append(f"{pk}: has {len(fixes)} required fix(es)")

        # visual_status 'blocked' is a hard block before user visual review
        if blocking:
            fail("Self-review blockers:\n  - " + "\n  - ".join(blocking))
        if png_review_missing:
            fail("PNG visual self-review evidence is missing:\n  - " + "\n  - ".join(png_review_missing))
        if validator_pages_missing:
            fail("Validator findings were not integrated into self-review:\n  - " + "\n  - ".join(validator_pages_missing))
        if warnings_need_revision_pass:
            vrp = sr.get("validator_revision_pass")
            if not isinstance(vrp, dict) or vrp.get("attempted") is not True:
                fail(
                    "Validation has warning(s) for page(s) "
                    + ", ".join(warnings_need_revision_pass)
                    + "; perform at least one validator-informed revision pass and record self_review.validator_revision_pass.attempted=true"
                )
            if not str(vrp.get("summary", "")).strip():
                fail("self_review.validator_revision_pass.summary is required when validation warnings exist")

        # required_fixes with visual_status 'revise' or 'blocked' blocks user review
        if pages_with_fixes:
            fail("Required fixes must be resolved before user visual review:\n  - " + "\n  - ".join(pages_with_fixes))

    for pk in batch_pages:
        manifest_by_key[pk]["validation_status"] = report_by_key[pk].get("status", "pass")

    if batch_id:
        _set_batch_status(manifest, batch_id, "preview_ready")
    _save_manifest(internal, manifest)
    if vision_available:
        ok(f"Batch '{batch_id}' preview ready — PNG previews, validation, and self-review are clean")
    else:
        ok(f"Batch '{batch_id}' preview ready — PNG previews and validation are clean; model visual review is unavailable, so human review remains required")


def gate_visual_approved(root, internal, batch_id=None):
    """Check that visual review HTML exists, feedback is submitted, and pages are clear."""
    if not batch_id:
        fail("--batch is required for visual-approved gate")
    review_html = root / "02_visual_review.html"
    if not review_html.exists():
        fail("02_visual_review.html not found — run generate_review_html.py first")

    # Load manifest
    manifest = _load_manifest(internal)

    manifest_pages = manifest.get("pages", [])
    manifest_by_key = {p.get("page_key"): p for p in manifest_pages if isinstance(p, dict)}

    # Determine batch pages
    batch_pages = _get_batch_pages(manifest, batch_id)
    _fail_if_future_artifacts(root, internal, manifest, batch_id, {"svg", "png", "validation", "self_review"})

    # ── Check 1: manifest page state — no validation failures ──
    for pk in batch_pages:
        mp = manifest_by_key.get(pk, {})
        if mp.get("validation_status") in ("fail", "not_validated", "", None):
            fail(f"{pk}: validation_status is '{mp.get('validation_status')}' — cannot approve visually")

    # ── Check 2: self-review blockers ──
    self_review_path = internal / "04_validation" / "self_review.json"
    sr = load_json(self_review_path)
    if sr and sr.get("vision_available", True):
        sr_pages = sr.get("pages", {})
        for pk in batch_pages:
            sp = sr_pages.get(pk, {})
            vs = sp.get("visual_status", sp.get("status", ""))
            if vs == "blocked":
                fail(f"{pk}: visual_status is 'blocked' in self-review — cannot approve visually")
            fixes = sp.get("required_fixes", [])
            if fixes:
                fail(f"{pk}: has {len(fixes)} required fix(es) in self-review — cannot approve visually")

    # ── Check 3: batch feedback existence and approval ──
    fb, feedback_path = _require_visual_feedback_for_batch(internal, batch_id)

    pages_fb = fb.get("pages", {})
    if not pages_fb:
        fail(f"{feedback_path} has no page feedback entries")

    for pk in batch_pages:
        page_fb = pages_fb.get(pk)
        if page_fb is None:
            fail(f"{pk}: not present in {feedback_path} — submit feedback for this page")
        if not page_fb.get("approved"):
            fail(f"{pk}: not approved in visual review feedback")

    for pk in batch_pages:
        manifest_by_key[pk]["visual_approved"] = True
        manifest_by_key[pk]["export_allowed"] = True
    if batch_id:
        _set_batch_status(manifest, batch_id, "visual_approved")
    _save_manifest(internal, manifest)

    if batch_id:
        ok(f"Batch '{batch_id}' visual approved — all checks passed")
    else:
        ok("All pages visually approved — all checks passed")


def gate_export_ready(root, internal):
    """Check that all pages are generated, validated, and approved for PPT export."""
    manifest = load_json(internal / "00_project" / "page_manifest.json")
    if not manifest:
        fail("page_manifest.json not found or invalid")

    layout_feedback = load_json(internal / "01_layout_plan" / "layout_feedback.json")
    if not layout_feedback:
        fail("layout_feedback.json not found or invalid — export requires trusted layout approval")
    _require_review_server_provenance(layout_feedback, "/layout-feedback", "layout_feedback.json")
    if layout_feedback.get("all_approved") is not True:
        fail("layout_feedback.json is not fully approved")

    pages = manifest.get("pages", [])
    if not pages:
        fail("page_manifest.json has no pages — nothing to export")

    batch_config = manifest.get("batch_config", {})
    if not isinstance(batch_config, dict) or not batch_config:
        fail("page_manifest.json batch_config is required for trusted visual approval export checks")

    for batch_id in sorted(batch_config):
        batch_pages = _get_batch_pages(manifest, batch_id)
        visual_feedback, feedback_path = _require_visual_feedback_for_batch(internal, batch_id)
        pages_fb = visual_feedback.get("pages", {})
        missing_or_unapproved = [
            pk for pk in batch_pages
            if not isinstance(pages_fb.get(pk), dict) or not pages_fb[pk].get("approved")
        ]
        if missing_or_unapproved:
            fail(
                f"{feedback_path}: batch '{batch_id}' is missing approved feedback for "
                + ", ".join(missing_or_unapproved)
            )

    issues = []
    for p in pages:
        pk = p.get("page_key", "?")
        svg_path = p.get("svg_path", "")
        png_path = p.get("png_path", "")

        if not svg_path:
            issues.append(f"{pk}: svg_path not set")
        elif not (root / svg_path).exists():
            issues.append(f"{pk}: SVG not found at {svg_path}")

        if not png_path:
            issues.append(f"{pk}: png_path not set")
        elif not (root / png_path).exists():
            issues.append(f"{pk}: PNG not found at {png_path}")

        if not p.get("layout_approved"):
            issues.append(f"{pk}: layout not approved")
        if not p.get("visual_approved"):
            issues.append(f"{pk}: visual not approved")
        if not p.get("export_allowed"):
            issues.append(f"{pk}: export_allowed is false")
        if p.get("validation_status") in ("fail", "not_validated", "", None):
            issues.append(f"{pk}: validation_status is '{p.get('validation_status')}'")

    # Check for planned-but-missing pages (catches "18 generated but 24 planned")
    planned_count = len(pages)
    generated_count = sum(1 for p in pages if p.get("svg_path") and (root / p.get("svg_path", "")).exists())
    if generated_count < planned_count:
        issues.append(
            f"Only {generated_count}/{planned_count} pages have generated SVG files — "
            f"{planned_count - generated_count} page(s) are planned but not generated"
        )

    if issues:
        fail("Export not ready:\n  - " + "\n  - ".join(issues))

    ok(f"Export ready — {planned_count} page(s) all cleared for PPT conversion")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline gate enforcer for Planner's PPT Hell."
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("gate", choices=[
        "layout-ready", "layout-approved",
        "batch-svg-ready", "validation-passed", "preview-ready",
        "visual-approved", "export-ready",
    ], help="Gate to check")
    parser.add_argument("--batch", default="", help="Batch ID (required for batch-svg-ready, validation-passed, preview-ready, and visual-approved)")
    parser.add_argument(
        "--allow-vision-unavailable",
        action="store_true",
        help="Allow preview-ready to continue with vision_available=false. Use only when the runtime truly cannot inspect PNG images.",
    )
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"

    if not internal.is_dir():
        fail(f"_internal/ directory not found in {root} — run init_svg_project.py first")

    gate_funcs = {
        "layout-ready": lambda: gate_layout_ready(root, internal),
        "layout-approved": lambda: gate_layout_approved(root, internal, args.batch or None),
        "batch-svg-ready": lambda: gate_batch_svg_ready(root, internal, args.batch),
        "validation-passed": lambda: gate_validation_passed(root, internal, args.batch),
        "preview-ready": lambda: gate_preview_ready(root, internal, args.batch, args.allow_vision_unavailable),
        "visual-approved": lambda: gate_visual_approved(root, internal, args.batch),
        "export-ready": lambda: gate_export_ready(root, internal),
    }

    gate_funcs[args.gate]()


if __name__ == "__main__":
    main()
