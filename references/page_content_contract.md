# Page Content Contract

This document defines the schema for `_internal/01_content/page_content.json`. It is the single source of truth for all page copy that flows through the pipeline.

---

## Purpose

`page_content.json` preserves complete per-page copy — action titles, core messages, body blocks, tables, speaker notes, and the original source text for each page. No downstream step (layout, SVG, review, PPT) should guess or paraphrase what the page says. The content contract makes copy visible, verifiable, and traceable from source to final slide.

---

## Copy Policy

CONTENT 阶段的职责是把源 Markdown 转成可审阅的页面内容契约，而不是重写源文案。

允许：

- 将源文案按页、章节或叙事顺序拆成 `page_01`、`page_02` 等页面。
- 将原始标题、段落或要点提炼成更适合 PPT 的 `action_title`。
- 将该页要证明的核心意思整理为 1-3 句 `core_message`。
- 将长段落拆成 `paragraph`、`bullet_list`、`numbered_list`、`kpi_set` 等结构化块。
- 将演讲提示、背景解释、长引用说明放入 `speaker_notes`。
- 修正明显的标点、空格、换行和重复标题问题。

禁止：

- 修改事实、数字、百分比、品牌名、产品名、时间、来源、案例对象或限定条件。
- 将源文案中没有的判断写成事实。
- 因为版面担心放不下，就在 CONTENT 阶段删减正文。
- 把多个不同论点合并成一个无法追溯的概括。
- 用新的营销话术替换原文的策略判断。
- 丢失反例、条件、保留意见或“不确定性”表达。

`action_title` 和 `core_message` 可以是页面化表达，但必须满足：

- 与源文案的主张一致。
- 不扩大结论范围。
- 不改变因果关系。
- 不新增未经来源支持的数据或判断。
- 能通过 `source_excerpt` 找到完整来源依据。

`body_blocks` 是完整内容保全层。它应保留该页的全部正文信息；真正的上屏取舍发生在 PLAN 阶段，并必须记录在 `layout_plan.json` 的 `copy_handling` 中。

---

## File Location

```
_internal/01_content/page_content.json
```

---

## JSON Schema

```json
{
  "project": "项目名称",
  "source_path": "source.md",
  "generated_at": "2026-06-22T00:00:00Z",
  "pages": [
    {
      "page_key": "page_01",
      "source_page_id": "P1",
      "source_title": "市场格局概览",
      "action_title": "市场正在从增量竞争转向存量博弈",
      "core_message": "三个信号同时出现，窗口期不超过18个月。2024年行业CR5首次突破60%，头部集中度加速提升。",
      "body_blocks": [
        {
          "type": "bullet_list",
          "items": [
            "信号一：头部品牌集中度连续三个季度突破60%",
            "信号二：中小品牌获客成本同比上升42%",
            "信号三：消费者品牌切换意愿降至三年最低"
          ]
        },
        {
          "type": "paragraph",
          "text": "上述三个信号的同时出现，标志着行业正式进入存量博弈阶段。品牌需要在18个月内完成从流量驱动到品牌驱动的转型。"
        }
      ],
      "tables": [],
      "speaker_notes": "这一页是开场定调页。核心要传达的是紧迫感——窗口期有限，必须现在行动。如果客户对某个信号的数据来源有疑问，可以补充第三方报告引用。",
      "source_excerpt": "## Page 1: Market Overview\n\nH1: 市场正在从增量竞争转向存量博弈\n\nBody: 三个信号同时出现..."
    }
  ]
}
```

---

## Field Definitions

### Top-Level

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `project` | Yes | string | Project name or identifier |
| `source_path` | No | string | Path to the source markdown file |
| `generated_at` | No | string | ISO 8601 timestamp of content extraction |
| `pages` | Yes | array | Ordered list of page content objects |

