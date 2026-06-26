"""
Validate self_review.json against the self-review contract.

Checks that the file exists, has required fields, and marks vision-unavailable
status explicitly. Used by pipeline_gate.py to determine if self-review gate passes.

Usage:
  python validate_self_review.py <project_dir>
"""

import argparse
import json
import sys
from pathlib import Path

VALID_STATUSES = {"pass", "revise", "blocked"}


def load_json(path):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Validate self_review.json against the self-review contract."
    )
    parser.add_argument("project_dir", help="Project root directory")
    args = parser.parse_args()

    root = Path(args.project_dir)
    internal = root / "_internal"
    sr_path = internal / "04_validation" / "self_review.json"

    if not sr_path.exists():
        print("ERROR: self_review.json not found.")
        print("Model visual self-review is required before proceeding.")
        print("If vision capability is unavailable, create a minimal file with vision_available: false.")
        sys.exit(1)

    sr = load_json(sr_path)
    if not sr:
        print("ERROR: self_review.json is invalid JSON.")
        sys.exit(1)

    errors = []
    warnings = []

    # Check top-level fields
    if "reviewed_at" not in sr:
        warnings.append("Missing 'reviewed_at' timestamp")
    if "vision_available" not in sr:
        errors.append("Missing required field 'vision_available' (set to true or false)")

    vision_available = sr.get("vision_available", False)
    if not vision_available:
        if sr.get("human_review_required") is not True:
            errors.append("vision_available is false, so human_review_required must be true")
        if not str(sr.get("vision_unavailable_reason", "")).strip():
            errors.append("vision_available is false, so vision_unavailable_reason is required")
    else:
        if not str(sr.get("vision_check_method", "")).strip():
            errors.append("vision_available is true, so vision_check_method is required")

    # Check pages
    pages = sr.get("pages", {})
    if not isinstance(pages, dict):
        errors.append("'pages' must be an object")
    elif not pages and vision_available:
        warnings.append("'pages' is empty — no pages have been reviewed")
    elif not vision_available and pages:
        errors.append("vision_available is false, so pages must be empty; do not write visual verdicts without vision")

    if isinstance(pages, dict):
        for pk, page in pages.items():
            if not isinstance(page, dict):
                errors.append(f"{pk}: not an object")
                continue

            vs = page.get("visual_status")
            if vs is None:
                warnings.append(f"{pk}: missing 'visual_status'")
            elif vs not in VALID_STATUSES:
                errors.append(f"{pk}: invalid visual_status '{vs}' — must be one of: {', '.join(sorted(VALID_STATUSES))}")

            if vision_available and page.get("png_reviewed") is not True:
                errors.append(f"{pk}: png_reviewed must be true when vision_available is true")

            va = page.get("validator_assessment")
            if va is not None:
                if not isinstance(va, dict):
                    errors.append(f"{pk}: validator_assessment must be an object")
                elif not str(va.get("action_taken", "")).strip():
                    errors.append(f"{pk}: validator_assessment.action_taken is required when validator_assessment is present")

            # If status is 'blocked', must have required_fixes
            if vs == "blocked":
                fixes = page.get("required_fixes", [])
                if not fixes:
                    errors.append(f"{pk}: visual_status is 'blocked' but required_fixes is empty")

            # If status is 'revise', should have required_fixes
            if vs == "revise":
                fixes = page.get("required_fixes", [])
                if not fixes:
                    warnings.append(f"{pk}: visual_status is 'revise' but required_fixes is empty")

            # Check confidence if present
            confidence = page.get("confidence")
            if confidence is not None:
                if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
                    warnings.append(f"{pk}: confidence should be between 0.0 and 1.0, got {confidence}")

            # Check suggestions
            suggestions = page.get("suggestions", [])
            if isinstance(suggestions, list) and len(suggestions) > 3:
                warnings.append(f"{pk}: has {len(suggestions)} suggestions (expected 0-3)")

    # Report results
    if vision_available:
        print("Vision: available")
    else:
        print("Vision: UNAVAILABLE — all model-visual checks deferred to human review")

    for e in errors:
        print(f"ERROR: {e}")
    for w in warnings:
        print(f"WARNING: {w}")

    total = len(errors) + len(warnings)
    if total == 0:
        print("Self-review validation passed.")
    else:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")

    if errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
