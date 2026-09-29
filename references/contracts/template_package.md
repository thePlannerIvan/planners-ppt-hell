# 多模态 PPT 模板包契约（`template_package.md`）

> 替代旧版「8 步机械 XML 审批 + 4 份冗余 JSON 账本（`template_asset_registry.json`、`template_worker_result.json`、`template_canvas_self_review.json`、空壳 `content_base.svg`）」。无论输入是 `.pptx`、`.pdf` 还是页面截图，统一收敛为**「标准四件套（Four-Piece Template Pack）」**。

---

## 一、 标准四件套目录结构

每个模板包（位于内置库 `assets/template_library/<template_id>/` 或项目工作区 `_internal/00_project/template_pack/`）包含以下 4 件核心资产与 `manifest.json`：

```text
<template_id>/
├── tokens.css                  # [件 1] 全局设计令牌 (:root CSS 变量：75:20:5 色盘、字体族、6 档字号)
├── skyline_shell.svg           # [件 2] 1920x1080 全局天际线底壳（页眉左竖条+Action Title+副标+右上锚点+正文安全区+底部定海神针+页脚）
├── assets/                     # [件 2 附属] 从源 PPTX 母版/版式/幻灯片无损提取去重的 Logo 与矢量底纹（可为空目录）
├── primitives/                 # [件 3] 6–8 个带精确坐标与 var(--*) 变量的 1920x1080 内页 SVG 版式原语骨架
│   ├── p01_cover.svg
│   ├── p02_*.svg
│   └── ...
├── anchors/                    # [件 4] 4–6 张精选源参考页高清 PNG（供多模态模型在画页时直接看图对齐质感）
├── SPEC.md                     # [件 4] 一页纸排版标尺、原语选型表与「五减五加」防丑红线
└── manifest.json               # 包元数据、推荐场景、预览图路径与全文件 SHA256 校验和
```

---

## 二、 四件套各组件硬性规格

### 1. `tokens.css`（全局设计令牌）
- 必须在 `:root` 下定义语义化色彩变量，严格执行 **75% 中性灰白底 : 20% 炭黑墨色 : 5% 唯一品牌强调色** 纪律：
  - 画布与表面色（75%）：`--canvas-bg`、`--surface-card`、`--surface-muted`、`--surface-dark`、`--surface-accent-tint`
  - 墨色与文字层级（20%）：`--ink-primary`、`--ink-secondary`、`--ink-muted`、`--ink-on-dark`
  - 品牌强调色（5%）：`--accent-brand`、`--accent-secondary`
  - 线条与分割：`--border-subtle`、`--border-strong`
- 配合支持 `:root` `var(--*)` 展开的 `native_svg_to_ppt.py`，所有内页 SVG 直接内联或引用这套变量，彻底根除跨批次生成的“彩虹糖色漂移”。

### 2. `skyline_shell.svg` + `assets/`（1920×1080 全局天际线底壳）
- 锁死 `viewBox="0 0 1920 1080"` 全局天际线坐标：
  - **页眉左竖条**：`x="80" y="68" width="8" height="56" rx="4" fill="var(--accent-brand)"`
  - **Action Title 主标题基线**：`x="108" y="104" font-size="44" font-weight="900"`（限 1 行 ≤26 字，必须是观点结论句）
  - **副标题 / 导语基线**：`x="108" y="148" font-size="22" fill="var(--ink-secondary)"`（核心词 `<tspan fill="var(--accent-brand)" font-weight="700">`）
  - **右上角章节锚点**：`x="1840" y="92" text-anchor="end"` 等宽大写编号（如 `SECTION 01 // MARKET INSIGHT`）
  - **页眉分割线**：`x1="80" y1="176" x2="1840" y2="176" stroke="var(--border-subtle)"`
  - **正文安全区（Safe Zone）**：`x = 80..1840`（宽 `1760px`），`y = 200..896`（高 `696px`）
  - **底部定海神针横幅（Takeaway Banner）**：`x="80" y="916" width="1760" height="76" rx="12" fill="var(--surface-dark)"`
  - **页脚来源与页码**：左下 `x="80" y="1032"` 数据口径，右下 `x="1840" y="1032"` 页码。

### 3. `primitives/*.svg`（内页版式原语骨架）
- 每个原语文件本身就是一张合法、零重叠、可直接用 `render_svg_png.py` 渲染成 `1920×1080` PNG 并用 `native_svg_to_ppt.py` 转为可编辑 PPTX 的完整 SVG。
- 遵守「五减五加」工程纪律：
  1. 容器嵌套 ≤ 2 层（禁止框套框超过 2 层）；
  2. 零系统 Emoji（全部使用纯矢量几何 `<path>`/`<circle>`/`<polygon>` 或等宽大数字编号 `01` `02`）；
  3. 胶囊宽度留足余量（满足 `width >= zh_chars * font_size * 1.15 + en_chars * font_size * 0.65 + 2 * pad_x`）；
  4. 分割线绝不穿过任何 `<text>` 包围盒；
  5. 凡涉及图片槽位，占位提示文字必须独立封装在 `<g class="slot-hint-removable">` 中。

### 4. `SPEC.md` + `anchors/` + `manifest.json`
- `SPEC.md` 用一页纸列出：色彩与字号速查表、全局天际线坐标表、各原语的适用叙事场景与字数上限、以及防翻车红线。
- `anchors/` 保留 4–6 张高清参考页 PNG。
- `manifest.json` 由 `template_library.py` 自动生成并校验 SHA256。
