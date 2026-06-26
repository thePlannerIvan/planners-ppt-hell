# Page Manifest Contract

This document defines the schema for `_internal/00_project/page_manifest.json`. It tracks the production state of every page through the pipeline.

---

## Purpose

`page_manifest.json` is the production ledger. It records which pages are planned, generated, validated, reviewed, and exportable. The pipeline gate script (`pipeline_gate.py`) reads this file to enforce phase transitions, batch discipline, and export readiness.

---

## File Location

```
_internal/00_project/page_manifest.json
```

---

## JSON Schema

```json
{
  "project": "项目名称",
  "version": "2.0",
  "batch_size": 3,
  "batch_config": {
    "batch_01": {
      "status": "visual_approved",
      "pages": ["page_01", "page_02", "page_03"]
    },
    "batch_02": {
      "status": "planned",
      "pages": ["page_04", "page_05", "page_06"]
    }
  },
  "pages": [
    {
      "page_key": "page_01",
      "svg_path": "_internal/02_svg_source/page_01.svg",
      "png_path": "_internal/03_png_preview/page_01.png",
      "validation_status": "pass",
      "layout_approved": true,
      "visual_approved": true,
      "export_allowed": true
    },
    {
      "page_key": "page_02",
      "svg_path": "_internal/02_svg_source/page_02.svg",
      "png_path": "_internal/03_png_preview/page_02.png",
      "validation_status": "warning",
      "layout_approved": true,
      "visual_approved": false,
      "export_allowed": false
    }
  ]
}
```

---

## Field Definitions

### Top-Level

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `project` | Yes | string | Project name |
| `version` | Yes | string | Manifest schema version (`"2.0"`) |
| `batch_size` | Yes | integer | Maximum pages per batch (default: 3) |
| `batch_config` | Yes | object | Batch assignments and statuses, keyed by `batch_id` |
| `pages` | Yes | array | Production state for every planned page |

### Batch Config Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `status` | Yes | string | Batch status: `planned`, `layout_approved`, `svg_generated`, `validation_passed`, `preview_ready`, `visual_approved` |
| `pages` | Yes | string[] | `page_key` values assigned to this batch |

### Page State Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `page_key` | **Yes** | string | Canonical page identifier. Must match `page_content.json` and `layout_plan.json` |
| `svg_path` | No | string | Relative path to SVG file (from project root) |
| `png_path` | No | string | Relative path to PNG preview (from project root) |
| `validation_status` | No | string | Current validation state: `not_validated`, `pass`, `warning`, `fail` |
| `layout_approved` | Yes | boolean | Whether layout direction was approved by reviewer |
| `visual_approved` | Yes | boolean | Whether final visual was approved by reviewer |
| `export_allowed` | Yes | boolean | Whether this page is cleared for PPT conversion |

---

## Status Lifecycle

Each page moves through these states:

```
[planned]
  → layout_approved (layout feedback submitted + approved)
  → svg_generated (SVG file written to svg_path)
  → preview_ready (PNG preview exists, validation has no blockers, and visual self-review is complete)
  → visual_approved (review feedback submitted + approved)
  → export_allowed (all gates cleared)
```

A page can be **blocked** at any stage:
- `validation_status: "fail"` → cannot proceed to `visual_approved`
- `layout_approved: false` → cannot proceed to `svg_generated`
- `visual_approved: false` → cannot proceed to `export_allowed`

---

## Batch Discipline Rules

1. A batch cannot exceed `batch_size` pages unless the batch config explicitly sets a larger `batch_size` override.
2. A batch cannot move to `svg_generated` until all pages in the batch are `layout_approved`.
3. A batch cannot move to `preview_ready` until all pages in the batch have PNG previews, validation reports with no blockers, and clean visual self-review. `vision_available: false` is rejected by default and requires the explicit `--allow-vision-unavailable` exception.
4. A batch cannot move to `visual_approved` until all pages in the batch are `preview_ready`.
5. A new batch cannot start SVG generation while the previous batch has unresolved feedback (i.e., `visual_approved: false` for any page in the previous batch).
6. Future batch artifacts are prohibited. While processing batch B, later batches must not have SVG, PNG, validation reports, or self-review entries. Early generation is a workflow violation because later pages must incorporate feedback from earlier visual review.
7. `export-ready` fails if any planned page is missing from `pages` array or has `export_allowed: false`.

