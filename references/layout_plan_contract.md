# Layout Plan Contract

This document defines the schema for `_internal/01_layout_plan/layout_plan.json`. It records every PLAN-stage content organization decision made per page before SVG generation begins.

---

## Purpose

`layout_plan.json` captures the model's page-specific layout judgment: page mode, information density, reference layout family, adapted wireframe zones, copy handling, asset-slot decision, layout rationale, risks, and reviewer-facing alternatives. It is the contract between content understanding and SVG production — the user approves the model's organization plan here, and SVG generation obeys the approved plan.

The layout stage also produces `_internal/01_layout_plan/layout_capacity_report.json`. That report is a lightweight physical estimate of whether planned on-slide copy can fit the approved wireframe. It does not replace layout judgment and does not automatically rewrite the layout; it surfaces likely `tight`, `overfull`, and `too_empty` cases before SVG production.

`page_mode` is the PLAN-stage expression mode:

- `rational`: analysis, data, strategy, method, comparison, dense summary pages. The layout must preserve evidence, hierarchy, and readable information flow.
- `emotional`: cover, divider, quote, closing, and value-judgment pages. The layout should allocate more space to a single memorable anchor and reduce competing content.

`layout_id` is a reference family from `05_layout_taxonomy.md`, not a locked template. The model must explain how it adapts the reference to the actual copy, evidence, capacity, and deck rhythm.

Every page must also declare a `visual_asset_strategy`. In PLAN, this means deciding whether the page needs a picture/material slot, what information role that asset plays, where it belongs, and what source or aspect ratio is expected. It does not decide final visual style, rendering treatment, color, crop, or illustration aesthetics; those belong to DRAFT/SVG.

---

## File Location

```
_internal/01_layout_plan/layout_plan.json
```

---

## JSON Schema

