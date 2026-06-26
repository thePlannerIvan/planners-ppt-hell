# Quality Checklist

Use this checklist to judge generated SVG pages and their PNG previews. Each item belongs to one severity level (P0-P3) and one review mode.

**Severity levels:**

| Level | Meaning | Blocks PPT conversion? |
|-------|---------|----------------------|
| P0 | Delivery blocker — must fix before any PPT output | Yes |
| P1 | Serious experience issue — must fix before delivery | No |
| P2 | Design quality issue — should fix | No |
| P3 | Polish — nice to have | No |

**Review modes:**

- `script-checkable`: Can be verified by `validate_svg_layout.py`
- `model-visual`: Requires model visual inspection of PNG preview
- `human-review`: Requires human confirmation in `02_visual_review.html`

---

## P0 — Delivery Blockers

Must all pass before `pptflow.py <project_dir> export` runs the PPT converter.

| # | Item | Review Mode |
|---|------|-------------|
| P0-01 | Violates SVG/PPT compatibility rules — uses features listed as prohibited in `04_svg_rules.md` (e.g., `<foreignObject>`, `<filter>`, `<use>`, `<marker>`, `stroke-dasharray`, `<mask>`, `<animate>`, CSS `<style>`, `<tspan>` line-breaks). See `04_svg_rules.md` for the full list and alternatives. | `script-checkable` |
| P0-02 | Uses unsupported SVG feature that would silently disappear or distort in PPT — covers `<circle r<6>` shrinking to subpixel, `text-anchor="middle"` on long text causing offsets, and `opacity<0.3` on text being lost. See `04_svg_rules.md` for details. | `script-checkable` |
| P0-03 | Key text is invisible — missing `fill` on `<text>` in dark-background areas, or `fill` only set on parent `<g>` (converter does not inherit) | `script-checkable` |
| P0-04 | Key content outside safe margins (60px from canvas edge) | `script-checkable` |
| P0-05 | Page delivered as full-slide pasted image while claiming "editable PPT" | `human-review` |
| P0-06 | PNG preview not generated — cannot visually verify the page | `script-checkable` |
| P0-07 | Body text font-size below 20px SVG (≈10pt in PPT, unreadable) | `script-checkable` |

---

## P1 — Serious Experience Issues

Must fix before delivering to a real audience.

| # | Item | Review Mode |
|---|------|-------------|
| P1-01 | Text visually crowded — insufficient line spacing or padding | `model-visual` |
| P1-02 | Information hierarchy broken — subtitle looks like body, body looks like caption | `model-visual` |
| P1-03 | Title is a label, not a point of view (e.g., "Market Data" instead of "Market is shifting from growth to retention") | `model-visual` |
| P1-04 | Font family inconsistent across the same page | `script-checkable` |
| P1-05 | Font size tiers exceed 4 distinct sizes on one page | `script-checkable` |
| P1-06 | Palette drift — color value used that is not in the active token set | `script-checkable` |
| P1-07 | Three consecutive pages use the same `page_mode` + `visual_density` combination; treat as a rhythm diagnostic, not an automatic reason to redesign | `script-checkable` |
| P1-08 | Missing `font-family` declaration on one or more `<text>` elements | `script-checkable` |
| P1-09 | Text overflows its container rectangle horizontally | `script-checkable` |
| P1-10 | Text overflows its container rectangle vertically | `script-checkable` |
| P1-11 | Image lacks `data-slot` binding | `script-checkable` |
| P1-12 | Image aspect ratio is not a standard value (16:9, 16:10, 4:3, 3:2, 1:1, 3:4, 21:9) | `script-checkable` |
| P1-13 | Body content invades the Footer Zone (Y > 960 without being a footer element) | `script-checkable` |
| P1-14 | Missing SVG metadata comment (`data-layout`, `page_mode`, `visual_density`, `reason`) | `script-checkable` |
| P1-15 | Deck has no emotional page — all pages are rational dense, causing reader fatigue | `script-checkable` |
| P1-16 | `font-weight` value is invalid (not one of normal, bold, 100-900) | `script-checkable` |

---

## P2 — Design Quality Issues

Should fix for a polished result.

| # | Item | Review Mode |
|---|------|-------------|
| P2-01 | Whitespace strategy is weak — page feels either stuffed or empty without intention | `model-visual` |
| P2-02 | SVG execution does not match the PLAN-declared information density in `visual_density` (e.g., `airy` declared but 4 cards packed) | `model-visual` |
| P2-03 | Missing visual focus — no single element draws the eye first | `model-visual` |
| P2-04 | Takeaway bar missing on a page that would benefit from one (data-heavy, argument-heavy) | `model-visual` |
| P2-05 | Takeaway bar present but text is a label, not a conclusion | `model-visual` |
| P2-06 | Section divider missing in a deck over 8 pages | `script-checkable` |
| P2-07 | Card sizes within the same page are not uniform (sibling cards should match dimensions and padding) | `script-checkable` |
| P2-08 | Accent color used for decoration rather than functional distinction | `model-visual` |
| P2-09 | Line height for body text is visually cramped (Y spacing < font-size × 1.3 between consecutive lines) | `script-checkable` |

---

## P3 — Polish Items

Nice to have. Fix when time permits.

| # | Item | Review Mode |
|---|------|-------------|
| P3-01 | Source note placement is inconsistent with other pages | `model-visual` |
| P3-02 | Page number or section marker missing or inconsistent | `script-checkable` |
| P3-03 | Small annotations (< 20px) use fill that is too light for readability | `model-visual` |
| P3-04 | Alignment of secondary elements (captions, notes) drifts by more than 4px from the page baseline | `script-checkable` |
| P3-05 | The page does not look like a finished consulting slide — appears schematic or WIP | `model-visual` |
| P3-06 | Red accent bar missing on pages where it would anchor the header (rational pages with long headers) | `model-visual` |

---

## Self-Review Integration

When the model performs visual self-review of PNG previews, it should check each `model-visual` item above and record results in `_internal/04_validation/self_review.json`. If the runtime can inspect images, it must set `vision_available: true`, write `vision_check_method`, and mark every batch page `png_reviewed: true`. Script-checkable items are verified by `validate_svg_layout.py` automatically, but non-blocking validator warnings are internal evidence for the model. First combine validator findings and PNG observations in `_internal/04_validation/integrated_review.json`; then synthesize concise design advice only when the PNG confirms a real visual or communication issue.

The structured self-review contract is defined in `self_review_contract.md` and consumed by `generate_review_html.py`. The output must use that contract whenever vision review is available. `vision_available: false` is only for runtimes that genuinely cannot inspect PNG images and is rejected by `preview-ready` unless the explicit `--allow-vision-unavailable` exception is used. If validator warnings remain, self-review must include a `validator_revision_pass` and per-page `validator_assessment`; the user-facing review page should show design suggestions, not raw validator warning lists.
