# 4. 预览、校验与 PPTX 转换共享 CSS 变量与 SVG 几何引擎

- **Status**: accepted

工作台 HTML 预览（`generate_review_html.py`）、布局校验器（`validate_svg_layout.py`）与可编辑 PPTX 转换器（`native_svg_to_ppt.py`）强制共享同一套 `<style>` / `:root` CSS 变量内联器（`lib/svg_style_inline.py`）和轴对齐矩阵几何计算（`lib/svg_geometry.py`）。

## Considered Options

- **三处各自解析 SVG 与估计包围盒**：预览看着正常、校验报通过，但导出成 PPTX 时文字折行、胶囊溢出、细分割线丢失或组内变换位移。
- **在入口禁止 `<style>` 与 CSS 变量**：虽然省去了解析一致性的工作，但让模板包无法集中管理 `:root` 设计令牌，换肤和统一改色失效。

## Consequences

- 任何一处看到的坐标、包围盒和 token 展开结果都保持同构；一旦修改 `svg_geometry.py` 中的坐标或规则算法，校验器规则指纹自动失效并触发页面重查。
- `slides` 出口仍保持可转换为原生 PowerPoint 图元的受限子集约束（禁 `foreignObject` / `filter` / 容器 `rotate()` / 系统位图 Emoji），`video` 出口只校验通用结构与画面安全规则。
