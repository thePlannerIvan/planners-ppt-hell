# Revision Notes Contract

This document defines `_internal/05_review/revision_notes.json`, which records what changed after a visual review round.

`generate_review_html.py` reads this file and shows the notes on each page so the human reviewer can verify the latest revision without guessing what the model changed.

---

## Output Location

```text
_internal/05_review/revision_notes.json
```

---

## JSON Shape

```json
{
  "batch_id": "batch_01",
  "generated_at": "2026-01-01T00:00:00Z",
  "pages": {
    "page_03": {
      "previous_feedback": [
        "小字或字体风险",
        "收短长句，避免文字贴边"
      ],
      "changes_made": [
        "将旧做法说明从 18px 提升到 22px",
        "删除两条非关键注释",
        "扩大右侧新打法容器宽度"
      ],
      "not_changed": [
        "保留四个关键词，因为它们对应源文案中的四层打法"
      ],
      "remaining_risks": [
        "仍有 2 条小字号 warning，需要人工确认是否接受"
      ]
    }
  }
}
```

---

## Field Definitions

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `batch_id` | Yes | string | Batch being revised |
| `generated_at` | Yes | ISO timestamp | When the notes were written |
| `pages` | Yes | object | Keyed by `page_key` |
| `pages.{page_key}.previous_feedback` | Yes | string[] | User-selected actions and free-text feedback from the previous review round |
| `pages.{page_key}.changes_made` | Yes | string[] | Concrete changes made in the latest SVG revision |
| `pages.{page_key}.not_changed` | No | string[] | Requested changes not made, with reasons |
| `pages.{page_key}.remaining_risks` | No | string[] | Remaining warnings or reviewer decisions needed |

---

## Rules

1. Write this file after revising SVGs from visual feedback and before regenerating `02_visual_review.html`.
2. Use user-facing language, not validator codes.
3. `changes_made` must describe actual edits, not intentions.
4. If a selected action was not implemented, explain it in `not_changed`.
5. If warning-derived issues remain, translate them into human-readable `remaining_risks`.