```json
{
  "project": "项目名称",
  "generated_at": "2026-06-22T00:00:00Z",
  "layout_version": 1,
  "pages": [
    {
      "page_key": "page_01",
      "layout_id": "L04",
      "page_mode": "rational",
      "visual_density": "balanced",
      "grid": "8-4",
      "layout_usage": "adapted",
      "design_judgment": {
        "persuasion_action": "prove",
        "content_relation": "claim plus evidence",
        "information_anchor": "right-side evidence screenshot",
        "reader_takeaway": "The claim is credible because the evidence is visible."
      },
      "why_this_layout": "本页是主论点加证据，因此参考 L04 的 argument + evidence 组织逻辑。",
      "why_not_other_layouts": "没有选择三卡并列，因为正文不是三个平权要点；没有选择纯结论页，因为需要证据支撑。",
      "adaptation_note": "本页按证据重要性把 content 区域调整为 7-5 或 8-4。",
      "anti_laziness_check": "右侧视觉不是装饰图，而是支撑标题判断的证据槽。",
      "wireframe": [
        {
          "label": "主论点 + 支撑论述",
          "x": 60,
          "y": 200,
          "w": 1140,
          "h": 640,
          "zone": "main_left"
        },
        {
          "label": "证据截图 / 数据图",
          "x": 1260,
          "y": 200,
          "w": 600,
          "h": 640,
          "zone": "main_right"
        },
        {
          "label": "底部结论条",
          "x": 60,
          "y": 960,
          "w": 1800,
          "h": 60,
          "zone": "footer"
        }
      ],
      "copy_handling": {
        "final_on_slide": {
          "title": "市场正在从增量竞争转向存量博弈",
          "subtitle": "三个信号同时出现，窗口期不超过18个月。",
          "body": [
            "头部品牌集中度连续三个季度突破60%",
            "中小品牌获客成本同比上升42%",
            "消费者品牌切换意愿降至三年最低"
          ],
          "footer_takeaway": "窗口期有限，品牌需要现在完成从流量驱动到品牌驱动的转型。"
        },
        "kept_on_slide": ["action_title", "core_message", "body_bullets"],
        "compression_rationale": [
          "保留三条信号和关键数字，因为它们构成页面证据链。",
          "将长解释压缩为底部结论句，完整解释保留在 notes。"
        ],
        "compressed": ["正文解释段：压缩为底部结论句，避免主内容区超载"],
        "moved_to_notes": ["详细数据来源说明"]
      },
      "capacity_notes": [
        "主论点区域按 28px 正文估算可容纳约 8-10 行，正文需压缩为 4 条以内。"
      ],
      "visual_asset_strategy": {
        "asset_need": "required",
        "asset_type": "screenshot_placeholder",
        "placement": "main_right",
        "reason": "本页需要右侧证据截图来支撑标题判断，避免只用文字说明。",
        "prompt_or_source": "用户提供 16:9 网页截图或 3:4 手机端截图；若无素材，先保留截图占位符。"
      },
      "layout_reason": "PageMode: rational\nPurpose: prove\nInformationAnchor: 右列证据截图\nReadingPath: 标题判断 -> 左侧论点 -> 右侧证据 -> 底部结论\nSpatialPlan: 左8列放置核心论点与支撑论述，右4列放置证据截图。8-4非对称网格给论点足够阅读空间，同时用右列证据建立可信度。",
      "design_risks": [
        "如果右列截图内容过多，4列宽度可能不足以清晰展示"
      ],
      "review_suggestions": [
        "考虑将右列扩展为5列（7-5分），给证据截图更多呼吸空间",
        "如果截图内容较少，考虑在右列底部增加一个关键数字强调",
        "标题拆成两行可以增加留白呼吸感，但会占用更多Header区高度"
      ]
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
| `generated_at` | No | string | ISO 8601 timestamp |
| `layout_version` | No | integer | Incremented after each round of layout revision |
| `pages` | Yes | array | Ordered list of layout decisions, matching page_content.json order |

### Page Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `page_key` | **Yes** | string | Canonical page identifier. Must match `page_content.json` |
| `layout_id` | **Yes** | string | Reference layout family from L01-L15, or `L00` for custom/adapted logic outside the reference list |
| `layout_usage` | No | string | `reference`, `adapted`, or `custom`; recommended for making adaptation explicit |
| `page_mode` | **Yes** | string | `rational` or `emotional` |
| `visual_density` | **Yes** | string | `dense`, `balanced`, or `airy`. Historical field name; in PLAN this means information/spatial density, not final visual style. |
| `grid` | **Yes** | string | Planned spatial strategy, e.g. `4-4-4`, `8-4`, `6-6`, `5-7`, `7-5`, `3-9`, `full-width`, `custom-asymmetric`, etc. This is descriptive, not a template lock. |
| `design_judgment` | No | object | Structured PLAN-stage reasoning: persuasion action, content relation, information anchor, reader takeaway |
| `why_this_layout` | No | string | Why this reference family fits the page's content relationship |
| `why_not_other_layouts` | No | string | Why nearby tempting layout families were not chosen |
| `adaptation_note` | No | string | How the reference family is adapted for actual copy, evidence, capacity, and deck rhythm |
| `anti_laziness_check` | No | string | Explicit note showing the page is not defaulting to a lazy visual habit |
| `wireframe` | **Yes** | array | At least one zone rectangle defining the spatial layout |
| `copy_handling` | **Yes** | object | How source copy is rewritten into final on-slide copy and allocated across slide vs. notes |
| `capacity_notes` | No | string[] | Human-readable capacity assumptions or risks from layout_capacity_report.json |
| `visual_asset_strategy` | **Yes** | object | Whether this page needs a picture/material slot, where it sits, and what information role/source it has |
| `layout_reason` | **Yes** | string | Human-readable rationale. Should include PageMode / Purpose / InformationAnchor / ReadingPath / SpatialPlan / Reason, or equivalent reasoning. |
| `design_risks` | No | string[] | Anticipated issues with this layout choice |
| `review_suggestions` | No | string[] | Alternative layout directions for reviewer consideration (0-3 items) |

### Wireframe Zone Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `label` | **Yes** | string | Human-readable zone label (Chinese preferred) |
| `x` | **Yes** | number | Left edge in SVG pixels (canvas: 1920×1080) |
| `y` | **Yes** | number | Top edge in SVG pixels |
| `w` | **Yes** | number | Width in SVG pixels |
| `h` | **Yes** | number | Height in SVG pixels |
| `zone` | No | string | Semantic zone: `header`, `main_left`, `main_right`, `main_center`, `footer` |

### Copy Handling Object

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `final_on_slide` | **Yes** | object | The exact title, subtitle/body bullets, labels, and takeaway text that will be visible on the PPT page |
| `kept_on_slide` | **Yes** | string[] | Legacy/capacity helper: which source sections remain represented on the slide |
| `compression_rationale` | **Yes** | string[] | Why the source copy was kept, shortened, merged, or moved; must explain the business/content principle, not only "space is limited" |
| `compressed` | No | string[] | Which content sections were shortened, including method and reason |
| `moved_to_notes` | No | string[] | Which source details were moved to speaker notes and must remain traceable |

Rules:

1. `copy_handling` is the only approved place to record slide-level copy reduction.
2. `final_on_slide` is the authoritative PPT-visible copy after layout approval. SVG generation must draw from it and must not silently rewrite it.
3. `final_on_slide.title` should normally match the approved `action_title`; if shortened, the reason must appear in `compression_rationale`.
4. `final_on_slide.body` should contain the exact bullets, labels, or short paragraphs that will be laid out. Do not write vague labels such as "body_bullets" here.
5. `kept_on_slide` remains for capacity estimation and source traceability; it identifies source sections represented by `final_on_slide`.
6. `compression_rationale` must explain the content principle: what was preserved, what was simplified, what was moved, and why the meaning is still faithful.
7. `compressed` must include the reason and the compression method, e.g. "body paragraph 2: shortened to one label because full explanation is in speaker_notes".
8. `moved_to_notes` must preserve any content removed from the visible slide.
9. Facts, numbers, percentages, sources, brand/product names, and core conclusions must not be compressed into a less precise claim.
10. If the page cannot hold required copy without violating readability, change layout, split the page, or move explanatory copy to notes; do not silently delete it.

### Copy Reduction Principles

PLAN 阶段必须把原始文案处理成可上屏文案。原则是：

- 保留主张、关键证据、数字、来源、限定条件和业务判断。
- 可以精简重复铺垫、口语化解释、过长修饰语和次要背景。
- 可以把长段落拆成短句、标签、证据点或结论句，但不得改变判断强度。
- 可以把完整解释移入 `speaker_notes`，但必须在 `moved_to_notes` 中说明。
- 不能为了视觉好看删掉反例、风险、条件或不确定性。
- 如果精简后只剩口号而证据链消失，应重新调整版式或拆页，而不是继续压缩。

### Capacity Report

The optional companion file `_internal/01_layout_plan/layout_capacity_report.json` uses this shape:

```json
{
  "project": "项目名称",
  "generated_at": "2026-06-22T00:00:00Z",
  "canvas": {"w": 1920, "h": 1080},
  "pages": {
    "page_01": {
      "status": "tight",
      "summary": "正文区预计 9 行，可用 8 行，建议压缩一条解释性文字或扩大文本区。",
      "regions": [
        {
          "zone": "main_left",
          "label": "主论点 + 支撑论述",
          "estimated_chars": 188,
          "font_size": 28,
          "estimated_lines": 9,
          "max_lines": 8,
          "utilization": 1.12,
          "status": "tight"
        }
      ],
      "recommendations": [
        "把 body paragraph 2 移入 speaker notes，或将网格从 8-4 改为 7-5。"
      ]
    }
  }
}
```

Capacity statuses:

| Status | Meaning |
|--------|---------|
| `ok` | Planned copy is likely to fit with normal spacing |
| `tight` | Copy may fit, but needs careful line breaks or slightly larger zone |
| `overfull` | Planned copy likely cannot fit without unreadable text or layout changes |
| `too_empty` | Zone is much larger than expected copy and may need a clearer information role, asset slot, or rebalanced layout |

Rules:

1. Capacity estimates are advisory, but `overfull` on primary content should be addressed before layout approval.
2. Fix `overfull` by changing layout, moving explanatory copy to notes, or splitting the page; do not solve it by shrinking body text below readability limits.
3. `too_empty` is not an error. It should prompt the model to clarify whether the whitespace is intentional, emotional, or needs a stronger information role or asset slot.

### Visual Asset Strategy Object

Every page must include this object, even when no visual asset is used.

In this contract, `visual_asset_strategy` means "does this page need a picture/material slot?" It is a layout-stage decision because a photo, screenshot, chart, SVG illustration, or generated image requires reserved space. It does not define final style. DRAFT/SVG decides crop, styling, color treatment, masking, annotation style, and component rendering after the layout is approved.

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `asset_need` | **Yes** | string | `required`, `optional`, or `none` |
| `asset_type` | **Yes** | string | `real_asset`, `data_visual`, `editable_schematic`, `photo_placeholder`, `screenshot_placeholder`, `svg_background`, `svg_illustration`, `generated_image`, `chart`, or `none`. In PLAN this names the expected asset/material type, not its final rendering style. |
| `placement` | **Yes** | string | `main_right`, `full_bleed`, `background`, `card_visual`, `evidence_slot`, `inline_diagram`, or `none` |
| `reason` | **Yes** | string | Why the page needs this asset/material slot, or why it does not need one |
| `prompt_or_source` | No | string | Expected source, subject, aspect ratio, or material requirement. Detailed image-generation style belongs to DRAFT/SVG. |
| `fallback_if_missing` | No | string | What to do if the expected asset is unavailable. Prefer "deliver with editable schematic and report the limitation" over blocking delivery. |

Rules:

1. Product, scenario, people, store, social content, ad sample, and case pages should not default to pure text; reserve an asset/material slot unless the rationale explains why not.
2. Use `real_asset` when the page needs actual screenshots, photos, product images, or case evidence. If no file is available, say so and provide a fallback.
3. Use `editable_schematic` when the visual is a model-made SVG explanation, not proof. Do not let it masquerade as a real screenshot or image.
4. Use `data_visual` when the asset is mainly a chart, trend, map, or structured diagram.
5. If `asset_type` is `generated_image`, `prompt_or_source` must describe purpose, subject, aspect ratio, and whether the image is replaceable. Avoid final art-direction detail here.
6. If `asset_type` is `photo_placeholder` or `screenshot_placeholder`, `prompt_or_source` must specify the expected source and aspect ratio.
7. If `asset_need` is `none`, `asset_type` and `placement` must both be `none`, and `reason` must justify the decision.
8. If the user asks for "加图" and no real asset exists, first deliver with a clearly described fallback, then report that the page uses an editable schematic rather than real image evidence.

---

## Wireframe Requirements

Every page **must** have a non-empty `wireframe` array. Wireframes are simple grey-box spatial diagrams:

- Canvas: 1920 × 1080 (16:9)
- Each zone is a `<rect>` with grey fill, border, and centered label
- Zones must cover all planned content areas. Rational pages should show the stable shell when relevant and should make the adaptive content field clear.
- No decorative styling — purpose is spatial communication only

A page without a wireframe is an error. `generate_layout_html.py` will refuse to render pages with empty wireframes.

---

## Layout ID Rules

- `L01`–`L15`: Reference layout families from `05_layout_taxonomy.md`
- `L00`: Custom organization logic outside the reference list. Requires detailed reasoning.
- `layout_id` is not a command to copy coordinates. It records the dominant information organization logic.
- Unknown layout IDs produce `info`-level validator messages, not errors.

---

## Page Mode + Information Density Consistency

The declared `page_mode` and `visual_density` should usually be consistent with the chosen `layout_id`, but adaptation is allowed when the reasoning is explicit. Although the field is named `visual_density`, PLAN uses it as information/spatial density:

| If layout is... | Expected page_mode | Expected visual_density |
|----------------|-------------------|------------------------|
| L01 Cover | emotional | airy |
| L03 KPI Dashboard | rational | dense |
| L08 Big Quote | emotional | airy |
| L09 Before/After | rational | balanced |

For adapted or custom layouts, any mode/density combination is accepted as long as the layout judgment explains why it serves the page.

---

## Chinese Page Example

```json
{
  "page_key": "page_01",
  "layout_id": "L04",
  "page_mode": "rational",
  "visual_density": "balanced",
  "grid": "8-4",
  "wireframe": [
    {"label": "标题区", "x": 60, "y": 60, "w": 1800, "h": 120, "zone": "header"},
    {"label": "主论点 + 支撑论述", "x": 60, "y": 200, "w": 1140, "h": 740, "zone": "main_left"},
    {"label": "证据截图", "x": 1260, "y": 200, "w": 600, "h": 740, "zone": "main_right"}
  ],
  "copy_handling": {
    "final_on_slide": {
      "title": "市场正在从增量竞争转向存量博弈",
      "subtitle": "三个信号同时出现，窗口期不超过18个月。",
      "body": [
        "头部品牌集中度连续三个季度突破60%",
        "中小品牌获客成本同比上升42%",
        "消费者品牌切换意愿降至三年最低"
      ],
      "footer_takeaway": "品牌需要在窗口期内完成从流量驱动到品牌驱动的转型。"
    },
    "kept_on_slide": ["action_title", "core_message", "body_bullets"],
    "compression_rationale": [
      "保留三条信号和关键数字，因为它们构成页面证据链。",
      "将长解释压缩为底部结论，完整背景放入 notes。"
    ],
    "compressed": ["长解释段压缩为底部结论句"],
    "moved_to_notes": ["详细数据来源说明"]
  },
  "visual_asset_strategy": {
    "asset_need": "required",
    "asset_type": "screenshot_placeholder",
    "placement": "main_right",
    "reason": "本页用截图作为证据锚点，帮助用户判断右侧论据是否可信。",
    "prompt_or_source": "需要一张 16:9 桌面截图或 3:4 手机截图。"
  },
  "layout_reason": "PageMode: rational\nPurpose: prove\nInformationAnchor: 右列证据截图\nReadingPath: 标题判断 -> 左侧论点 -> 右侧证据\nSpatialPlan: 左文右图版式，正文结论在左列锚定，右列截图做证据支撑。",
  "design_risks": [],
  "review_suggestions": [
    "考虑右列扩展为5列（7-5分），给证据截图更多空间"
  ]
}
```

---

## Validation Rules

Enforced by `scripts/validate_project_contracts.py`:

1. File must exist and be valid JSON
2. `pages` array must be non-empty
3. Every page must have `page_key` matching content
4. Every page must have `layout_id`, `page_mode`, `visual_density`, `grid`
5. Every page must have non-empty `wireframe` array
6. Every page must have non-empty `layout_reason`
7. Every page must have `copy_handling.final_on_slide`, `kept_on_slide`, and `compression_rationale`
8. Every page must have `visual_asset_strategy` with `asset_need`, `asset_type`, `placement`, and `reason`
9. No page may use `page`, `page_number`, `page_id`, or `layout` as its primary identifier