---

## Validation Status Values

| Value | Meaning | Blocks Next Phase? |
|-------|---------|-------------------|
| `not_validated` | Validation not yet run | Yes — must run validation |
| `pass` | No errors or warnings | No |
| `warning` | Warnings present, no errors | Blocks only if the warning code is blocker-class (`TEXT_OVERFLOW_MAJOR`, `FOOTER_ZONE_INVASION`). Other warnings are model-internal diagnostics; the model may convert meaningful visual implications into concise design suggestions, but raw warnings should not be shown directly to users. |
| `fail` | P0 errors present | **Yes** — must fix before proceeding |

---

## Gate Script Integration

`pipeline_gate.py` reads `page_manifest.json` to enforce:

- `layout-ready`: All planned pages exist in manifest, page_content.json and layout_plan.json are cross-valid
- `layout-approved`: Layout feedback exists (in `layout_feedback.json`), all pages or specified batch pages approved through review server with `approval_key_required: true` and `approval_key_verified: true`
- `batch-svg-ready --batch B`: SVG exists at `svg_path` for every page in batch B; no future batch artifacts exist
- `validation-passed --batch B`: legacy/static check; `validation_summary.json` exists, no fail/error and no blocking warning for batch B; no future batch artifacts exist. This gate may still be used for diagnostics but is no longer required before PNG rendering.
- `preview-ready --batch B`: PNG previews exist for batch B, `validation_summary.json` exists with no fail/error and no blocker-class warning for batch B, `integrated_review.json` combines validator + PNG judgment with no unresolved `must_fix`, and `self_review.json` records real PNG visual review (`vision_available: true`, `vision_check_method`, per-page `png_reviewed: true`). If validation warnings remain, `self_review.json` must also record `validator_revision_pass` and per-page `validator_assessment`. `vision_available: false` is allowed only with the explicit `--allow-vision-unavailable` exception; no future batch artifacts may exist.
- `visual-approved --batch B`: `02_visual_review.html` exists, batch-specific review feedback exists for batch B through review server with `approval_key_required: true` and `approval_key_verified: true`; this gate writes `visual_approved` and `export_allowed` to the manifest
- `export-ready`: All planned pages have SVG/PNG, approved layout, approved visual review, valid validation status, and `export_allowed: true`; layout feedback and every batch's visual feedback must also have trusted review server provenance with `approval_key_required: true` and `approval_key_verified: true`

Visual feedback persistence:

- `_internal/05_review/feedback.json` is the latest submitted visual feedback only.
- `_internal/05_review/batches/<batch_id>.json` is the durable approval record for each batch.
- A new batch cannot start from browser approval alone; `pipeline_gate.py visual-approved --batch B` must run successfully and update `page_manifest.json`.
- Export must verify every batch-specific feedback file, not only the latest `feedback.json`.

PPT export must be started through `pptflow.py <project_dir> export`; do not run `native_svg_to_ppt.py` directly.

---

## Chinese Page Example

```json
{
  "page_key": "page_01",
  "svg_path": "_internal/02_svg_source/page_01.svg",
  "png_path": "_internal/03_png_preview/page_01.png",
  "validation_status": "pass",
  "layout_approved": true,
  "visual_approved": true,
  "export_allowed": true
}
```

---

## Prohibited Fields

The following must **not** appear as page identifiers in `page_manifest.json`:

- `page`
- `page_number`
- `page_id`
- `layout`

If present, `validate_project_contracts.py` flags a warning.

---

## Validation Rules

Enforced by `scripts/validate_project_contracts.py`:

1. File must exist and be valid JSON
2. `pages` array must be non-empty (once project is initialized with content)
3. Every page must have `page_key` matching content and layout contracts
4. Every page must have `layout_approved`, `visual_approved`, `export_allowed` booleans
5. `batch_config` batches must reference valid `page_key` values
6. `batch_size` must be > 0
7. No page may use `page`, `page_number`, or `page_id` as its primary identifier
8. `export_allowed` must be `false` if `validation_status` is `"fail"`
