#!/usr/bin/env python3
"""Publish, list, validate, and apply local template packages (v2 4-piece Multimodal Template Packs + v1 legacy support)."""

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
DEFAULT_LIBRARY_ROOT = LIBRARY_ROOT

PROJECT_FILES = (
    "template_profile.json",
    "template_asset_registry.json",
    "template_worker_result.json",
)
PROJECT_DIRS = ("fidelity_template", "template_media")

REQUIRED_PACK_FILES = ("tokens.css", "skyline_shell.svg", "SPEC.md")
REQUIRED_PACK_DIRS = ("primitives", "anchors")


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


sha256_file = sha256


def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", str(value).strip()).strip("-_")
    return value[:48] or "template"


def package_files(root):
    root = Path(root)
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json" and not path.name.startswith(".")
    )


def package_hashes(root):
    root = Path(root)
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


def validate_pack_dir(pack_dir, check_manifest_hashes=False):
    """Validate a v2 4-piece multimodal template pack (`tokens.css`, `skyline_shell.svg`, `primitives/*.svg`, `SPEC.md` + `anchors/`)."""
    pack_dir = Path(pack_dir).resolve()
    issues = []
    if not pack_dir.is_dir():
        return {"valid": False, "issues": [f"Directory not found: {pack_dir}"]}

    for req_file in REQUIRED_PACK_FILES:
        if not (pack_dir / req_file).is_file():
            issues.append(f"Missing required file: {req_file}")

    for req_dir in REQUIRED_PACK_DIRS:
        if not (pack_dir / req_dir).is_dir():
            issues.append(f"Missing required directory: {req_dir}/")

    primitives = sorted((pack_dir / "primitives").glob("*.svg")) if (pack_dir / "primitives").is_dir() else []
    if len(primitives) < 5:
        issues.append(f"Expected at least 5 SVG primitives in primitives/, found {len(primitives)}")

    anchors = sorted((pack_dir / "anchors").glob("*.png")) if (pack_dir / "anchors").is_dir() else []
    if len(anchors) < 1:
        issues.append("Expected at least 1 reference PNG in anchors/")

    tokens_path = pack_dir / "tokens.css"
    if tokens_path.is_file():
        tokens_text = tokens_path.read_text(encoding="utf-8")
        if ":root" not in tokens_text or "--" not in tokens_text:
            issues.append("tokens.css must define :root CSS custom properties (--*)")

    if check_manifest_hashes:
        manifest_path = pack_dir / "manifest.json"
        if not manifest_path.is_file():
            issues.append("Missing manifest.json")
        else:
            manifest = read_json(manifest_path, {})
            actual_hashes = package_hashes(pack_dir)
            if manifest.get("files") != actual_hashes:
                issues.append("manifest.json file hash mismatch")
            if manifest.get("package_sha256") != package_sha256(actual_hashes):
                issues.append("manifest.json package_sha256 mismatch")

    return {
        "valid": len(issues) == 0,
        "pack_dir": str(pack_dir),
        "primitive_count": len(primitives),
        "primitives": [p.name for p in primitives],
        "anchor_count": len(anchors),
        "issues": issues,
    }


def build_manifest(pack_dir, template_id, name, description="", is_default=False, palette_summary=None, scenarios=None):
    pack_dir = Path(pack_dir).resolve()
    hashes = package_hashes(pack_dir)
    primitives = sorted((pack_dir / "primitives").glob("*.svg"))
    anchors = sorted((pack_dir / "anchors").glob("*.png"))
    preview = ""
    if (pack_dir / "previews" / "full_deck_contact_sheet.png").is_file():
        preview = "previews/full_deck_contact_sheet.png"
    elif anchors:
        preview = f"anchors/{anchors[0].name}"

    manifest = {
        "schema": "planner.multimodal-template-pack.v2",
        "template_id": template_id,
        "name": name,
        "description": description,
        "status": "approved",
        "is_default": bool(is_default),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "canvas_size": "1920x1080",
        "four_piece_contract": {
            "tokens_css": "tokens.css",
            "skyline_shell_svg": "skyline_shell.svg",
            "primitives": [f"primitives/{p.name}" for p in primitives],
            "spec_md": "SPEC.md",
            "anchors": [f"anchors/{a.name}" for a in anchors],
        },
        "palette_summary": palette_summary or {},
        "recommended_scenarios": scenarios or [],
        "preview": preview,
        "files": hashes,
        "package_sha256": package_sha256(hashes),
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def list_templates(library_root=None):
    lib_root = Path(library_root).resolve() if library_root else LIBRARY_ROOT
    items = []
    if lib_root.is_dir():
        for manifest_path in sorted(lib_root.glob("*/manifest.json")):
            data = read_json(manifest_path, {})
            if data.get("status") == "approved":
                entry = {
                    "template_id": data.get("template_id", manifest_path.parent.name),
                    "name": data.get("name", manifest_path.parent.name),
                    "schema": data.get("schema", "planner.template-library.v1"),
                    "mode": data.get("mode", "multimodal-pack" if "four_piece_contract" in data else "reference"),
                    "is_default": data.get("is_default") is True,
                    "published_at": data.get("published_at", ""),
                    "preview": str(manifest_path.parent / data.get("preview", "")) if data.get("preview") else "",
                }
                if "four_piece_contract" in data:
                    entry["description"] = data.get("description", "")
                    entry["primitive_count"] = len(data["four_piece_contract"].get("primitives", []))
                    entry["primitives"] = data["four_piece_contract"].get("primitives", [])
                    entry["palette_summary"] = data.get("palette_summary", {})
                    entry["recommended_scenarios"] = data.get("recommended_scenarios", [])
                items.append(entry)
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
    snapshot = template_review_snapshot(project_root)
    if not snapshot or str(feedback.get("review_id", "")) != str(snapshot.get("review_id", "")):
        raise ValueError("template approval is not bound to the current review page; rerun template-review and decide again")
    review_html = project_root / "00_template_review.html"
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


def publish_template(project_root, template_id="", name="", description="", library_root=None):
    """Publish a v2 4-piece multimodal template pack from `<project_root>/_internal/00_project/template_pack`."""
    project_root = Path(project_root).resolve()
    lib_root = Path(library_root).resolve() if library_root else LIBRARY_ROOT
    source_pack = project_root / "_internal" / "00_project" / "template_pack"
    validation = validate_pack_dir(source_pack, check_manifest_hashes=False)
    if not validation["valid"]:
        raise ValueError(f"Project template_pack is incomplete: {validation['issues']}")

    feedback = read_json(project_root / "_internal" / "00_project" / "template_feedback.json", {})
    final_name = name or feedback.get("template_name") or project_root.name
    final_id = template_id or slugify(final_name)

    dest = lib_root / final_id
    if dest.exists():
        shutil.rmtree(dest)
    lib_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_pack, dest)

    return build_manifest(
        dest,
        template_id=final_id,
        name=final_name,
        description=description or feedback.get("overall_feedback", ""),
        is_default=False,
    )


