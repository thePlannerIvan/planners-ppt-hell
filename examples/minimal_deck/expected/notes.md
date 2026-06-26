# Expected Output Notes

This example generates a 3-page deck from a short product review brief. No network access required.

## Pipeline Flow

The expected fixture files in this directory demonstrate the correct contract shapes at each stage:

1. `page_content.json` — full copy for all 3 pages (action titles, core messages, body blocks, tables, speaker notes)
2. `layout_plan.json` — layout decisions with wireframes, copy handling, rationale, and suggestions
3. `page_manifest.json` — production state tracking with batch config

## Contract Validation

Running `validate_project_contracts.py` on a project initialized with these fixtures should:
- Pass all cross-contract page_key checks
- Pass all required-field checks
- Pass sequential key ordering (page_01, page_02, page_03)
- Detect missing wireframe or empty copy if contracts are broken

## Failure Mode Reproduction

The following intentional contract breaks should cause validation failures:

| Break | Expected Failure |
|-------|-----------------|
| Remove `action_title` from page_02 in page_content.json | Error: action_title is empty |
| Set `wireframe: []` on page_01 in layout_plan.json | Error: wireframe is empty |
| Set `page_key: "page_04"` in layout_plan.json (mismatch) | Error: orphan page_key not in content |
| Set `export_allowed: true` with `validation_status: "fail"` | Error: export_allowed true but validation fail |
| Use `page: 1` instead of `page_key` | Warning: legacy identifier |
| Set `batch_size: 3` but put 6 pages in a batch | Warning: batch exceeds batch_size |

## What a good output demonstrates

- Page 1: Cover (L01) — emotional/airy, large title (48-64px), deliberate whitespace
- Page 2: KPI Dashboard (L03) — rational/dense, 3 stat cards in 4-4-4 grid, action title anchoring the data
- Page 3: Before/After (L09) — rational/balanced, 6-6 comparison, with supporting table

## Validation expectations

- All 3 SVG files pass `validate_svg_layout.py` (status: pass or non-blocking warning, never fail)
- Each SVG contains metadata comment with `page_key`, `data-layout`, `page_mode`, `visual_density`, `reason`
- PNG previews render at 1920×1080
- PPT output has 3 editable slides (not pasted images)

## Gate sequence for E2E test

1. `init_svg_project.py` → scaffold created
2. Populate contracts with expected fixtures
3. `validate_project_contracts.py` → pass
4. `estimate_layout_capacity.py` → `layout_capacity_report.json`
5. `generate_layout_html.py` → `01_layout_direction.html`
6. `pipeline_gate.py layout-ready` → pass
7. Submit layout feedback via `review_server.py`
8. `pipeline_gate.py layout-approved` → pass
9. Generate only `batch_01` SVGs
10. `pipeline_gate.py batch-svg-ready --batch batch_01` → pass
11. Render PNGs with `render_svg_png.py --batch batch_01`
12. Run `validate_svg_layout.py` with `--batch batch_01`
13. Create self-review and fix until no blockers remain
14. `pipeline_gate.py preview-ready --batch batch_01` → pass
15. `generate_review_html.py --batch batch_01` → `02_visual_review.html`
16. Submit visual feedback
17. `pipeline_gate.py visual-approved --batch batch_01` → pass
18. `pipeline_gate.py export-ready` → pass
19. `pptflow.py export` → `final_deck.pptx`

## Key landmarks for manual review

| Page | Expected landmark |
|------|------------------|
| 1 | Title is 48-64px, centered feel, red accent bar optional (L01 cover) |
| 2 | Three equal-width cards, large KPI numbers (64-80px), takeaway bar at Y=980 |
| 3 | Before/After columns side by side, visual distinction between old and new states |
