import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canvas_frame import FRAME_H_INT, FRAME_W_INT  # noqa: E402


PLAYWRIGHT_SNIPPET = r'''
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys

sys.path.insert(0, __CANVAS_FRAME_DIR__)
from canvas_frame import FRAME_H_INT, FRAME_W_INT

out_dir = Path(sys.argv[1])
svg_files = [Path(p) for p in sys.argv[2:]]
out_dir.mkdir(parents=True, exist_ok=True)
written = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": FRAME_W_INT, "height": FRAME_H_INT})
    for svg in svg_files:
        out_file = out_dir / f"{svg.stem}.png"
        page.goto(svg.resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(out_file), omit_background=False)
        written.append(str(out_file))
    browser.close()

print("\n".join(written))
'''.replace("__CANVAS_FRAME_DIR__", repr(str(Path(__file__).resolve().parent)))


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def select_svg_files(svg_dir, manifest_path=""):
    svg_root = Path(svg_dir)
    if not manifest_path:
        return sorted(svg_root.glob("*.svg"))

    manifest = load_json(manifest_path)
    if not manifest:
        raise SystemExit(f"Could not read manifest: {manifest_path}")

    wanted_keys = {
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


def make_contact_sheet(written_files, output_path):
    if not written_files:
        return ""
    thumb_w, thumb_h, gap, label_h = 600, 338, 30, 44
    cols = min(3, len(written_files))
    rows = (len(written_files) + cols - 1) // cols
    canvas_w = gap + cols * (thumb_w + gap)
    canvas = Image.new("RGB", (canvas_w, gap + rows * (thumb_h + label_h + gap)), "#EEF2F6")
    draw = ImageDraw.Draw(canvas)
    for index, file_path in enumerate(written_files):
        image = Image.open(file_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = gap + (index % cols) * (thumb_w + gap)
        y = gap + (index // cols) * (thumb_h + label_h + gap) + label_h
        canvas.paste(image, (x, y))
        draw.text((x, y - label_h + 10), Path(file_path).stem, fill="#1F2933")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Render SVG files to PNG previews. Requires playwright installed with a browser runtime."
    )
    parser.add_argument("svg_dir", help="Directory containing SVG files")
    parser.add_argument("png_dir", help="Output directory for PNG previews")
    parser.add_argument("--manifest", default="", help="Optional _internal/00_project/page_manifest.json")
    parser.add_argument("--update-manifest", action="store_true", help="Update png_path for rendered pages")
    parser.add_argument("--contact-sheet-only", action="store_true", help="Rebuild the full-deck contact sheet from existing page PNGs")
    args = parser.parse_args()

    png_dir = Path(args.png_dir)
    if args.contact_sheet_only:
        existing = sorted((png_dir / "pages").glob("*.png"))
        if not existing:
            raise SystemExit("No existing page PNGs found for contact sheet.")
        contact_sheet = make_contact_sheet(existing, png_dir / "full_deck_contact_sheet.png")
        print(json.dumps({"count": len(existing), "contact_sheet": contact_sheet}, ensure_ascii=False, indent=2))
        return

    svg_files = select_svg_files(args.svg_dir, args.manifest)
    svg_files = [Path(f) for f in svg_files if Path(f).exists()]
    if not svg_files:
        raise SystemExit("No SVG files found to render.")

    pages_dir = png_dir / "pages"
    cmd = [sys.executable, "-c", PLAYWRIGHT_SNIPPET, str(pages_dir), *[str(f) for f in svg_files]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(
            "Playwright render failed. Install `playwright` and run `playwright install chromium`, "
            "or replace this script with your team renderer.\n"
        )
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)

    written = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    contact_sheet = make_contact_sheet(written, png_dir / "full_deck_contact_sheet.png")
    def portable(path):
        try:
            return str(Path(path).resolve().relative_to(png_dir.resolve()))
        except ValueError:
            return Path(path).name

    files_meta = []
    for out_path in written:
        p = Path(out_path)
        w, h = png_dimensions(p)
        files_meta.append({
            "file": portable(p),
            "width": w,
            "height": h,
            "bytes": p.stat().st_size if p.exists() else 0,
            "valid_size": w == FRAME_W_INT and h == FRAME_H_INT,
        })

    if args.update_manifest and args.manifest:
        update_manifest_png_paths(args.manifest, written)

    manifest = {
        "png_dir": ".",
        "generated_files": [portable(path) for path in written],
        "files": files_meta,
        "count": len(written),
        "all_valid_size": all(f["valid_size"] for f in files_meta),
        "contact_sheet": portable(contact_sheet),
    }
    png_dir.mkdir(parents=True, exist_ok=True)
    (png_dir / "png_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
