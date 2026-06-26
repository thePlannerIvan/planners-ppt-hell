"""
Contract validator for Planner's PPT Hell.

Validates project contract files for the requested workflow stage.

Exit code: 0 if all checks pass, 1 if any error-level failure is found.
"""

import argparse
import json
import sys
from pathlib import Path

# Legacy fields that must not be used as primary page identifiers
LEGACY_ID_FIELDS = {"page", "page_number", "page_id", "layout"}

# Required fields per contract
CONTENT_REQUIRED = {"page_key", "action_title", "core_message", "body_blocks"}
LAYOUT_REQUIRED = {
    "page_key",
    "layout_id",
    "page_mode",
    "visual_density",
    "grid",
    "wireframe",
    "layout_reason",
    "copy_handling",
    "visual_asset_strategy",
}
VALID_ASSET_NEEDS = {"required", "optional", "none"}
VALID_ASSET_TYPES = {
    "real_asset",
    "data_visual",
    "editable_schematic",
    "photo_placeholder",
    "screenshot_placeholder",
    "svg_background",
    "svg_illustration",
    "generated_image",
    "chart",
    "none",
}
VALID_ASSET_PLACEMENTS = {
    "main_right",
    "full_bleed",
    "background",
    "card_visual",
    "evidence_slot",
    "inline_diagram",
    "none",
}
MANIFEST_REQUIRED = {"page_key", "layout_approved", "visual_approved", "export_allowed"}
VALID_BATCH_STATUSES = {
    "planned",
    "layout_approved",
    "svg_generated",
    "validation_passed",
    "preview_ready",
    "visual_approved",
}


