# 转可编辑 PPT 的双向契约与专属约束（SVG-to-PPT Rules v6.0）

**只有幻灯片出口（`slides`）读取本文件。** 本文件定义了 SVG 源码与 `native_svg_to_ppt.py`（v6.0 原生形状转换器）之间的精确双向契约。通用排版规则见 `svg_rules.md` 与 `style_system.md`。

---

## 1. 物理尺寸与字号换算（写死标尺，无需重算）

- **画布到幻灯片映射**：`1920 × 1080 px` 对应 `13.333 × 7.5 in`（标准 16:9 宽屏 PPT），因此：
  - **1 SVG px = 0.5 pt**（`FONT_SCALE = 0.5`）
  - `44px = 22pt`（主标题）｜`28px = 14pt`（卡片主标题）｜`20px = 10pt`（正文）｜`14px = 7pt`（辅助标签/图注）
- **字号硬下限**：
  - `讲` 页（现场投屏）：任何可见 `<text>` **≥ 18px（9pt）**
  - `读` 页（商业提案/留档报告）：正文 **≥ 16px（8pt）**，角标与数据来源底线 **≥ 12px（6pt）**

---

## 2. `native_svg_to_ppt.py` v6.0 原生支持的能力清单（放心使用）

v6.0 转换器已打通以下 6 大核心能力，无需再写繁琐的手工 workaround：

1. **页内 `<style>` 与 `:root` `var(--...)` CSS 变量自动展开**：
   - 支持在 `<style>` 中定义 `:root { --accent-brand: #E60012; ... }` 及 `.class` / `#id` / `tag` 样式规则；转换器会在导出 PPTX 前自动求值并内联为标准 SVG 属性。
2. **原生虚线 `stroke-dasharray` 与 `1px` 精致分割线**：
   - `<line>`、`<rect>`、`<path>`、`<circle>` 上的 `stroke-dasharray` 会按占空比自动映射为 PowerPoint 原生 `ROUND_DOT`、`DASH` 或 `LONG_DASH`；
   - `width="1"` 或 `height="1"` 的 `<rect>` 细分割线（`≥ 0.2px`）完整保留为原生无边框填充色条，不再被过滤丢失。
3. **`<tspan dy>` 多段落换行与行内富文本混排**：
   - 同一 `<text>` 内带有正值 `dy`（如 `<tspan x="80" dy="28">`）的子节点，会自动转换为同一个 PowerPoint 文本框内的**独立自然段（Paragraph）**，并把 `dy` 映射为段落间距；
   - 无 `dy`（或 `dy="0"`）的 `<tspan fill="#E60012" font-weight="700">` 会作为同一段落内的独立 `Run` 保留局部高亮色与字重。
4. **叶子节点与分组的轴对齐 `transform` 累乘**：
   - `<g>` 以及 `<rect>`、`<text>`、`<path>`、`<circle>`、`<ellipse>`、`<line>`、`<polygon>`、`<polyline>`、`<image>` 上的 `transform="translate(tx, ty) scale(sx, sy)"` 均被精确累乘（包括在交互审阅台拖拽元素产生的位移）。
5. **文字透明度、`rgba()`、`letter-spacing` 与垂直居中基线**：
   - `<text>` 自身及祖先 `<g>` 的 `opacity` / `fill-opacity`，以及 `fill="rgba(255,255,255,0.7)"` 均会写入 PowerPoint `<a:solidFill><a:srgbClr><a:alpha>`，保证 `132–140px` 浅灰水印大数字在 PPTX 中保持柔和水印质感，绝不变成纯黑实心字挡住正文；
   - `letter-spacing`（支持 `2px`、`0.08em`）自动乘以 `FONT_SCALE (0.5)` 写入 `<a:rPr spc>`；
   - `dominant-baseline="central|middle|hanging"` 自动补偿文本框 Y 偏移；
   - 胶囊标签与多 `<tspan>` 文本框内置宽度安全余量（避免末字在 PPTX 中掉行）。
6. **`<linearGradient>` / `<radialGradient>` 原生渐变转换**：
   - `<defs>` 中的线性/径向渐变会直接生成 PowerPoint 原生 `<a:gradFill>` XML（含 `<a:gsLst>` 色标位置、颜色与 `<a:alpha>` 透明度，以及 `<a:lin ang>` 角度）。

---

## 3. 转换器明确禁用的特性（会被 `validate_svg_layout.py` 拦截）

以下 SVG 特性在 PowerPoint 原生形状模型中没有等价物，**严禁在 `slides` 出口使用**：

- **禁用标签**：`foreignObject`、`filter`（如 `feDropShadow`、`feGaussianBlur`，阴影靠浅色底差或底层偏移 `<rect>` 表达）、`use`、`marker`（箭头一律用显式 `<polygon>` 或 `<path>` 绘制）、`mask`、`animate`、`animateTransform`。
- **禁用属性**：`textLength`、`lengthAdjust`、`marker-start`、`marker-mid`、`marker-end`。
- **禁用非轴对齐几何变形**：禁止在容器 `<g>`、`<rect>`、`<path>` 上使用 `rotate()`、`skewX()`、`skewY()` 或含旋转分量的 `matrix()`（注：单个 `<text transform="rotate(...)">` 支持旋转角映射）。
- **禁用系统 Emoji**：`<text>` 内严禁出现位图 Emoji（`EMOJI_IN_SLIDE_TEXT`），必须使用 SVG 矢量图形或等宽数字徽章。

---

## 4. 胶囊与容器防溢出写法建议

虽然转换器已内置文本框宽度余量，但在设计胶囊标签（Pill Badge）与窄指标卡时仍应遵守：
- 胶囊 `<rect>` 宽度按 **`中文字符数 × 字号 + 英文字符数 × 字号 × 0.62 + 左右内边距 32px`** 预算（例如 6 个 14px 汉字的胶囊，`width` 至少给 `14 × 6 + 32 = 116px`，推荐 `124–140px`）；
- 胶囊内文字优先使用 `text-anchor="middle"` 并将 `x` 设为胶囊中心点 `rect_x + rect_width / 2`。

---

## 5. 导出前硬门禁与 `EXPORT_VERIFY` 闭环

- `export` 命令在调用 `native_svg_to_ppt.py` 之前会强制逐页运行 `validate_svg_layout.py --route slides`；凡有 `error`（包括 `LINE_CROSSES_TEXT`、`EMOJI_IN_SLIDE_TEXT`、`TEXT_OVERLAP`、`OUT_OF_BOUNDS`）一律阻断导出。
- 导出 `.pptx` 后，必须经过 LibreOffice → PDF → PNG 渲染（`EXPORT_VERIFY`），逐页核对最终 PPTX 渲染图中的文字换行、水印层级、渐变方向与图片裁切。