def publish(project_root, template_id="", name="", description="", library_root=None):
    project_root = Path(project_root).resolve()
    project = project_root / "_internal" / "00_project"
    if (project / "template_pack").is_dir() and not (project / "fidelity_template").is_dir():
        return publish_template(project_root, template_id=template_id, name=name, description=description, library_root=library_root)

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

    t_name = str(feedback["template_name"]).strip()
    digest_source = json.dumps({
        "profile": profile,
        "registry": read_json(project / "fidelity_template" / "template_registry.json", {}),
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(digest_source).hexdigest()[:8]
    t_id = f"{slugify(t_name)}-{digest}"
    destination = LIBRARY_ROOT / t_id
    if destination.exists():
        existing = read_json(destination / "manifest.json", {})
        if existing.get("template_id") == t_id and package_hashes(destination) == existing.get("files", {}):
            return existing
        raise ValueError(f"template library destination already exists: {destination}")

    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{t_id}.", dir=str(LIBRARY_ROOT)))
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
            "template_id": t_id,
            "name": t_name,
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


def apply_template(project_root, template_id, library_root=None):
    project_root = Path(project_root).resolve()
    lib_root = Path(library_root).resolve() if library_root else LIBRARY_ROOT.resolve()
    source = (lib_root / template_id).resolve()
    if source.parent != lib_root or not source.is_dir():
        raise ValueError(f"unknown template_id: {template_id}")
    manifest = read_json(source / "manifest.json", {})
    if manifest.get("status") != "approved" or manifest.get("template_id") != template_id:
        raise ValueError("template library manifest is invalid")

    # v2 4-piece multimodal template pack
    if manifest.get("schema") == "planner.multimodal-template-pack.v2" or "four_piece_contract" in manifest:
        validation = validate_pack_dir(source, check_manifest_hashes=True)
        if not validation["valid"]:
            raise ValueError(f"Template pack '{template_id}' failed validation: {validation['issues']}")
        target = project_root / "_internal" / "00_project" / "template_pack"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        (project_root / "_internal" / "00_project" / "template_library_source.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "applied_template_id": template_id,
            "target_dir": str(target),
            "primitives": manifest.get("four_piece_contract", {}).get("primitives", []),
        }

    # v1 legacy fidelity template package
    actual = package_hashes(source)
    if actual != manifest.get("files", {}):
        raise ValueError("template library package hash mismatch")
    if manifest.get("package_sha256") != package_sha256(actual):
        raise ValueError("template library package_sha256 mismatch")
    registry = read_json(source / "fidelity_template" / "template_registry.json", {})
    if registry:
        validate_component_references(registry)
    project = project_root / "_internal" / "00_project"
    project.mkdir(parents=True, exist_ok=True)
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
    p_list = sub.add_parser("list")
    p_list.add_argument("--library-root", default=None)

    p_val = sub.add_parser("validate")
    p_val.add_argument("pack_dir")
    p_val.add_argument("--check-hashes", action="store_true")

    p_pub = sub.add_parser("publish")
    p_pub.add_argument("project_dir")
    p_pub.add_argument("--template-id", default="")
    p_pub.add_argument("--name", default="")
    p_pub.add_argument("--description", default="")
    p_pub.add_argument("--library-root", default=None)

    p_app = sub.add_parser("apply")
    p_app.add_argument("project_dir")
    p_app.add_argument("--template-id", required=True)
    p_app.add_argument("--library-root", default=None)

    args = parser.parse_args()
    if args.command == "list":
        result = list_templates(args.library_root)
    elif args.command == "validate":
        result = validate_pack_dir(args.pack_dir, check_manifest_hashes=args.check_hashes)
        if not result["valid"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(1)
    elif args.command == "publish":
        result = publish(args.project_dir, template_id=args.template_id, name=args.name,
                         description=args.description, library_root=args.library_root)
    else:
        result = apply_template(args.project_dir, args.template_id, library_root=args.library_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
