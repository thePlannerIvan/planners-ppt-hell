# Self-Review Contract

This document defines the structured self-review format for model visual inspection of PNG previews. The contract is consumed by `generate_review_html.py` and referenced by `06_quality_checklist.md`.

Self-review exists for one purpose: before the user is asked to approve a batch, the model must look at the actual PNG result and synthesize whether the approved layout became a readable, mature slide. It is not a replacement for human review and it is not a raw dump of validator warnings.

Before writing `self_review.json`, first write `_internal/04_validation/integrated_review.json` after reading both PNG previews and `validation_summary.json`. Integrated review is the internal "what should we fix?" judgment; self-review is the user-facing synthesis after those fixes are resolved or accepted.

The model must use self-review to answer:

- Did the approved information anchor become visually obvious?
- Did the approved reading path survive SVG execution?
- Did copy reduction remain faithful and readable on the page?
- Are there visual problems that validator cannot see, such as weak hierarchy, dull rhythm, overused component language, or poor image treatment?
- Do non-blocking validator warnings matter visually, or are they acceptable?

In `02_visual_review.html`, users see only model-synthesized design suggestions. Validator warnings are internal model evidence and should be considered during self-review, but they must not be dumped directly into the user checklist. A checked design suggestion means "revise this before approval"; an unchecked suggestion is treated as accepted or deferred by the human reviewer.

---

## Output Location

`_internal/04_validation/self_review.json`

---

## JSON Shape

```json
{
  "reviewed_at": "2026-01-01T00:00:00Z",
  "vision_available": true,
  "human_review_required": false,
  "vision_unavailable_reason": "",
  "vision_check_method": "inspected rendered PNG previews for the current batch",
  "validator_revision_pass": {
    "attempted": true,
    "summary": "Validation warnings were reviewed against PNG previews; text overflow was fixed and remaining badge-tight warnings were accepted visually."
  },
  "pages": {
    "page_01": {
      "visual_status": "pass",
      "png_reviewed": true,
      "layout_feedback": "Grid 8-4 works well for this content.",
      "copy_feedback": "Title is an action title — strong.",
      "visual_feedback": "Red accent bar anchors the header zone correctly.",
      "validator_assessment": {
        "warning_count": 2,
        "action_taken": "fixed",
        "notes": "Adjusted vertical spacing and reran validation before self-review."
      },
      "required_fixes": [],
      "confidence": 0.85,
      "suggestions": [
        {"id": "A", "type": "layout", "text": "Consider 6-6 comparison instead of 8-4.", "basis": "PNG preview and validation warnings"},
        {"id": "B", "type": "copy", "text": "Shorten the h2 to one line.", "basis": "PNG preview"},
        {"id": "C", "type": "visual", "text": "Increase spacing between the three stat cards.", "basis": "PNG preview"}
      ]
    },
    "page_02": {
      "visual_status": "revise",
      "layout_feedback": "4-4-4 grid is correct but cards are vertically misaligned.",
      "copy_feedback": "Body text is too dense; split into two paragraphs.",
      "visual_feedback": "Accent blue used on all three cards — only first should use it.",
      "required_fixes": ["Card top edges must be at same Y"],
      "confidence": 0.7,
      "suggestions": [
        {"id": "A", "type": "layout", "text": "Align card top edges to Y=220."},
        {"id": "B", "type": "copy", "text": "Break the body into two shorter paragraphs."},
        {"id": "C", "type": "visual", "text": "Use accent blue only on the first card."}
      ]
    }
  }
}
```

---

