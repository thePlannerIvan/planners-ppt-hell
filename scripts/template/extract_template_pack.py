#!/usr/bin/env python3
"""
One-Step Multimodal Template Preprocessor (`extract_template_pack.py`).

Replaces the legacy split between `prepare_visual_references.py` and the
1,251-line `extract_template_assets.py`.

Given a `.pptx`, `.pdf`, or directory of slide images:
1. Renders/normalizes full-page PNGs (`page_001.png`...) and `contact_sheet.png`
   into `<project>/_internal/00_project/template_visuals/`.
2. When given a `.pptx`:
   - Traverses `slide_masters`, `slide_layouts`, and `slides` (including nested
     group shapes) to extract deduplicated reusable bitmap/vector assets into
     `<project>/_internal/00_project/template_pack/assets/` (separating true
     reusable logos/decorations from full-slide PNG snapshots).
   - Computes actual visible color frequency across slides (resolving both
     `srgbClr` and `schemeClr` via the theme XML map, bucketed into surfaces,
     accents/bars, strokes, and text colors) and flags unused Office default
     theme colors (`#4F81BD` etc.) so they never mislead downstream models.
   - Computes actual visible font-family and font-size distribution across
     slides, normalized to the 1920x1080 canvas coordinate space.
3. Also performs lightweight visual pixel sampling across rendered page PNGs so
   even PDFs and PNG-wrapped PPTX files get accurate canvas/ink/accent hex
   candidates in `extraction_facts.json`.

Usage:
  python3 extract_template_pack.py <source> --project <project_dir> [--dpi 144]
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.oxml.ns import qn
except ImportError:
    Presentation = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


EMU_PER_INCH = 914400
DEFAULT_DPI = 96
TARGET_CANVAS_W = 1920.0
TARGET_CANVAS_H = 1080.0
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}

OFFICE_DEFAULT_ACCENTS = {
    "#4F81BD", "#C0504D", "#9BBB59", "#8064A2", "#4BACC6", "#F79646",
    "#EEECE1", "#1F497D", "#0000FF", "#800080",
}

DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def emu_to_px(emu, dpi=DEFAULT_DPI):
    if emu is None:
        return 0.0
    return round(emu / EMU_PER_INCH * dpi, 1)


def sha256_blob(blob):
    return hashlib.sha256(blob).hexdigest()


def natural_key(path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def hex_to_rgb(hex_str):
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb):
    r, g, b = [max(0, min(255, int(round(v)))) for v in rgb]
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_saturation_and_luma(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    diff = mx - mn
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = 0.0 if mx == 0 else diff / mx
    return sat, luma


# ---------------------------------------------------------------------------
# 1. Visual Rendering (PDF / PPTX / Images -> page_001.png + contact_sheet.png)
# ---------------------------------------------------------------------------

def render_pdf_to_pngs(pdf_path, out_dir, dpi=144, max_pages=0):
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    if fitz is not None:
        doc = fitz.open(str(pdf_path))
        total = len(doc) if max_pages <= 0 else min(len(doc), max_pages)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for idx in range(total):
            pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
            out_file = out_dir / f"page_{idx + 1:03d}.png"
            pix.save(str(out_file))
            pages.append(out_file)
        doc.close()
        return pages

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("Neither PyMuPDF (fitz) nor pdftoppm is available to render PDF pages.")
    prefix = out_dir / "_pdf_page"
    cmd = [pdftoppm, "-png", "-r", str(dpi)]
    if max_pages > 0:
        cmd.extend(["-f", "1", "-l", str(max_pages)])
    cmd.extend([str(pdf_path), str(prefix)])
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {(res.stderr or res.stdout).strip()}")
    generated = sorted(out_dir.glob("_pdf_page-*.png"), key=natural_key)
    for idx, raw in enumerate(generated, start=1):
        out_file = out_dir / f"page_{idx:03d}.png"
        raw.replace(out_file)
        pages.append(out_file)
    return pages


def extract_full_slide_images_if_wrapper_pptx(prs, out_dir):
    """
    If every slide (or >=90% of slides) in a PPTX is simply a full-bleed bitmap
    snapshot (like Mizuno_Proposal_Deck_Final.pptx), extract those bitmaps directly
    as page_001.png..page_NNN.png without needing LibreOffice!
    """
    if len(prs.slides) == 0:
        return []
    cw = emu_to_px(prs.slide_width)
    ch = emu_to_px(prs.slide_height)
    c_area = cw * ch if cw and ch else 1.0

    slide_blobs = []
    for slide in prs.slides:
        full_pic = None
        for shape in slide.shapes:
            if shape.shape_type == 13:  # Picture
                sw = emu_to_px(shape.width)
                sh = emu_to_px(shape.height)
                if (sw * sh) / c_area >= 0.85:
                    try:
                        full_pic = shape.image.blob
                        break
                    except Exception:
                        pass
        slide_blobs.append(full_pic)

    valid_count = sum(1 for b in slide_blobs if b is not None)
    if valid_count < max(1, int(len(prs.slides) * 0.9)):
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for idx, blob in enumerate(slide_blobs, start=1):
        if blob is None:
            continue
        out_file = out_dir / f"page_{idx:03d}.png"
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
            tmp.write(blob)
            tmp_path = Path(tmp.name)
        try:
            im = Image.open(tmp_path).convert("RGB")
            im.save(out_file, "PNG")
            pages.append(out_file)
        finally:
            tmp_path.unlink(missing_ok=True)
    return pages


def render_pptx_to_pngs(pptx_path, prs, out_dir, dpi=144, max_pages=0):
    # Fast path: wrapper PPTX where slides are full-slide PNGs
    wrapper_pages = extract_full_slide_images_if_wrapper_pptx(prs, out_dir)
    if wrapper_pages:
        if max_pages > 0:
            for extra in wrapper_pages[max_pages:]:
                extra.unlink(missing_ok=True)
            wrapper_pages = wrapper_pages[:max_pages]
        return wrapper_pages, "direct_full_slide_bitmap"

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return [], "unavailable_no_soffice"

    with tempfile.TemporaryDirectory(prefix="ppt_hell_soffice_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        user_profile = (tmp_path / "lo_profile").as_uri()
        cmd = [
            soffice,
            f"-env:UserInstallation={user_profile}",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(tmp_path),
            str(pptx_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        pdf_candidates = list(tmp_path.glob("*.pdf"))
        if res.returncode != 0 or not pdf_candidates:
            return [], f"soffice_failed: {(res.stderr or res.stdout).strip()[:200]}"
        pages = render_pdf_to_pngs(pdf_candidates[0], out_dir, dpi=dpi, max_pages=max_pages)
        return pages, "soffice_pdf_to_png"


def write_contact_sheet_png(page_paths, output_path):
    if not page_paths:
        return None
    cell_w, cell_h, columns = 480, 310, 3
    rows = max(1, (len(page_paths) + columns - 1) // columns)
    canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), "#F4F6F8")
    draw = ImageDraw.Draw(canvas)
    for index, page_path in enumerate(page_paths):
        image = Image.open(page_path).convert("RGB")
        image.thumbnail((cell_w - 32, cell_h - 58))
        x0 = (index % columns) * cell_w
        y0 = (index // columns) * cell_h
        x = x0 + (cell_w - image.width) // 2
        y = y0 + 16
        draw.rounded_rectangle(
            (x0 + 8, y0 + 8, x0 + cell_w - 8, y0 + cell_h - 8),
            radius=8, fill="#FFFFFF", outline="#D6DCE4", width=2,
        )
        canvas.paste(image, (x, y))
        draw.text((x0 + 16, y0 + cell_h - 34), f"{index + 1:03d} · {page_path.name}", fill="#3B4652")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path


# ---------------------------------------------------------------------------
# 2. Visual Pixel Color Sampling (Works on ALL inputs: PDF, PNG-PPTX, Native PPTX)
# ---------------------------------------------------------------------------

def sample_visual_palette_from_pages(page_paths, max_sample_pages=24):
    """
    Quantize & bucket actual rendered slide pixels across pages into:
      - dominant_backgrounds (light/dark canvas & card surfaces)
      - dominant_ink_colors (dark/light text & dark banner fills)
      - dominant_accent_colors (saturated brand colors like #E60012 or #0066CC)
    """
    if not page_paths:
        return {}

    bg_counter = Counter()
    ink_counter = Counter()
    accent_counter = Counter()
    accent_pages = defaultdict(set)

    sampled_paths = page_paths[:max_sample_pages]
    for idx, p in enumerate(sampled_paths, start=1):
        try:
            im = Image.open(p).convert("RGB").resize((240, 135), Image.Resampling.BILINEAR)
        except Exception:
            continue
        pixels = list(im.getdata())
        page_accents_seen = Counter()
        for r, g, b in pixels:
            # Quantize to 4-unit steps for acc, 8-unit steps for neutral
            sat, luma = rgb_saturation_and_luma((r, g, b))
            if sat >= 0.38 and 0.08 <= luma <= 0.88:
                qr, qg, qb = (r // 4) * 4, (g // 4) * 4, (b // 4) * 4
                hx = rgb_to_hex((qr, qg, qb))
                accent_counter[hx] += 1
                page_accents_seen[hx] += 1
            elif luma >= 0.85:
                qr, qg, qb = (r // 4) * 4, (g // 4) * 4, (b // 4) * 4
                bg_counter[rgb_to_hex((qr, qg, qb))] += 1
            elif luma <= 0.22:
                qr, qg, qb = (r // 4) * 4, (g // 4) * 4, (b // 4) * 4
                ink_counter[rgb_to_hex((qr, qg, qb))] += 1

        for hx, cnt in page_accents_seen.items():
            if cnt >= 15:  # At least ~0.05% of slide pixels
                accent_pages[hx].add(idx)

    def merge_nearby_colors(counter, page_map=None, dist_thresh=24, top_k=6):
        clusters = []
        for hx, count in counter.most_common(60):
            rgb = hex_to_rgb(hx)
            merged = False
            for c in clusters:
                crgb = c["rgb"]
                dist = ((rgb[0] - crgb[0]) ** 2 + (rgb[1] - crgb[1]) ** 2 + (rgb[2] - crgb[2]) ** 2) ** 0.5
                if dist <= dist_thresh:
                    c["count"] += count
                    if page_map and hx in page_map:
                        c["pages"].update(page_map[hx])
                    merged = True
                    break
            if not merged:
                clusters.append({
                    "hex": hx,
                    "rgb": rgb,
                    "count": count,
                    "pages": set(page_map[hx]) if (page_map and hx in page_map) else set(),
                })
        clusters.sort(key=lambda x: (len(x["pages"]), x["count"]), reverse=True)
        out = []
        for c in clusters[:top_k]:
            item = {"hex": c["hex"], "pixel_weight": c["count"]}
            if page_map is not None:
                item["page_count"] = len(c["pages"])
                item["sample_pages"] = sorted(c["pages"])[:10]
            out.append(item)
        return out

    return {
        "sampled_page_count": len(sampled_paths),
        "dominant_light_surfaces": merge_nearby_colors(bg_counter, dist_thresh=16, top_k=5),
        "dominant_dark_ink_or_surfaces": merge_nearby_colors(ink_counter, dist_thresh=20, top_k=5),
        "dominant_saturated_accents": merge_nearby_colors(accent_counter, page_map=accent_pages, dist_thresh=28, top_k=6),
    }


# ---------------------------------------------------------------------------
# 3. Deep PPTX Inspection (Masters + Layouts + Slides, Visible Colors & Fonts)
# ---------------------------------------------------------------------------

def _parse_theme_scheme_map(pptx_path):
    """
    Parse ppt/theme/theme1.xml into a dict mapping schemeClr names
    (dk1, lt1, dk2, lt2, accent1..6, tx1, tx2, bg1, bg2) to #RRGGBB.
    """
    scheme = {}
    try:
        with zipfile.ZipFile(str(pptx_path), "r") as z:
            theme_files = sorted([f for f in z.namelist() if f.startswith("ppt/theme/") and f.endswith(".xml")])
            for tf in theme_files:
                root = ET.fromstring(z.read(tf))
                clr_scheme = root.find(f".//{{{DRAWINGML_NS}}}clrScheme")
                if clr_scheme is None:
                    continue
                for child in list(clr_scheme):
                    tag = child.tag.split("}")[-1]
                    srgb = child.find(f"{{{DRAWINGML_NS}}}srgbClr")
                    sys_clr = child.find(f"{{{DRAWINGML_NS}}}sysClr")
                    if srgb is not None and srgb.get("val"):
                        scheme[tag] = "#" + srgb.get("val").upper()
                    elif sys_clr is not None and sys_clr.get("lastClr"):
                        scheme[tag] = "#" + sys_clr.get("lastClr").upper()
                break
    except Exception:
        pass
    # Standard aliases used in DrawingML
    if "dk1" in scheme:
        scheme.setdefault("tx1", scheme["dk1"])
    if "lt1" in scheme:
        scheme.setdefault("bg1", scheme["lt1"])
    if "dk2" in scheme:
        scheme.setdefault("tx2", scheme["dk2"])
    if "lt2" in scheme:
        scheme.setdefault("bg2", scheme["lt2"])
    return scheme


def _apply_color_mods(hex_val, clr_el):
    """Apply basic DrawingML lumMod / lumOff / tint / shade to a resolved hex color."""
    if not hex_val:
        return None
    r, g, b = hex_to_rgb(hex_val)
    lum_mod = clr_el.find(f"{{{DRAWINGML_NS}}}lumMod")
    lum_off = clr_el.find(f"{{{DRAWINGML_NS}}}lumOff")
    tint = clr_el.find(f"{{{DRAWINGML_NS}}}tint")
    shade = clr_el.find(f"{{{DRAWINGML_NS}}}shade")
    if lum_mod is not None and lum_mod.get("val"):
        factor = int(lum_mod.get("val")) / 100000.0
        r, g, b = r * factor, g * factor, b * factor
    if lum_off is not None and lum_off.get("val"):
        offset = (int(lum_off.get("val")) / 100000.0) * 255.0
        r, g, b = r + offset, g + offset, b + offset
    if tint is not None and tint.get("val"):
        t = int(tint.get("val")) / 100000.0
        r, g, b = r + (255 - r) * (1 - t), g + (255 - g) * (1 - t), b + (255 - b) * (1 - t)
    if shade is not None and shade.get("val"):
        s = int(shade.get("val")) / 100000.0
        r, g, b = r * s, g * s, b * s
    return rgb_to_hex((r, g, b))


def _resolve_color_from_xml_node(node, scheme_map):
    """Resolve `<a:solidFill>` or similar node containing `srgbClr` or `schemeClr`."""
    if node is None:
        return None
    srgb = node.find(f".//{{{DRAWINGML_NS}}}srgbClr")
    if srgb is not None and srgb.get("val"):
        return _apply_color_mods("#" + srgb.get("val").upper(), srgb)
    sc = node.find(f".//{{{DRAWINGML_NS}}}schemeClr")
    if sc is not None and sc.get("val"):
        base = scheme_map.get(sc.get("val"))
        if base:
            return _apply_color_mods(base, sc)
    return None


def _iter_shapes_recursive(shapes):
    """Yield all shapes including children inside group shapes."""
    for shape in shapes:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            try:
                yield from _iter_shapes_recursive(shape.shapes)
            except Exception:
                pass


def _image_ext_from_content_type(content_type):
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    return mapping.get(content_type, ".bin")


def extract_pptx_facts_and_assets(pptx_path, prs, pack_assets_dir):
    pack_assets_dir.mkdir(parents=True, exist_ok=True)
    scheme_map = _parse_theme_scheme_map(pptx_path)

    canvas_w_px = emu_to_px(prs.slide_width) or 960.0
    canvas_h_px = emu_to_px(prs.slide_height) or 540.0
    canvas_area = max(1.0, canvas_w_px * canvas_h_px)
    scale_to_1080p = round(TARGET_CANVAS_W / canvas_w_px, 4)

    # 1) Traverse slide_masters + slide_layouts + slides for bitmap/SVG assets
    sha_records = {}
    counters = {"logo": 0, "deco": 0, "bg": 0, "content": 0}

    def record_picture(shape, origin_kind, origin_index):
        if shape.shape_type != 13:
            return
        try:
            img = shape.image
            blob = img.blob
            if not blob:
                return
        except Exception:
            return
        sha = sha256_blob(blob)
        sx = round(emu_to_px(shape.left) * scale_to_1080p, 1)
        sy = round(emu_to_px(shape.top) * scale_to_1080p, 1)
        sw = round(emu_to_px(shape.width) * scale_to_1080p, 1)
        sh = round(emu_to_px(shape.height) * scale_to_1080p, 1)
        area_ratio = (sw * sh) / (TARGET_CANVAS_W * TARGET_CANVAS_H)
        ext = _image_ext_from_content_type(getattr(img, "content_type", "image/png"))

        if sha not in sha_records:
            sha_records[sha] = {
                "sha256": sha[:16],
                "ext": ext,
                "blob": blob,
                "origins": [],
                "slide_pages": [],
                "geometries_1080p": [],
                "area_ratio": round(area_ratio, 4),
            }
        sha_records[sha]["origins"].append(f"{origin_kind}:{origin_index}")
        if origin_kind == "slide":
            sha_records[sha]["slide_pages"].append(origin_index)
        sha_records[sha]["geometries_1080p"].append({"x": sx, "y": sy, "width": sw, "height": sh})

    for m_idx, master in enumerate(prs.slide_masters, start=1):
        for sh in _iter_shapes_recursive(master.shapes):
            record_picture(sh, "master", m_idx)
        for l_idx, layout in enumerate(master.slide_layouts, start=1):
            for sh in _iter_shapes_recursive(layout.shapes):
                record_picture(sh, f"master{m_idx}_layout", l_idx)

    for s_idx, slide in enumerate(prs.slides, start=1):
        for sh in _iter_shapes_recursive(slide.shapes):
            record_picture(sh, "slide", s_idx)

    reusable_assets = []
    full_bleed_snapshot_count = 0
    content_image_count = 0

    for sha, rec in sha_records.items():
        from_master_or_layout = any(not o.startswith("slide:") for o in rec["origins"])
        slide_count = len(set(rec["slide_pages"]))
        ar = rec["area_ratio"]
        is_full_bleed = ar >= 0.85

        if is_full_bleed and not from_master_or_layout and slide_count == 1:
            # This is a single-slide full-page screenshot wrapper, NOT a reusable template asset
            full_bleed_snapshot_count += 1
            continue

        if from_master_or_layout or slide_count >= 2:
            if is_full_bleed:
                counters["bg"] += 1
                role = "reusable_background"
                asset_id = f"bg_{counters['bg']:02d}"
            elif ar <= 0.12:
                counters["logo"] += 1
                role = "logo_or_badge"
                asset_id = f"logo_{counters['logo']:02d}"
            else:
                counters["deco"] += 1
                role = "reusable_decoration"
                asset_id = f"deco_{counters['deco']:02d}"

            fname = f"{asset_id}{rec['ext']}"
            (pack_assets_dir / fname).write_bytes(rec["blob"])
            reusable_assets.append({
                "asset_id": asset_id,
                "file": f"assets/{fname}",
                "role": role,
                "from_master_or_layout": from_master_or_layout,
                "slide_occurrences": slide_count,
                "slide_pages": sorted(set(rec["slide_pages"]))[:15],
                "geometry_1080p": rec["geometries_1080p"][0],
                "sha256_prefix": rec["sha256"],
            })
        else:
            content_image_count += 1

    # 2) Compute ACTUAL visible color & font distributions across slides
    surface_fills = Counter()
    surface_pages = defaultdict(set)
    accent_fills = Counter()
    accent_pages = defaultdict(set)
    stroke_colors = Counter()
    stroke_pages = defaultdict(set)
    text_colors = Counter()
    text_color_pages = defaultdict(set)

    font_families = Counter()
    font_size_buckets = defaultdict(lambda: {"run_count": 0, "char_count": 0, "pages": set(), "examples": []})
    total_native_shapes = 0

    for s_idx, slide in enumerate(prs.slides, start=1):
        # Check slide background fill if explicitly set
        bg_fill = _resolve_color_from_xml_node(slide.element.find(f".//{{{DRAWINGML_NS}}}solidFill"), scheme_map)
        if bg_fill:
            surface_fills[bg_fill] += 1
            surface_pages[bg_fill].add(s_idx)

        for sh in _iter_shapes_recursive(slide.shapes):
            total_native_shapes += 1
            sw = emu_to_px(sh.width)
            sh_h = emu_to_px(sh.height)
            area_ratio = (sw * sh_h) / canvas_area

            # Shape solidFill (direct child of spPr)
            spPr = sh.element.find(qn("p:spPr"))
            if spPr is not None:
                solid = spPr.find(qn("a:solidFill"))
                fill_hex = _resolve_color_from_xml_node(solid, scheme_map)
                if fill_hex:
                    sat, _ = rgb_saturation_and_luma(hex_to_rgb(fill_hex))
                    if area_ratio >= 0.03 and sat < 0.35:
                        surface_fills[fill_hex] += 1
                        surface_pages[fill_hex].add(s_idx)
                    else:
                        accent_fills[fill_hex] += 1
                        accent_pages[fill_hex].add(s_idx)

                ln = spPr.find(qn("a:ln"))
                if ln is not None:
                    ln_solid = ln.find(qn("a:solidFill"))
                    stroke_hex = _resolve_color_from_xml_node(ln_solid, scheme_map)
                    if stroke_hex:
                        stroke_colors[stroke_hex] += 1
                        stroke_pages[stroke_hex].add(s_idx)

            # Text runs
            if getattr(sh, "has_text_frame", False):
                for para in sh.text_frame.paragraphs:
                    for run in para.runs:
                        txt = (run.text or "").strip()
                        if not txt:
                            continue
                        char_len = len(txt)
                        rPr = run._r.find(qn("a:rPr"))
                        # Text color
                        t_hex = None
                        if rPr is not None:
                            t_solid = rPr.find(qn("a:solidFill"))
                            t_hex = _resolve_color_from_xml_node(t_solid, scheme_map)
                        if t_hex:
                            text_colors[t_hex] += char_len
                            text_color_pages[t_hex].add(s_idx)

                        # Font family
                        ff = run.font.name
                        if not ff and rPr is not None:
                            ea = rPr.find(qn("a:ea"))
                            latin = rPr.find(qn("a:latin"))
                            if ea is not None and ea.get("typeface"):
                                ff = ea.get("typeface")
                            elif latin is not None and latin.get("typeface"):
                                ff = latin.get("typeface")
                        if ff:
                            font_families[ff] += char_len

                        # Font size
                        sz_pt = None
                        if run.font.size is not None:
                            sz_pt = round(run.font.size.pt, 1)
                        elif rPr is not None and rPr.get("sz"):
                            try:
                                sz_pt = round(int(rPr.get("sz")) / 100.0, 1)
                            except Exception:
                                pass
                        if sz_pt is not None:
                            px_1080p = round((sz_pt * 96.0 / 72.0) * scale_to_1080p, 1)
                            bucket_key = f"{px_1080p:.0f}px (raw {sz_pt:g}pt)"
                            b = font_size_buckets[bucket_key]
                            b["px_1080p"] = round(px_1080p)
                            b["raw_pt"] = sz_pt
                            b["run_count"] += 1
                            b["char_count"] += char_len
                            b["pages"].add(s_idx)
                            if len(b["examples"]) < 3 and len(txt) >= 2:
                                snippet = txt[:28]
                                if snippet not in b["examples"]:
                                    b["examples"].append(snippet)

    # Check if theme1.xml colors are actually used or just Office default zombies
    all_used_hexes = set(surface_fills) | set(accent_fills) | set(stroke_colors) | set(text_colors)
    theme_accents = {scheme_map.get(f"accent{i}") for i in range(1, 7) if scheme_map.get(f"accent{i}")}
    unused_theme_accents = sorted(theme_accents - all_used_hexes)
    is_office_default_theme = bool(theme_accents & OFFICE_DEFAULT_ACCENTS) and len(unused_theme_accents) >= 4

    def format_color_ranking(counter, pages_map, top_k=10):
        items = []
        for hx, weight in counter.most_common(top_k):
            items.append({
                "hex": hx,
                "slide_count": len(pages_map[hx]),
                "weight": weight,
                "sample_slides": sorted(pages_map[hx])[:10],
            })
        items.sort(key=lambda x: (x["slide_count"], x["weight"]), reverse=True)
        return items

    typography_tiers = []
    for key, info in sorted(font_size_buckets.items(), key=lambda kv: kv[1].get("px_1080p", 0), reverse=True):
        typography_tiers.append({
            "size_label": key,
            "px_1080p": info.get("px_1080p"),
            "raw_pt": info.get("raw_pt"),
            "slide_count": len(info["pages"]),
            "run_count": info["run_count"],
            "char_count": info["char_count"],
            "examples": info["examples"],
        })

    return {
        "slide_count": len(prs.slides),
        "master_count": len(prs.slide_masters),
        "source_canvas_px": f"{int(canvas_w_px)}x{int(canvas_h_px)}",
        "normalized_target_canvas_px": "1920x1080",
        "scale_factor_to_1080p": scale_to_1080p,
        "total_native_shapes": total_native_shapes,
        "is_full_slide_bitmap_wrapper": full_bleed_snapshot_count >= max(1, int(len(prs.slides) * 0.8)),
        "full_slide_bitmap_count": full_bleed_snapshot_count,
        "single_slide_content_image_count": content_image_count,
        "reusable_assets": reusable_assets,
        "theme_xml_diagnostics": {
            "theme_scheme_map": scheme_map,
            "unused_theme_accents": unused_theme_accents,
            "theme_xml_is_unused_office_default": is_office_default_theme,
            "warning": (
                "Theme XML contains unused Office default colors (#4F81BD/#C0504D/#9BBB59). "
                "Ignore theme1.xml and use `visible_color_stats` + `visual_palette_sampling`!"
                if is_office_default_theme else "Theme XML inspected."
            ),
        },
        "visible_color_stats": {
            "surfaces_and_backgrounds": format_color_ranking(surface_fills, surface_pages, top_k=8),
            "accents_bars_and_badges": format_color_ranking(accent_fills, accent_pages, top_k=10),
            "text_colors": format_color_ranking(text_colors, text_color_pages, top_k=8),
            "stroke_and_line_colors": format_color_ranking(stroke_colors, stroke_pages, top_k=8),
        },
        "visible_typography_stats": {
            "font_families_by_char_count": [
                {"font_family": ff, "char_count": cnt}
                for ff, cnt in font_families.most_common(8)
            ],
            "font_size_tiers_1080p": typography_tiers[:15],
        },
    }


# ---------------------------------------------------------------------------
# Main One-Step Preprocessor Entrypoint
# ---------------------------------------------------------------------------

def run_extract_template_pack(source, project, output_visuals=None, dpi=144, max_pages=0):
    source_path = Path(source).resolve()
    project_path = Path(project).resolve()
    if not source_path.exists():
        raise RuntimeError(f"Source path does not exist: {source_path}")

    visuals_dir = Path(output_visuals).resolve() if output_visuals else (
        project_path / "_internal" / "00_project" / "template_visuals"
    )
    pack_dir = project_path / "_internal" / "00_project" / "template_pack"
    assets_dir = pack_dir / "assets"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    pack_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    for old in visuals_dir.glob("page_*"):
        if old.is_file():
            old.unlink()

    suffix = source_path.suffix.lower()
    pages = []
    render_method = ""
    pptx_facts = None

    if source_path.is_dir():
        img_files = sorted(
            [p for p in source_path.iterdir() if p.is_file() and p.suffix.lower() in RASTER_SUFFIXES],
            key=natural_key,
        )
        if not img_files:
            raise RuntimeError(f"No raster images found in directory: {source_path}")
        if max_pages > 0:
            img_files = img_files[:max_pages]
        for idx, img_p in enumerate(img_files, start=1):
            dest = visuals_dir / f"page_{idx:03d}.png"
            Image.open(img_p).convert("RGB").save(dest, "PNG")
            pages.append(dest)
        render_method = "image_directory_copy"

    elif suffix == ".pdf":
        pages = render_pdf_to_pngs(source_path, visuals_dir, dpi=dpi, max_pages=max_pages)
        render_method = "pdf_to_png"

    elif suffix == ".pptx":
        if Presentation is None:
            raise RuntimeError("python-pptx is required to process .pptx files.")
        prs = Presentation(str(source_path))
        pptx_facts = extract_pptx_facts_and_assets(source_path, prs, assets_dir)
        pages, render_method = render_pptx_to_pngs(source_path, prs, visuals_dir, dpi=dpi, max_pages=max_pages)

    elif suffix in RASTER_SUFFIXES:
        dest = visuals_dir / "page_001.png"
        Image.open(source_path).convert("RGB").save(dest, "PNG")
        pages = [dest]
        render_method = "single_raster_image"
    else:
        raise RuntimeError(f"Unsupported input type: {source_path}")

    contact_sheet = write_contact_sheet_png(pages, visuals_dir / "contact_sheet.png")
    visual_palette = sample_visual_palette_from_pages(pages)

    page_entries = []
    for idx, p in enumerate(pages, start=1):
        with Image.open(p) as im:
            w, h = im.size
        page_entries.append({"page": idx, "image": p.name, "width_px": w, "height_px": h})

    visual_manifest = {
        "source_file": str(source_path),
        "input_type": "image_directory" if source_path.is_dir() else suffix.lstrip("."),
        "render_method": render_method,
        "page_count": len(page_entries),
        "pages": page_entries,
        "contact_sheet": "contact_sheet.png" if contact_sheet else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (visuals_dir / "visual_manifest.json").write_text(
        json.dumps(visual_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    extraction_facts = {
        "schema_version": "multimodal-template-pack-v1",
        "source_file": str(source_path),
        "input_type": visual_manifest["input_type"],
        "render_method": render_method,
        "visuals_dir": str(visuals_dir),
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "rendered_page_count": len(page_entries),
        "visual_palette_sampling": visual_palette,
        "pptx_structural_facts": pptx_facts,
        "next_step_instruction": (
            "Step 2 (Multimodal Synthesis): View `contact_sheet.png` and representative `page_NNN.png` files "
            "alongside `visual_palette_sampling` and `pptx_structural_facts`. Then author the 4-piece Template Pack "
            "(`tokens.css`, `skyline_shell.svg`, `primitives/*.svg`, `SPEC.md` + `anchors/`)."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    facts_path = pack_dir / "extraction_facts.json"
    facts_path.write_text(json.dumps(extraction_facts, ensure_ascii=False, indent=2), encoding="utf-8")
    return facts_path


def main():
    parser = argparse.ArgumentParser(description="One-step multimodal template preprocessor")
    parser.add_argument("source", help="Path to .pptx, .pdf, or directory of slide images")
    parser.add_argument("--project", required=True, help="Target project root directory")
    parser.add_argument("--output-visuals", help="Optional custom directory for rendered visuals")
    parser.add_argument("--dpi", type=int, default=144, help="Rendering DPI for PDF/PPTX (default: 144)")
    parser.add_argument("--max-pages", type=int, default=0, help="Optional limit on pages to render (0 = all)")
    args = parser.parse_args()

    try:
        facts_path = run_extract_template_pack(
            args.source,
            args.project,
            output_visuals=args.output_visuals,
            dpi=args.dpi,
            max_pages=args.max_pages,
        )
        print(str(facts_path))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
