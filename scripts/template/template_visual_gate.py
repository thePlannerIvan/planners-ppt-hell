#!/usr/bin/env python3
"""Machine gate for the Template Worker's source-vs-canvas visual judgment.

判据与逐页审阅**不同**，不要照搬同一句自检话术：

- 逐页审阅（`inspect --first-glance/--design-check`）问的是「**这个 PPT 做得好不好**」——
  重心、层级、节奏、可读性。
- 这里问的是「**有没有提炼出足够的模板规律**」——这套 canvas 是否真的复刻了源模板
  可复用的规律（`retained_features`、`compared_source_pages`、`visual_similarity`），
  而不是这套幻灯片本身好不好看。
"""

import hashlib
import json
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canvas_frame import FRAME_H_INT, FRAME_W_INT  # noqa: E402


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashes(paths):
    return {Path(path).name: sha256(path) for path in sorted(paths) if Path(path).is_file()}


def review_issues(project_root):
    root = Path(project_root).resolve()
    project = root / "_internal" / "00_project"
    fidelity = project / "fidelity_template"
    registry = read_json(fidelity / "template_registry.json", {})
    review = read_json(project / "template_canvas_self_review.json", {})
    visual_manifest = read_json(project / "template_visuals" / "visual_manifest.json", {})
    preview_manifest = read_json(fidelity / "canvas_previews" / "png_manifest.json", {})
    issues = []
    layouts = registry.get("layouts", {})
    expected_layouts = set(layouts)
    expected_sources = {
        Path(item.get("image", "")).stem
        for item in visual_manifest.get("pages", [])
        if isinstance(item, dict) and item.get("image")
    }
    if not expected_layouts:
        return ["fidelity registry has no layouts for visual comparison"]
    if review.get("status") != "completed" or review.get("vision_available") is not True:
        issues.append("template extraction self-check is not completed with vision_available=true: judge whether enough template regularity was extracted, not whether the deck looks good")
    if review.get("source_contact_sheet_viewed") is not True or review.get("canvas_contact_sheet_viewed") is not True:
        issues.append("both source and canvas contact sheets must be viewed")
    if int(review.get("inspection_rounds", 0) or 0) < 1:
        issues.append("template canvas visual review requires at least one inspection round")
    if set(review.get("source_pages_reviewed", [])) != expected_sources:
        issues.append("source_pages_reviewed does not cover every rendered source page")
    layout_reviews = review.get("layouts", {})
    if set(layout_reviews) != expected_layouts:
        issues.append("template canvas review does not cover every fidelity layout")
    for layout_id in sorted(expected_layouts):
        item = layout_reviews.get(layout_id, {})
        if item.get("canvas_png_reviewed") is not True:
            issues.append(f"{layout_id}: canvas PNG was not visually reviewed")
        if not item.get("compared_source_pages"):
            issues.append(f"{layout_id}: no source-page comparison evidence")
        if item.get("usable") is not True or item.get("visual_similarity") != "pass":
            issues.append(f"{layout_id}: canvas is not visually usable")
        if item.get("must_fix"):
            issues.append(f"{layout_id}: unresolved visual must_fix")
        if not item.get("retained_features", []):
            issues.append(f"{layout_id}: retained template features are not explicitly identified")

    canvas_svgs = [fidelity / layout.get("canvas_file", "") for layout in layouts.values()]
    canvas_pngs = list((fidelity / "canvas_previews").rglob("*.png"))
    source_pngs = list((project / "template_visuals").glob("*.png"))
    actual = {
        "source_png_sha256": hashes(source_pngs),
        "canvas_png_sha256": hashes(canvas_pngs),
        "canvas_svg_sha256": hashes(canvas_svgs),
    }
    evidence = review.get("evidence", {})
    for key, value in actual.items():
        if not value or evidence.get(key) != value:
            issues.append(f"template canvas visual evidence is stale or incomplete: {key}")
    preview_stems = {
        Path(item.get("file", "") if isinstance(item, dict) else item).stem
        for item in preview_manifest.get("generated_files", [])
    }
    if preview_stems != expected_layouts or preview_manifest.get("all_valid_size") is not True:
        issues.append(f"canvas preview manifest does not contain one valid {FRAME_W_INT}x{FRAME_H_INT} PNG per layout")
    return issues


def review_complete(project_root):
    return not review_issues(project_root)


def main():
    parser = argparse.ArgumentParser(description="Validate Template Worker source-vs-canvas visual evidence")
    parser.add_argument("project_dir")
    args = parser.parse_args()
    issues = review_issues(args.project_dir)
    print(json.dumps({"status": "pass" if not issues else "fail", "issues": issues}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