## Field Definitions

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `reviewed_at` | Yes | ISO timestamp | When the review was performed |
| `vision_available` | Yes | boolean | Whether vision capability was used. If false, all model-visual checks are deferred to human-review |
| `human_review_required` | Yes | boolean | Must be true when `vision_available` is false. Indicates the batch still needs human visual judgment. |
| `vision_unavailable_reason` | Conditionally yes | string | Required when `vision_available` is false. Explain why PNG visual inspection was not performed. |
| `vision_check_method` | Conditionally yes | string | Required when `vision_available` is true. State how PNG previews were inspected. |
| `validator_revision_pass` | Conditionally yes | object | Required when validation reports contain warnings. Records the at-least-one validator-informed revision/review pass before user review. |
| `pages` | Yes | object | Keyed by page id (`page_01`, `page_02`, ...) |
| `pages.{id}.visual_status` | **Yes** | `"pass"`, `"revise"`, or `"blocked"` | Self-review verdict. `"blocked"` prevents export. |
| `pages.{id}.png_reviewed` | **Yes when vision is available** | boolean | Must be true after visually inspecting that page's PNG preview |
| `pages.{id}.layout_feedback` | No | string | Free-text observation about layout |
| `pages.{id}.copy_feedback` | No | string | Free-text observation about copy/text |
| `pages.{id}.visual_feedback` | No | string | Free-text observation about visual design |
| `pages.{id}.validator_assessment` | Conditionally yes | object | Required when that page has validation warnings. Records how validator findings were fixed or accepted after PNG review. |
| `pages.{id}.required_fixes` | No | string[] | Issues that MUST be fixed before PPT conversion |
| `pages.{id}.confidence` | No | number (0.0–1.0) | Model's confidence in its visual assessment. Lower confidence → more human scrutiny needed. |
| `pages.{id}.suggestions` | No | object[] | Up to 3 improvement suggestions; merged into the visual review action checklist |

### Suggestion Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | `"A"`, `"B"`, or `"C"` |
| `type` | string | `"layout"`, `"copy"`, or `"visual"` |
| `text` | string | One-sentence actionable suggestion |
| `basis` | string | Optional short basis, e.g. `"PNG preview"`, `"validation warning + visual judgment"` |

---

## Rules

1. Each page should produce at most 3 suggestions, ideally one each for layout, copy, and visual when issues are found.
2. Suggestions are optional — a perfect page may have 0 suggestions and `visual_status: "pass"`.
3. `required_fixes` must be non-empty when `visual_status` is `"revise"` or `"blocked"`.
4. Any page with `visual_status: "blocked"` must not proceed to PPT conversion. Pipeline gate enforces this.
5. If no vision capability is available, set `vision_available: false`, set `human_review_required: true`, write `vision_unavailable_reason`, and do not write page-level visual verdicts. The correct `pages` value is `{}`.
6. `confidence` should reflect the model's certainty about its visual assessment. Values below 0.5 indicate the reviewer should pay extra attention.
7. `visual_status: "blocked"` is for showstopper issues (e.g., unreadable text, missing key content, severe layout breakage). `"revise"` is for pages that need improvement but aren't broken.
8. Validator warnings should be synthesized into `layout_feedback`, `copy_feedback`, `visual_feedback`, or `suggestions` only when they are visually meaningful. Do not expose raw warning codes as user-facing design suggestions.
9. If `vision_available` is true, every batch page must set `png_reviewed: true`. Do not infer visual quality from SVG code alone.
10. If validation has any warning for a page, that page must include `validator_assessment.action_taken` with one of: `fixed`, `accepted_after_png_review`, or `deferred_to_human`.
11. If validation has warnings anywhere in the batch, `validator_revision_pass.attempted` must be true and `validator_revision_pass.summary` must describe the one revision/review pass done before user review.
12. Multimodal-capable models must not set `vision_available: false`. That value is only for runtimes that genuinely cannot inspect rendered PNG images.

---

## Placeholder (No Vision)

When vision is unavailable, write a minimal self-review:

```json
{
  "reviewed_at": "...",
  "vision_available": false,
  "human_review_required": true,
  "vision_unavailable_reason": "This runtime cannot inspect PNG previews directly.",
  "pages": {}
}
```

Do not write `"visual_status": "pass"` when vision is unavailable. Do not claim the page is visually acceptable. `generate_review_html.py` will detect `vision_available: false` and display a prominent warning in `02_visual_review.html`.
