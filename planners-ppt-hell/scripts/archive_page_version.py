import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

MAX_VERSIONS = 5


def archive_page(page_dir: Path, svg_path: Path, png_path: Path, reason: str = "revision"):
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG file not found: {svg_path}")
    if not png_path.exists():
        raise FileNotFoundError(f"PNG file not found: {png_path}")

    page_dir.mkdir(parents=True, exist_ok=True)
    history_path = page_dir / "history.json"

    # Load history
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid history JSON: {history_path}") from exc

    next_ver = len(history) + 1

    # Copy files into version directory
    v_svg = page_dir / f"v{next_ver}.svg"
    v_png = page_dir / f"v{next_ver}.png"
    shutil.copy2(svg_path, v_svg)
    shutil.copy2(png_path, v_png)

    # Append history entry
    entry = {
        "version": next_ver,
        "svg": f"v{next_ver}.svg",
        "png": f"v{next_ver}.png",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    history.append(entry)

    # Prune old material files if over limit
    if len(history) > MAX_VERSIONS:
        to_prune = history[:-MAX_VERSIONS]
        for old in to_prune:
            old_svg = page_dir / old["svg"]
            old_png = page_dir / old["png"]
            if old_svg.exists():
                old_svg.unlink()
            if old_png.exists():
                old_png.unlink()
            old["material_pruned"] = True

    # Write updated history
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Archived v{next_ver} → {page_dir.name} ({len(history)} total, max {MAX_VERSIONS})")


def main():
    parser = argparse.ArgumentParser(description="Archive a page version for before/after comparison.")
    parser.add_argument("versions_dir", help="_internal/05_review/versions/ directory")
    parser.add_argument("page", help="Page name (e.g., page_01)")
    parser.add_argument("svg", help="Current SVG file to archive")
    parser.add_argument("png", help="Current PNG file to archive")
    parser.add_argument("--reason", default="revision", help="Reason for this version")
    args = parser.parse_args()

    page_dir = Path(args.versions_dir) / args.page
    archive_page(page_dir, Path(args.svg), Path(args.png), args.reason)


if __name__ == "__main__":
    main()
