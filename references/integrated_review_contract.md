# Integrated Review Contract

`_internal/04_validation/integrated_review.json` records the model's combined judgment after both PNG preview and `validate_svg_layout.py` are available.

It exists to prevent piecemeal SVG fixes. The model should first read the validator report, inspect the PNG, then decide what must be fixed before user review.

## Path

```text
_internal/04_validation/integrated_review.json
```

## Shape

```json
{
  "batch_id": "batch_02",
  "reviewed_at": "2026-06-25T14:00:00Z",
  "method": "PNG visual inspection + validate_svg_layout diagnostics",
  "pages": {
    "page_04": {
      "decision": "ready_for_user_review",
      "must_fix": [],
      "should_fix": ["Increase evidence feeling if real assets are available."],
      "accepted_risks": ["HIGH_TEXT_DENSITY accepted after PNG review."],
      "fix_plan": ["No blocking SVG revision required."]
    }
  }
}
```

## Fields

| Field | Required | Notes |
|-------|----------|-------|
| `batch_id` | Yes | Current batch id |
| `reviewed_at` | Yes | ISO timestamp |
| `method` | Yes | How validator and PNG were reviewed |
| `pages` | Yes | Object keyed by page_key |
| `pages.*.decision` | Yes | `revise_before_user_review`, `ready_for_user_review`, or `return_to_plan` |
| `pages.*.must_fix` | Yes | Blocking items. Must be empty before `preview-ready` |
| `pages.*.should_fix` | No | High-value improvements; fix now if cheap, otherwise expose as design suggestion only when useful |
| `pages.*.accepted_risks` | No | Non-blocking warnings or visual risks accepted after PNG review |
| `pages.*.fix_plan` | No | What was changed or why no change is needed |

## Rule

Do not expose raw validator codes to users. Use this file to synthesize machine findings and visual judgment, then write user-facing observations in `self_review.json`.