### Page Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `page_key` | **Yes** | string | Canonical page identifier. Format: `page_01`, `page_02`, ... |
| `source_page_id` | No | string | Original page identifier from source (e.g., `P2`, `P17.5`) |
| `source_title` | No | string | Original section title from source markdown |
| `action_title` | **Yes** | string | The strategic judgment or insight that anchors this page. Must be a claim, not a label. |
| `core_message` | **Yes** | string | 1-3 sentence summary of what this page proves or communicates |
| `body_blocks` | **Yes** | array | Ordered list of content blocks (bullet lists, paragraphs, etc.) |
| `tables` | No | array | Any tables on this page |
| `speaker_notes` | No | string | Presenter notes, context, or delivery guidance |
| `source_excerpt` | No | string | Historical field name; should contain the complete original source text for this page whenever available |

`source_excerpt` should be present whenever source text is available. Despite the field name, it should be treated as the page's original full source text, not a short excerpt. Only omit unrelated neighboring pages or sections; preserve all source copy that supports `action_title`, `core_message`, `body_blocks`, tables, caveats, and evidence.

### Body Block Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `type` | Yes | string | One of: `bullet_list`, `paragraph`, `numbered_list`, `quote`, `kpi_set` |
| `items` | No | string[] | For list types: array of text items |
| `text` | No | string | For paragraph/quote types: full text |

### Table Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `caption` | No | string | Table caption or title |
| `headers` | No | string[] | Column headers |
| `rows` | No | string[][] | Data rows (each row is an array of cell values) |

---

## Canonical Page Key

The `page_key` field is the **only** identifier used across all pipeline contracts.

**Format:** `page_01`, `page_02`, ..., `page_NN`

**Rules:**
- Keys must be sequential starting from `page_01`
- Keys must be unique within the project
- Keys must use two-digit zero-padded numbers
- All downstream contracts (`layout_plan.json`, `page_manifest.json`) reference pages by `page_key`

---

## Prohibited Identifiers

The following field names **must not** be used as primary page identifiers in any contract:

- `page`
- `page_number`
- `page_id`
- `layout` (as page identifier)

These legacy fields caused ambiguity and mismatch errors. If present in any contract file, `validate_project_contracts.py` will flag a warning.

> **Note on `layout_id`**: `layout_id` is a required layout classification field in `layout_plan.json` (e.g., `"layout_id": "L04"`). It is **not** a page identifier and must not be used to reference or look up pages. The canonical page identifier is always `page_key`.

---

## Full Copy Requirement

Every page must have non-empty `action_title`, `core_message`, and at least one `body_blocks` entry. The content contract is the authoritative record — downstream systems must not silently drop, compress, or paraphrase copy without recording the change in `layout_plan.json` → `copy_handling`.

CONTENT may create a sharper page title, but it may not create a shorter page body. If body content is too long for a slide, keep it in `body_blocks` first; PLAN decides what remains on slide and what moves to notes.

---

## Chinese Page Example

```json
{
  "page_key": "page_01",
  "source_page_id": "P1",
  "source_title": "市场格局概览",
  "action_title": "市场正在从增量竞争转向存量博弈",
  "core_message": "三个信号同时出现，窗口期不超过18个月。2024年行业CR5首次突破60%，头部集中度加速提升。",
  "body_blocks": [
    {
      "type": "bullet_list",
      "items": [
        "信号一：头部品牌集中度连续三个季度突破60%",
        "信号二：中小品牌获客成本同比上升42%",
        "信号三：消费者品牌切换意愿降至三年最低"
      ]
    }
  ],
  "tables": [],
  "speaker_notes": "这一页是开场定调页。核心要传达的是紧迫感——窗口期有限，必须现在行动。",
  "source_excerpt": "## Page 1: Market Overview\n\nH1: 市场正在从增量竞争转向存量博弈\n..."
}
```

---

## Validation Rules

Enforced by `scripts/validate_project_contracts.py`:

1. File must exist and be valid JSON
2. `pages` array must be non-empty
3. Every page must have `page_key`
4. `page_key` values must be unique and sequential
5. Every page must have non-empty `action_title`
6. Every page must have non-empty `core_message`
7. Every page must have non-empty `body_blocks`
8. No page may use `page`, `page_number`, or `page_id` as its primary identifier
