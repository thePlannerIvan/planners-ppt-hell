# SVG 画面的技术规则（SVG Rules v6.0）

模型负责画面判断；本文件规定通用技术契约与自动检查防线，用来防止渲染与排版事故。**两个出口——可编辑 PPT（`slides`）与视频静态画面（`video`）——均读取本文件**；可编辑 PPT 出口的专属转换契约见 `svg_to_ppt_rules.md`。

---

## 1. 画幅与天际线基准

- 默认 16:9 画布：`width="1920" height="1080"`、`viewBox="0 0 1920 1080"`，同一套项目保持一致。机器取值唯一 owner 为 `scripts/canvas_frame.py`。
- 常规内容页遵循 `style_system.md` 的 **1920×1080 全局天际线坐标**：
  - 页眉区：`y = 56..175`（左竖条 `x=80, y=64, w=8, h=54` + Action Title `x=106, y=102` + 副标题 `x=106, y=144` + 右上章节锚点 `x=1540..1560, y=64`）
  - 正文安全区：`x = 80..1840 (或 60..1860), y = 196..896`
  - 底部定海神针收口横幅：`x = 80, y = 918, width = 1760, height = 76`
  - 页脚来源与页码：`y = 1034..1036`

---

## 2. 基础表达与 `<style>` / `:root` CSS 变量支持

- **核心图元**：使用 `rect`、`line`、`circle`、`ellipse`、`polygon`、`polyline`、`path`、`text`、`image`、`linearGradient`、`radialGradient` 及结构化的 `g`。
- **双出口原生支持 `<style>` 与 `:root` `var(--...)` 设计令牌**：
  - `slides`（可编辑 PPT）与 `video`（视频静态画面）现在**均原生支持**页内 `<style>` 块与 `:root { --token: value; }` CSS 变量！
  - `native_svg_to_ppt.py` 与 `validate_svg_layout.py` 会在解析阶段自动展开 `:root` 变量并将 `.class`、`#id`、`tag` 选择器内联到元素属性上，从而让模板包的 `tokens.css` 在 SVG 渲染与 PPTX 导出两端 100% 同步生效。
  - 页面内若引用了未在 `:root` 中定义的 `var(--...)`（且无 fallback），会被检查器以 `UNDEFINED_CSS_VAR` 拦截。
- **文本与多行排版**：
  - 优先使用每行独立 `<text>` 或带 `<tspan x="..." dy="...">` 的显式多行段落（转换器会将带正 `dy` 的 `<tspan>` 自动拆分为 PowerPoint 文本框内的独立段落）。
  - 同一行内需要局部变色/加粗时，使用无 `dy`（或 `dy="0"`）的内联 `<tspan fill="var(--accent-brand)">`。
- **支持叶子节点与分组的轴对齐 `transform`**：
  - `<g>` 及叶子节点（`<rect>`、`<text>`、`<path>`、`<circle>`、`<ellipse>`、`<line>`、`<polygon>`、`<polyline>`、`<image>`）均支持轴对齐 `transform="translate(tx, ty) scale(sx, sy)"`，转换器与校验器共用同一套矩阵累乘模型。

---

## 3. 图片与可剥离占位层规范

```xml
<!-- 贴入真实图片时 -->
<image href="../00_project/source/assets/asset_001.png"
       x="104" y="276" width="472" height="380"
       data-asset-key="evidence" preserveAspectRatio="xMidYMid slice"/>

<!-- 尚未贴入真图、仅作占位提示时，必须包在可剥离组中 -->
<g data-slot="image-placeholder" class="slot-hint-removable">
  <rect x="104" y="276" width="472" height="380" rx="12" fill="#F1F5F9" stroke="#CBD5E1" stroke-dasharray="6 4"/>
  <text x="340" y="466" text-anchor="middle" font-size="16" fill="#64748B">[产品实拍图槽位 472×380]</text>
</g>
```

- 必须引用项目内真实存在的图片文件；完整显示用 `meet`，裁切铺满用 `slice`，**严禁使用 `none` 非等比拉伸**（会被 `IMAGE_STRETCHED` 拦截）。
- **卫生铁律**：一旦贴入真实 `<image>`，必须移除对应的 `<g data-slot="image-placeholder" class="slot-hint-removable">`，严禁在真照片底下残留 `[图片占位]` 文字。

---

## 4. 自动化检查防线（`validate_svg_layout.py` v6.0）

`validate_svg_layout.py` 与 `native_svg_to_ppt.py` **共用完全相同的坐标变换、`<style>` 展开与多行 `<tspan dy>` 文本框估算模型**，在 `check` 与 `export` 阶段自动拦截以下硬缺陷：

1. **`LINE_CROSSES_TEXT`（error，横线/分割线切字拦截）**：
   - 检测水平/垂直 `<line>` 或细长分割线 `<rect>`（厚 ≤ 6px、长 ≥ 60px）是否横穿任何 `<text>`（含多行 `<tspan dy>`）的包围盒内部。分割线必须严格走在容器或段落之间的留白通道内。
2. **`EMOJI_IN_SLIDE_TEXT`（error，幻灯片禁用系统 Emoji）**：
   - 拦截 `<text>` 中混入的 `🛡️💧🎯⚠️🔥` 等系统位图 Emoji。图标一律用原生 SVG 几何图形或等宽数字编号替代。
3. **`TEXT_OVERFLOWS_CONTAINER`（warning，胶囊/卡片文字溢出预警）**：
   - 当单行 `<text>` 位于胶囊标签或卡片 `<rect>` 内部，但估算字宽超出容器可用宽度时报警，防止转入 PowerPoint 后末字自动折行掉出胶囊。
4. **`TEXT_OVERLAP` / `OUT_OF_BOUNDS` / `TEXT_OUT_OF_BOUNDS`（error，文字重叠与出画布拦截）**：
   - 精确计入叶子节点 `transform`、`dominant-baseline` 与多行 `<tspan dy>` 高度，拦截同层文字互相踩踏或元素捅出 1920×1080 画布。
5. **图片与样式完整性（`MISSING_IMAGE` / `IMAGE_STRETCHED` / `UNDEFINED_CSS_VAR` / `INVALID_FONT_WEIGHT`）**：
   - 拦截缺失图片、拉伸变形、未定义 CSS 变量与非法属性。

> **技术报告零报错 ≠ 页面已经好看**。通过脚本检查后，必须实际打开每页渲染出的 **PNG 大图** 与整套联系表，按 `style_system.md` 核对 75:20:5 配比、天际线对齐、卡片下半截饱和度与视觉重心。
