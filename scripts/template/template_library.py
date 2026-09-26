#!/usr/bin/env python3
"""Publish, list, and apply human-approved local template packages."""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layout_canvas import ensure_layout_canvases, registry_canvases_ready  # noqa: E402
from project_state import template_review_snapshot  # noqa: E402
from template_visual_gate import review_issues as template_canvas_review_issues  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = SKILL_ROOT / "assets" / "template_library"
PROJECT_FILES = (
    "template_profile.json",
    "template_asset_registry.json",
    "template_worker_result.json",
)
PROJECT_DIRS = ("fidelity_template", "template_media")


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


def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", str(value).strip()).strip("-_")
    return value[:48] or "template"


def package_files(root):
    return sorted(path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json")


def package_hashes(root):
    return {path.relative_to(root).as_posix(): sha256(path) for path in package_files(root)}


def package_sha256(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()


def validate_component_references(registry):
    component_ids = {item.get("component_id") for item in registry.get("components", []) if isinstance(item, dict)}
    referenced = set()
    invalid = []
    for layout_id, layout in registry.get("layouts", {}).items():
        required = layout.get("required_components", [])
        optional = layout.get("optional_components", [])
        if not required or not set(required + optional).issubset(component_ids):
            invalid.append(layout_id)
        referenced.update(required + optional)
    unreferenced = sorted(component_ids - referenced)
    if invalid or unreferenced:
        raise ValueError(f"invalid layout component references: layouts={invalid}, unreferenced={unreferenced}")


def list_templates():
    items = []
    if LIBRARY_ROOT.is_dir():
        for manifest_path in sorted(LIBRARY_ROOT.glob("*/manifest.json")):
            data = read_json(manifest_path, {})
            if data.get("status") == "approved":
                items.append({
                    "template_id": data.get("template_id", manifest_path.parent.name),
                    "name": data.get("name", manifest_path.parent.name),
                    "mode": data.get("mode", "reference"),
                    "is_default": data.get("is_default") is True,
                    "published_at": data.get("published_at", ""),
                    "preview": str(manifest_path.parent / data.get("preview", "")) if data.get("preview") else "",
                })
    return sorted(items, key=lambda item: (not item.get("is_default"), item.get("name", "")))


def require_approved_feedback(project):
    feedback = read_json(project / "template_feedback.json", {})
    if feedback.get("approved") is not True:
        raise ValueError("template package cannot be published without human approval")
    if not str(feedback.get("template_name", "")).strip():
        raise ValueError("approved template feedback requires template_name")
    if not feedback.get("layouts") or not all(item.get("approved") is True for item in feedback.get("layouts", {}).values()):
        raise ValueError("approved template feedback requires every abstract layout to be marked Yes")
    provenance = feedback.get("provenance", {})
    project_root = project.parents[1]
    # 与页面审阅同一条消费侧保护：批准必须来自当前这一版审阅页（快照 + review_id）。
    snapshot = template_review_snapshot(project_root)
    if not snapshot or str(feedback.get("review_id", "")) != str(snapshot.get("review_id", "")):
        raise ValueError("template approval is not bound to the current review page; rerun template-review and decide again")
    review_html = project_root / "00_template_review.html"
    # 写者从服务器换成**页面**（经宿主落盘）→ 收件层盖章；`review_server` 那份继续认，
    # 因为老项目里那份 approvals 是人真的给过的（删掉它等于静默作废一次人工批准）。
    source = provenance.get("source")
    if (source not in {"review_server", "template_review_page"}
            or (source == "review_server" and provenance.get("route") != "/template-feedback")
            or not review_html.is_file() or provenance.get("html_sha256") != sha256(review_html)):
        raise ValueError("template approval is not bound to the current review page HTML")
    visuals = project / "template_visuals"
    current_png = {path.name: sha256(path) for path in visuals.glob("*.png")}
    if not current_png or provenance.get("png_sha256") != current_png:
        raise ValueError("template approval is not bound to the current rendered template pages")
    fidelity = project / "fidelity_template"
    package_files_for_review = [fidelity / "template_registry.json"]
    package_files_for_review += sorted((fidelity / "layout_canvases").glob("*.svg"))
    package_files_for_review += sorted((fidelity / "canvas_previews" / "pages").glob("*.png"))
    package_files_for_review += [fidelity / "canvas_previews" / "full_deck_contact_sheet.png"]
    current_package = {
        str(path.relative_to(project_root)): sha256(path)
        for path in package_files_for_review if path.is_file()
    }
    if not current_package or provenance.get("template_package_sha256") != current_package:
        raise ValueError("template approval is not bound to the current registry, canvases, and previews")
    return feedback


def publish(project_root):
    project_root = Path(project_root).resolve()
    project = project_root / "_internal" / "00_project"
    feedback = require_approved_feedback(project)
    profile = read_json(project / "template_profile.json", {})
    mode = read_json(project_root / "_internal" / "00_project" / "page_manifest.json", {}).get("template_intake", {}).get("mode", "reference")
    if not profile:
        raise ValueError("template_profile.json is required")
    asset_registry = read_json(project / "template_asset_registry.json", {})
    facts = profile.get("structural_extraction", {})
    candidate_ids = {
        item.get("asset_id") for item in facts.get("assets", []) if isinstance(item, dict) and item.get("asset_id")
    } | {
        item.get("candidate_id") for item in facts.get("native_shapes", []) if isinstance(item, dict) and item.get("candidate_id")
    }
    if candidate_ids and set(asset_registry.get("reviewed_source_ids", [])) != candidate_ids:
        raise ValueError("template candidate audit is incomplete; reviewed_source_ids must cover every extracted candidate")
    if mode == "fidelity" and not (project / "fidelity_template" / "template_registry.json").is_file():
        raise ValueError("fidelity publication requires fidelity_template/template_registry.json")
    if mode == "fidelity":
        registry = read_json(project / "fidelity_template" / "template_registry.json", {})
        component_ids = {item.get("component_id") for item in registry.get("components", []) if isinstance(item, dict)}
        decision_ids = {item.get("component_id") for item in read_json(project / "template_worker_result.json", {}).get("approved_components", []) if isinstance(item, dict)}
        layouts = registry.get("layouts", {})
        invalid = [layout_id for layout_id, layout in layouts.items()
                   if not layout.get("required_components") or not set(layout.get("required_components", [])).issubset(component_ids)]
        if (not component_ids or component_ids != decision_ids or not layouts or invalid
                or "content_base" not in layouts
                or not registry_canvases_ready(registry, project / "fidelity_template")):
            raise ValueError(f"fidelity publication has invalid required component bindings: {invalid or ['content_base missing']}")
        validate_component_references(registry)
        visual_issues = template_canvas_review_issues(project_root)
        if visual_issues:
            raise ValueError("fidelity publication lacks completed source-vs-canvas visual judgment: " + "; ".join(visual_issues))

    name = str(feedback["template_name"]).strip()
    digest_source = json.dumps({
        "profile": profile,
        "registry": read_json(project / "fidelity_template" / "template_registry.json", {}),
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()[:8]
    template_id = f"{slugify(name)}-{digest}"
    destination = LIBRARY_ROOT / template_id
    if destination.exists():
        existing = read_json(destination / "manifest.json", {})
        if existing.get("template_id") == template_id and package_hashes(destination) == existing.get("files", {}):
            return existing
        raise ValueError(f"template library destination already exists: {destination}")

    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{template_id}.", dir=str(LIBRARY_ROOT)))
    try:
        for name_in_project in PROJECT_FILES:
            source = project / name_in_project
            if source.is_file():
                shutil.copy2(source, staging / name_in_project)
        staged_profile_path = staging / "template_profile.json"
        staged_profile = read_json(staged_profile_path, {})
        if staged_profile:
            staged_profile["source_files"] = [Path(item).name for item in staged_profile.get("source_files", [])]
            staged_profile_path.write_text(json.dumps(staged_profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fidelity_source = project / "fidelity_template"
        if fidelity_source.is_dir():
            shutil.copytree(fidelity_source, staging / "fidelity_template")
            staged_registry = staging / "fidelity_template" / "template_registry.json"
            registry_data = read_json(staged_registry, {})
            registry_data["source_files"] = [Path(item).name for item in registry_data.get("source_files", [])]
            staged_registry.write_text(json.dumps(registry_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        media_source = project / "template_media"
        if media_source.is_dir() and fidelity_source.is_dir():
            text = "\n".join(path.read_text(encoding="utf-8") for path in [
                fidelity_source / "components.svg", *sorted((fidelity_source / "layout_canvases").glob("*.svg"))
            ] if path.is_file())
            reachable = {match for match in re.findall(r"template_media/([^\"']+)", text)}
            if reachable:
                (staging / "template_media").mkdir(parents=True, exist_ok=True)
            for filename in sorted(reachable):
                source = media_source / filename
                if not source.is_file():
                    raise ValueError(f"reachable template media is missing: {filename}")
                shutil.copy2(source, staging / "template_media" / filename)
        contact_sheet = project / "template_visuals" / "contact_sheet.png"
        if contact_sheet.is_file():
            shutil.copy2(contact_sheet, staging / "contact_sheet.png")
        hashes = package_hashes(staging)
        manifest = {
            "schema": "planner.template-library.v1",
            "template_id": template_id,
            "name": str(feedback["template_name"]).strip(),
            "status": "approved",
            "mode": mode,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source_files": [Path(item).name for item in profile.get("source_files", [])],
            "review_summary": feedback.get("overall_feedback", ""),
            "preview": "contact_sheet.png" if contact_sheet.is_file() else "",
            "files": hashes,
            "package_sha256": package_sha256(hashes),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def apply_template(project_root, template_id):
    project_root = Path(project_root).resolve()
    source = (LIBRARY_ROOT / template_id).resolve()
    if source.parent != LIBRARY_ROOT.resolve() or not source.is_dir():
        raise ValueError(f"unknown template_id: {template_id}")
    manifest = read_json(source / "manifest.json", {})
    if manifest.get("status") != "approved" or manifest.get("template_id") != template_id:
        raise ValueError("template library manifest is invalid")
    actual = package_hashes(source)
    if actual != manifest.get("files", {}):
        raise ValueError("template library package hash mismatch")
    if manifest.get("package_sha256") != package_sha256(actual):
        raise ValueError("template library package_sha256 mismatch")
    registry = read_json(source / "fidelity_template" / "template_registry.json", {})
    if registry:
        validate_component_references(registry)
    project = project_root / "_internal" / "00_project"
    for filename in PROJECT_FILES:
        src = source / filename
        if src.is_file():
            shutil.copy2(src, project / filename)
    for dirname in PROJECT_DIRS:
        src = source / dirname
        dst = project / dirname
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    registry_path = project / "fidelity_template" / "template_registry.json"
    if registry_path.is_file():
        registry = read_json(registry_path, {})
        ensure_layout_canvases(registry, registry_path.parent)
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(source / "manifest.json", project / "template_library_source.json")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Manage Planner's local approved template library")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("publish")
    p.add_argument("project_dir")
    p = sub.add_parser("apply")
    p.add_argument("project_dir")
    p.add_argument("--template-id", required=True)
    args = parser.parse_args()
    if args.command == "list":
        result = list_templates()
    elif args.command == "publish":
        result = publish(args.project_dir)
    else:
        result = apply_template(args.project_dir, args.template_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