def load_json(path):
    """Load and parse a JSON file. Returns (data, error_message)."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {p}: {e}"
    except Exception as e:
        return None, f"Cannot read {p}: {e}"


def validate(content_data, layout_data, manifest_data, stage="all"):
    errors = []
    warnings = []
    infos = []

    E = errors.append
    W = warnings.append
    I = infos.append

    # ── 1. Basic file presence (pre-checked by caller) ──

    # ── 2. Top-level structure ──
    files_to_check = [
        ("page_content.json", content_data, "pages"),
        ("page_manifest.json", manifest_data, "pages"),
    ]
    if stage in ("plan", "draft", "export", "all"):
        files_to_check.append(("layout_plan.json", layout_data, "pages"))

    for name, data, expected_key in files_to_check:
        if not isinstance(data, dict):
            E(f"{name}: not a JSON object")
            continue
        if expected_key not in data:
            E(f"{name}: missing '{expected_key}' array")
        elif not isinstance(data[expected_key], list):
            E(f"{name}: '{expected_key}' is not an array")
        elif len(data[expected_key]) == 0:
            W(f"{name}: '{expected_key}' array is empty — project may not be initialized yet")

    # ── 3. Extract page keys ──
    content_pages = content_data.get("pages", []) if isinstance(content_data, dict) else []
    layout_pages = layout_data.get("pages", []) if isinstance(layout_data, dict) else []
    manifest_pages = manifest_data.get("pages", []) if isinstance(manifest_data, dict) else []

    content_keys = set()
    for i, p in enumerate(content_pages):
        if not isinstance(p, dict):
            E(f"page_content.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            content_keys.add(pk)

    layout_keys = set()
    for i, p in enumerate(layout_pages):
        if not isinstance(p, dict):
            E(f"layout_plan.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            layout_keys.add(pk)

    manifest_keys = set()
    for i, p in enumerate(manifest_pages):
        if not isinstance(p, dict):
            E(f"page_manifest.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            manifest_keys.add(pk)

    # ── 4. Cross-contract key consistency ──
    # Every page_key in layout_plan must exist in page_content
    if stage in ("plan", "draft", "export", "all"):
        orphan_layout = layout_keys - content_keys
        if orphan_layout:
            E(f"layout_plan.json references page_keys not in page_content.json: {sorted(orphan_layout)}")

        # Every page_key in layout_plan must exist in page_manifest
        orphan_layout_m = layout_keys - manifest_keys
        if orphan_layout_m:
            E(f"layout_plan.json references page_keys not in page_manifest.json: {sorted(orphan_layout_m)}")

    # Every page_key in page_manifest must exist in page_content
    orphan_manifest = manifest_keys - content_keys
    if orphan_manifest:
        E(f"page_manifest.json references page_keys not in page_content.json: {sorted(orphan_manifest)}")

    if stage in ("plan", "draft", "export", "all"):
        # Every page_key in page_manifest must exist in layout_plan
        orphan_manifest_l = manifest_keys - layout_keys
        if orphan_manifest_l:
            E(f"page_manifest.json references page_keys not in layout_plan.json: {sorted(orphan_manifest_l)}")

    # All keys from content should be in manifest (once pages is non-empty)
    missing_from_manifest = content_keys - manifest_keys
    if missing_from_manifest and content_keys:
        E(f"page_content.json has page_keys not in page_manifest.json: {sorted(missing_from_manifest)}")

    # ── 5. page_key format and sequentiality ──
    all_keys = content_keys | layout_keys | manifest_keys
    for pk in sorted(all_keys):
        if not pk.startswith("page_"):
            E(f"Invalid page_key format: '{pk}' — must be 'page_NN'")
            continue
        try:
            num_part = pk.split("_")[1]
            if len(num_part) != 2 or not num_part.isdigit():
                E(f"Invalid page_key format: '{pk}' — must be 'page_NN' (two-digit zero-padded)")
        except (IndexError, ValueError):
            E(f"Invalid page_key format: '{pk}' — must be 'page_NN'")

    # Check sequentiality among content keys (defines canonical order)
    content_nums = []
    for pk in sorted(content_keys):
        try:
            content_nums.append(int(pk.split("_")[1]))
        except (IndexError, ValueError):
            pass
    if content_nums:
        expected_nums = list(range(1, len(content_nums) + 1))
        if content_nums != expected_nums:
            W(f"page_content.json page_keys are not sequential: got {content_nums}, expected {expected_nums}")

    # ── 6. Required fields per page ──
    # Content pages
    for i, p in enumerate(content_pages):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        # Check for legacy identifiers
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"page_content.json {pk}: uses legacy field '{legacy}' as identifier — use 'page_key' instead")
        # Required fields
        for field in CONTENT_REQUIRED:
            if field not in p:
                E(f"page_content.json {pk}: missing required field '{field}'")
            elif field == "body_blocks" and (not isinstance(p[field], list) or len(p[field]) == 0):
                E(f"page_content.json {pk}: 'body_blocks' is empty — full copy required")
            elif field in ("action_title", "core_message") and (not isinstance(p[field], str) or not p[field].strip()):
                E(f"page_content.json {pk}: '{field}' is empty")

    # Layout pages
    for i, p in enumerate(layout_pages if stage in ("plan", "draft", "export", "all") else []):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"layout_plan.json {pk}: uses legacy field '{legacy}' as identifier")
        for field in LAYOUT_REQUIRED:
            if field not in p:
                E(f"layout_plan.json {pk}: missing required field '{field}'")
            elif field == "wireframe" and (not isinstance(p[field], list) or len(p[field]) == 0):
                E(f"layout_plan.json {pk}: 'wireframe' is empty — at least one zone required")
            elif field == "layout_reason" and (not isinstance(p[field], str) or not p[field].strip()):
                E(f"layout_plan.json {pk}: 'layout_reason' is empty")
            elif field == "copy_handling":
                ch = p[field]
                if not isinstance(ch, dict) or "kept_on_slide" not in ch:
                    E(f"layout_plan.json {pk}: 'copy_handling' missing 'kept_on_slide'")
                elif not ch.get("kept_on_slide"):
                    E(f"layout_plan.json {pk}: 'copy_handling.kept_on_slide' is empty")
                if isinstance(ch, dict):
                    final_copy = ch.get("final_on_slide")
                    if not isinstance(final_copy, dict):
                        E(f"layout_plan.json {pk}: 'copy_handling.final_on_slide' is required")
                    else:
                        if not str(final_copy.get("title", "")).strip():
                            E(f"layout_plan.json {pk}: 'copy_handling.final_on_slide.title' is required")
                        body = final_copy.get("body", [])
                        has_body = (isinstance(body, list) and any(str(x).strip() for x in body)) or (
                            isinstance(body, str) and body.strip()
                        )
                        has_subtitle = bool(str(final_copy.get("subtitle", "")).strip())
                        has_footer = bool(str(final_copy.get("footer_takeaway", "")).strip())
                        if not (has_body or has_subtitle or has_footer):
                            E(f"layout_plan.json {pk}: final_on_slide needs body, subtitle, or footer_takeaway")
                    rationale = ch.get("compression_rationale", [])
                    if not isinstance(rationale, list) or not any(str(x).strip() for x in rationale):
                        E(f"layout_plan.json {pk}: 'copy_handling.compression_rationale' is required")
            elif field == "visual_asset_strategy":
                vas = p[field]
                if not isinstance(vas, dict):
                    E(f"layout_plan.json {pk}: 'visual_asset_strategy' must be an object")
                else:
                    for vf in ("asset_need", "asset_type", "placement", "reason"):
                        if not str(vas.get(vf, "")).strip():
                            E(f"layout_plan.json {pk}: 'visual_asset_strategy' missing '{vf}'")
                    if vas.get("asset_need") and vas.get("asset_need") not in VALID_ASSET_NEEDS:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.asset_need is '{vas.get('asset_need')}'")
                    if vas.get("asset_type") and vas.get("asset_type") not in VALID_ASSET_TYPES:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.asset_type is '{vas.get('asset_type')}'")
                    if vas.get("placement") and vas.get("placement") not in VALID_ASSET_PLACEMENTS:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.placement is '{vas.get('placement')}'")
                    if vas.get("asset_need") == "none":
                        if vas.get("asset_type") != "none" or vas.get("placement") != "none":
                            E(f"layout_plan.json {pk}: asset_need 'none' requires asset_type='none' and placement='none'")
                    if vas.get("asset_type") in ("real_asset", "photo_placeholder", "screenshot_placeholder", "generated_image"):
                        if not str(vas.get("prompt_or_source", "")).strip():
                            W(f"layout_plan.json {pk}: visual_asset_strategy.prompt_or_source should describe source/prompt")
            elif field in ("page_mode",):
                if p[field] not in ("rational", "emotional"):
                    W(f"layout_plan.json {pk}: 'page_mode' is '{p[field]}' — expected 'rational' or 'emotional'")
            elif field in ("visual_density",):
                if p[field] not in ("dense", "balanced", "airy"):
                    W(f"layout_plan.json {pk}: 'visual_density' is '{p[field]}' — expected 'dense', 'balanced', or 'airy'")

        # Wireframe zone checks
        wireframe = p.get("wireframe", [])
        for wi, zone in enumerate(wireframe):
            if not isinstance(zone, dict):
                continue
            for zf in ("label", "x", "y", "w", "h"):
                if zf not in zone:
                    W(f"layout_plan.json {pk} wireframe[{wi}]: missing '{zf}'")

    # Manifest pages
    for i, p in enumerate(manifest_pages):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"page_manifest.json {pk}: uses legacy field '{legacy}' as identifier")
        for field in MANIFEST_REQUIRED:
            if field not in p:
                E(f"page_manifest.json {pk}: missing required field '{field}'")
            elif field in ("layout_approved", "visual_approved", "export_allowed"):
                if not isinstance(p[field], bool):
                    E(f"page_manifest.json {pk}: '{field}' must be boolean, got {type(p[field]).__name__}")

        # Consistency: export_allowed must be false if validation_status is fail
        vs = p.get("validation_status")
        ea = p.get("export_allowed")
        if vs == "fail" and ea is True:
            E(f"page_manifest.json {pk}: 'export_allowed' is true but 'validation_status' is 'fail'")

    # ── 7. Manifest batch_config validation ──
    batch_config = manifest_data.get("batch_config", {}) if isinstance(manifest_data, dict) else {}
    batch_size = manifest_data.get("batch_size", 3) if isinstance(manifest_data, dict) else 3
    if not isinstance(batch_size, int) or batch_size <= 0:
        E("page_manifest.json batch_size must be a positive integer")
    if not isinstance(batch_config, dict):
        E("page_manifest.json batch_config must be an object")
    else:
        for bid, bdata in batch_config.items():
            if not isinstance(bdata, dict):
                E(
                    f"page_manifest.json batch_config.{bid}: must be an object with "
                    "'status' and 'pages'; list-style batches are not supported"
                )
                continue
            status = bdata.get("status")
            if status not in VALID_BATCH_STATUSES:
                E(
                    f"page_manifest.json batch_config.{bid}.status: expected one of "
                    f"{sorted(VALID_BATCH_STATUSES)}, got {status!r}"
                )
            batch_pages = bdata.get("pages", [])
            if not isinstance(batch_pages, list) or not batch_pages:
                E(f"page_manifest.json batch_config.{bid}.pages must be a non-empty list")
                continue
            if len(batch_pages) > batch_size:
                # Check for explicit batch_size_override on this batch
                override = bdata.get("batch_size_override")
                if override and isinstance(override, int) and len(batch_pages) <= override:
                    pass  # explicitly allowed
                else:
                    E(f"page_manifest.json batch_config.{bid}: {len(batch_pages)} pages exceed batch_size {batch_size} (set 'batch_size_override' to explicitly allow)")
            for bpk in batch_pages:
                if bpk not in manifest_keys:
                    E(f"page_manifest.json batch_config.{bid}: references unknown page_key '{bpk}'")

    return errors, warnings, infos


def main():
    parser = argparse.ArgumentParser(
        description="Validate project contract files for Planner's PPT Hell."
    )
    parser.add_argument("project_dir", help="Project root directory containing _internal/")
    parser.add_argument(
        "--stage",
        choices=["content", "plan", "draft", "export", "all"],
        default="all",
        help="Validate only the contracts required for this workflow stage.",
    )
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"

    content_path = internal / "01_content" / "page_content.json"
    layout_path = internal / "01_layout_plan" / "layout_plan.json"
    manifest_path = internal / "00_project" / "page_manifest.json"

    # Load required contracts for the requested stage.
    content_data, content_err = load_json(content_path)
    manifest_data, manifest_err = load_json(manifest_path)
    if args.stage in ("plan", "draft", "export", "all"):
        layout_data, layout_err = load_json(layout_path)
    else:
        layout_data, layout_err = {"pages": []}, None

    has_error = False

    # Report file-level errors
    for label, err in [
        ("page_content.json", content_err),
        ("layout_plan.json", layout_err),
        ("page_manifest.json", manifest_err),
    ]:
        if err:
            print(f"ERROR: {err}")
            has_error = True

    if has_error:
        sys.exit(1)

    errors, warnings, infos = validate(content_data, layout_data, manifest_data, args.stage)

    # Print results
    total_issues = len(errors) + len(warnings) + len(infos)
    if total_issues == 0:
        print("All contract checks passed.")
        sys.exit(0)

    for e in errors:
        print(f"ERROR: {e}")
    for w in warnings:
        print(f"WARNING: {w}")
    for i in infos:
        print(f"INFO: {i}")

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)")

    if errors:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
