import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

INTERNAL_ROOT = "_internal"

CANONICAL_DIRS = [
    f"{INTERNAL_ROOT}/00_project",
    f"{INTERNAL_ROOT}/01_content",
    f"{INTERNAL_ROOT}/01_layout_plan",
    f"{INTERNAL_ROOT}/02_svg_source",
    f"{INTERNAL_ROOT}/03_png_preview",
    f"{INTERNAL_ROOT}/04_validation",
    f"{INTERNAL_ROOT}/05_review/batches",
    f"{INTERNAL_ROOT}/05_review/versions",
    f"{INTERNAL_ROOT}/06_ppt_output",
    f"{INTERNAL_ROOT}/ref",
]

STARTER_FILES = {
    f"{INTERNAL_ROOT}/01_content/page_content.json": json.dumps(
        {"project": "", "source_path": "", "pages": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/01_layout_plan/layout_plan.json": json.dumps(
        {"project": "", "layout_version": 1, "pages": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/01_layout_plan/layout_capacity_report.json": json.dumps(
        {"project": "", "canvas": {"w": 1920, "h": 1080}, "pages": {}}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/01_layout_plan/layout_feedback.json": json.dumps(
        {"phase": "layout_plan", "version": 1, "pages": {}, "all_approved": False}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/00_project/page_manifest.json": json.dumps(
        {"project": "", "version": "2.0", "batch_size": 3, "batch_config": {}, "pages": []},
        ensure_ascii=False, indent=2,
    ),
    f"{INTERNAL_ROOT}/05_review/feedback.json": json.dumps(
        {"phase": "review", "batch_id": "", "pages": {}, "all_approved": False}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/00_project/feedback_archive.json": json.dumps(
        {"archived_at": "", "batches": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/00_project/flow_state.json": json.dumps(
        {
            "state": "CONTENT",
            "next_action": "整理源文案，写入 page_content.json，并建立 page_manifest.json 页面清单。",
            "current_batch": "",
            "current_pages": [],
            "checks": {},
        },
        ensure_ascii=False,
        indent=2,
    ),
    f"{INTERNAL_ROOT}/00_project/flow_events.jsonl": "",
}


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a Planner's PPT Hell project scaffold."
    )
    parser.add_argument("project_dir", help="Project output directory")
    parser.add_argument("--source", default="", help="Source markdown path")
    parser.add_argument("--mode", default="raw_mode", choices=["raw_mode", "prepared_mode"])
    args = parser.parse_args()

    root = Path(args.project_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Create canonical directories
    for dir_path in CANONICAL_DIRS:
        (root / dir_path).mkdir(parents=True, exist_ok=True)

    # Write manifest
    manifest = {
        "source_path": args.source,
        "mode": args.mode,
        "version": "2.0",
        "created_by": "init_svg_project.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ppt_conversion_allowed": False,
    }
    internal = root / INTERNAL_ROOT

    (internal / "00_project" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write pipeline config
    pipeline_config = {
        "version": "2.0",
        "batch_size": 3,
        "svg_canvas": "1920x1080",
        "review_server_enabled": False,
        "color_source": "wesdom",
        "ppt_conversion_allowed": False,
    }
    (internal / "00_project" / "pipeline_config.json").write_text(
        json.dumps(pipeline_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write empty starter JSON files
    for rel_path, content in STARTER_FILES.items():
        (root / rel_path).write_text(content, encoding="utf-8")

    print(f"Initialized v2 project at: {root.resolve()}")
    print("User-facing deliverables:")
    print("  01_layout_direction.html")
    print("  02_visual_review.html")
    print("  final_deck.pptx")
    print("Internal workspace:")
    for d in CANONICAL_DIRS:
        print(f"  {d}/")
    for rel_path in STARTER_FILES:
        print(f"  {rel_path}")


if __name__ == "__main__":
    main()
