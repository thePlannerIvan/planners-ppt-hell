import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path


PLAYWRIGHT_SNIPPET = r'''
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys

out_dir = Path(sys.argv[1])
svg_files = [Path(p) for p in sys.argv[2:]]
out_dir.mkdir(parents=True, exist_ok=True)
written = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    for svg in svg_files:
        out_file = out_dir / f"{svg.stem}.png"
        page.goto(svg.resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(out_file), omit_background=False)
        written.append(str(out_file))
    browser.close()

print("\n".join(written))
'''


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def get_batch_pages(manifest, batch_id):
    batch_config = manifest.get("batch_config", {})
    if batch_id not in batch_config:
        raise SystemExit(f"batch '{batch_id}' not found in page_manifest.json")
    batch = batch_config[batch_id]
    if not isinstance(batch, dict) or not isinstance(batch.get("pages"), list):
        raise SystemExit(f"batch_config.{batch_id}.pages must be a list")
    return batch["pages"]


def select_svg_files(svg_dir, manifest_path="", batch_id=""):
    svg_root = Path(svg_dir)
    if not manifest_path:
        return sorted(svg_root.glob("*.svg"))

    manifest = load_json(manifest_path)
    if not manifest:
        raise SystemExit(f"Could not read manifest: {manifest_path}")

    wanted_keys = set(get_batch_pages(manifest, batch_id)) if batch_id else {
        p.get("page_key") for p in manifest.get("pages", []) if isinstance(p, dict)
    }
    files = []
    for page in manifest.get("pages", []):
        if not isinstance(page, dict) or page.get("page_key") not in wanted_keys:
            continue
        svg_path = page.get("svg_path", "")
        if not svg_path:
            continue
        fp = Path(manifest_path).resolve().parents[2] / svg_path
        if not fp.exists():
            fallback = svg_root / Path(svg_path).name
            fp = fallback
        files.append(fp)
    return files


def png_dimensions(path):
    p = Path(path)
    try:
        with p.open("rb") as f:
            header = f.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None, None
        width, height = struct.unpack(">II", header[16:24])
        return width, height
    except Exception:
        return None, None


def update_manifest_png_paths(manifest_path, written_files):
    manifest_file = Path(manifest_path)
    manifest = load_json(manifest_file)
    if not manifest:
        return
    by_stem = {Path(p).stem: p for p in written_files}
    project_root = manifest_file.resolve().parents[2]
    changed = False
    for page in manifest.get("pages", []):
        if not isinstance(page, dict):
            continue
        key = page.get("page_key", "")
        if key not in by_stem:
            continue
        try:
            page["png_path"] = str(Path(by_stem[key]).resolve().relative_to(project_root))
        except ValueError:
            page["png_path"] = str(Path(by_stem[key]))
        changed = True
    if changed:
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Render SVG files to PNG previews. Requires playwright installed with a browser runtime."
    )
    parser.add_argument("svg_dir", help="Directory containing SVG files")
    parser.add_argument("png_dir", help="Output directory for PNG previews")
    parser.add_argument("--manifest", default="", help="Optional _internal/00_project/page_manifest.json")
    parser.add_argument("--batch", default="", help="Optional batch_id from page_manifest.json")
    parser.add_argument("--update-manifest", action="store_true", help="Update png_path for rendered pages")
    args = parser.parse_args()

    svg_files = select_svg_files(args.svg_dir, args.manifest, args.batch)
    svg_files = [Path(f) for f in svg_files if Path(f).exists()]
    if not svg_files:
        raise SystemExit("No SVG files found to render.")

    png_dir = Path(args.png_dir)
    cmd = [sys.executable, "-c", PLAYWRIGHT_SNIPPET, str(png_dir), *[str(f) for f in svg_files]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(
            "Playwright render failed. Install `playwright` and run `playwright install chromium`, "
            "or replace this script with your team renderer.\n"
        )
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)

    written = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    files_meta = []
    for out_path in written:
        p = Path(out_path)
        w, h = png_dimensions(p)
        files_meta.append({
            "file": str(p),
            "width": w,
            "height": h,
            "bytes": p.stat().st_size if p.exists() else 0,
            "valid_size": w == 1920 and h == 1080,
        })

    if args.update_manifest and args.manifest:
        update_manifest_png_paths(args.manifest, written)

    manifest = {
        "png_dir": str(png_dir),
        "batch": args.batch,
        "generated_files": written,
        "files": files_meta,
        "count": len(written),
        "all_valid_size": all(f["valid_size"] for f in files_meta),
    }
    png_dir.mkdir(parents=True, exist_ok=True)
    (png_dir / "png_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
