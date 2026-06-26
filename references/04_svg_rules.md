# SVG Rules

本文档只用于 DRAFT/SVG 阶段。它负责保证生成的 SVG 能稳定渲染、校验，并转换为可编辑 PPT。

一句话职责：

> 设计可以有变化，SVG 实现必须稳定。

本文档不决定版式，不决定审美风格，不决定上屏文案取舍。

- 版式判断看 `05_layout_taxonomy.md`。
- 视觉风格和设计底线看 `03_style_system.md`。
- 本文只描述当前转换器和校验器下的有效 SVG 写法。

---

## 1. 硬性契约

### 1.1 画布

每页 SVG 必须固定为 16:9、`1920x1080`：

```svg
<svg width="1920" height="1080" viewBox="0 0 1920 1080" xmlns="http://www.w3.org/2000/svg">
```

必须同时满足：

- `width="1920"`。
- `height="1080"`。
- `viewBox="0 0 1920 1080"`。
- 根节点包含 `xmlns="http://www.w3.org/2000/svg"`。
- 页面内容不得超出画布安全边距，默认 `60px`。

### 1.2 Metadata 注释

`<svg>` 标签后第一行必须写 metadata 注释：

```svg
<!--
page_key="page_01"
data-layout="L04"
page_mode="rational"
visual_density="balanced"
reason="Left text anchors the argument; right visual provides evidence."
-->
```

要求：

- `page_key` 必须与 `page_manifest.json` 中的页面一致。
- `data-layout` 使用 `L01`-`L15`；自定义版式用 `L00`。
- `page_mode` 为 `rational` 或 `emotional`。
- `visual_density` 为 `dense`、`balanced` 或 `airy`。
- `reason` 建议不超过 50 字。

metadata 缺失是阻断错误，因为 pipeline 依赖它做校验和可追溯检查。

---

## 2. 绝对禁止

以下写法不要使用。它们可能在 PPT 转换中消失、变形、不可编辑或导致不可控结果。

| 禁止项 | 替代方案 |
| --- | --- |
| `<foreignObject>` | 用 `<text>`、`<rect>`、`<image>` 重建 |
| `<filter>` | 用纯色、浅色阴影形状或无阴影 |
| `<use>` | 直接内联重复元素 |
| CSS `<style>` 块 | 所有样式写成元素内联属性 |
| `<marker>` / `marker-end` | 用独立 `<polygon>` 手动画箭头 |
| `stroke-dasharray` | 用低透明度实线，或多段短 `<line>` 模拟 |
| `<mask>` | 用纯色形状、裁切后的图片或叠放形状替代 |
| `<animate>` | 使用静态图形 |
| `transform="rotate(...)"` | 通过坐标和形状本身表达方向 |
| `textLength` / `lengthAdjust` | 手动换行和调整 x 坐标 |
| `<tspan>` 做换行 | 每行独立 `<text>` |
| 关键文字只依赖父级 `<g>` 的 `fill` | 每个 `<text>` 显式写 `fill` |

不要用“浏览器预览正常”作为理由保留这些写法。

---

## 3. 条件可用项

这些特性不是绝对禁止，但必须按限定范围使用。

| 特性 | 允许范围 | 慎用范围 |
| --- | --- | --- |
| `<tspan>` | 同一行内局部变色、加粗 | 不得用于换行、布局、定位 |
| `text-anchor="middle"` | 12 字符以内的短标题、短数字 | 长中文、混合中英文标题容易偏移 |
| `<path>` | 封闭填充形状、曲线、复杂轮廓 | 普通直线/折线优先用 `line` / `polyline` |
| `stroke-opacity` | 简单透明线可用 | 多层透明线条可能难维护 |
| `fill-opacity` / `opacity` | 当前转换器支持 | 文本 opacity 不低于 `0.3` |
| `<circle>` | 半径 `r >= 6` | 小点可用 `<rect>` 或增大半径 |
| `<linearGradient>` / `<radialGradient>` | 可用但会回退为首个 stop-color | 不要依赖渐变细节表达核心信息 |
| `clip-path="inset(round)"` | 可提取最大圆角值 | 不要用它做非对称圆角 |

---

## 4. 文本安全

### 4.1 必备属性

每个 `<text>` 必须显式包含：

- `x`
- `y`
- `font-family`
- `font-size`
- `fill`

推荐字体：

```text
Microsoft YaHei, SimHei, sans-serif
```

正确示例：

```svg
<text x="100" y="120" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="44" font-weight="bold" fill="#333333">标题文字</text>
```

深色底上的浅色文字必须在 `<text>` 自身声明 `fill`，不要依赖 `<g>` 继承。

### 4.2 换行

换行必须拆成多个独立 `<text>`：

```svg
<text x="100" y="120" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="44" fill="#333333">第一行标题</text>
<text x="100" y="178" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="44" fill="#333333">第二行标题</text>
```

不要用 `<tspan>` 换行：

```svg
<text x="100" y="100">
  <tspan x="100" dy="0">第一行</tspan>
  <tspan x="100" dy="50">第二行</tspan>
</text>
```

同行局部强调可以用 `<tspan>`：

```svg
<text x="100" y="220" font-family="Microsoft YaHei, SimHei, sans-serif" font-size="24" fill="#555555">核心是<tspan fill="#C62828" font-weight="bold">递进关系</tspan>，不是装饰。</text>
```

### 4.3 字号红线

转换公式：

```text
SVG font-size x 0.5 ~= PPT pt
```

| 角色 | SVG font-size | PPT 字号 |
| --- | --- | --- |
| H0 水印 / 巨型数字 | `120-160px` | `60-80pt` |
| H1 大标题 | `48-64px` | `24-32pt` |
| H2 副标题 | `28-36px` | `14-18pt` |
| H3 卡片标题 | `26-30px` | `13-15pt` |
| Body 正文 | `22-26px` | `11-13pt` |
| Caption / Source | `18-20px` | `9-10pt` |

红线：

- 正文推荐不低于 `20px`。
- 低于 `20px` 会触发可读性 warning。
- 低于 `16px` 会触发不可读 error。
- 放不下时，不要继续缩字，回到 PLAN。

### 4.4 溢出估算

宽度估算：

```text
中文/全角字符: font-size x 1.0
英文/数字/半角符号: font-size x 0.6
可用宽度 = container.width - 2 x padding
默认 padding = 24px
```

垂直估算：

```text
LINE_HEIGHT = font-size x 1.5
容器底边 = rect.y + rect.height - 20px
最底部文本 = last_text.y + font-size
```

修正优先级：

1. 拆行。
2. 缩小字号 2-4px，但不得低于字号红线。
3. 在已批准 wireframe 内增大容器、调整局部断行或重新分配同一区域内的元素。
4. 只对非正文辅助标注做轻量缩写；原始正文、数字、来源不得删减。

如果需要改变已批准的主版式、区域比例、上屏取舍或拆页，不属于 SVG 局部修复，应记录原因并回到 PLAN/用户确认。

---

## 5. 图形写法

### 5.1 矩形 / 卡片

```svg
<rect x="120" y="240" width="500" height="360" rx="12" fill="#FFFFFF" stroke="#E0E0E0" stroke-width="1"/>
```

仅顶部圆角可用重叠 `rect`，不用 CSS `clip-path` 做非对称圆角：

```svg
<rect x="120" y="350" width="500" height="450" rx="16" fill="#FFFFFF" stroke="#CCCCCC"/>
<rect x="120" y="350" width="500" height="100" rx="16" fill="#C62828"/>
<rect x="120" y="410" width="500" height="40" fill="#C62828"/>
```

组件选择看 `03_style_system.md`。SVG rules 只约束写法是否稳定。

### 5.2 箭头

正确：`line + polygon`

```svg
<line x1="100" y1="300" x2="190" y2="300" stroke="#C62828" stroke-width="3"/>
<polygon points="185,290 205,300 185,310" fill="#C62828"/>
```

不要使用 `<marker>`：

```svg
<line x1="100" y1="300" x2="200" y2="300" stroke="#C62828" stroke-width="3" marker-end="url(#arrow)"/>
```

### 5.3 直线 / 折线 / 曲线

```svg
<line x1="100" y1="300" x2="500" y2="300" stroke="#CCCCCC" stroke-width="2"/>
<polyline points="100,200 200,100 400,150" fill="none" stroke="#CCCCCC" stroke-width="2"/>
<path d="M100,200 Q300,80 500,200" fill="none" stroke="#CCCCCC" stroke-width="2"/>
```

普通直线和折线优先用 `<line>` / `<polyline>`；曲线或复杂轮廓才用 `<path>`。

不要用 `stroke-dasharray`。如果必须有断续感，用低透明度实线或多段短 `<line>` 手动排列。

### 5.4 分组

可以使用：

```svg
<g transform="translate(100,200)">
```

`translate` 和 `scale` 当前可转换。

限制：

- 不要使用 `rotate`。
- 分组内文字仍必须显式写 `fill`、`font-family`、`font-size`。
- 不要依赖父级 `<g>` 继承关键文本样式。

---

## 6. 内容完整性

SVG 必须服从：

- `page_content.json`
- 已批准的 `layout_plan.json`
- `copy_handling.final_on_slide`

不得在 SVG 阶段私自：

- 改写标题。
- 删除数字。
- 删除来源。
- 删除限定条件。
- 压缩正文。
- 拆页。
- 改变主版式比例。
- 改变已批准的内容上屏/notes 取舍。

SVG 上屏文案可以执行 `copy_handling` 中已记录的取舍，但不得出现未记录的删减、摘要或压缩。

如果内容放不下：

1. 先检查是否正确执行 `copy_handling`。
2. 再检查是否在已批准 wireframe 内合理断行。
3. 仍不成立，则记录原因并回到 PLAN，调整版式、拆页或移入 speaker notes。

---

## 7. Validator 处理

`validate_svg_layout.py` 是内部诊断器，不是审美裁判。它用于阻断确定性坏结果，并把可人工判断的风险送入视觉自检。

不要看到一个 warning 就立刻局部改 SVG。正确顺序是：先渲染 PNG、再读取 validator、然后把机器诊断和视觉观察合并成一次综合判断。只有综合判断完成后，才决定哪些 SVG 问题必须修，哪些是可接受风险。

必须先修：

- `TEXT_OVERFLOW_MAJOR`
- `TEXT_OVERLAP`
- `TEXT_IMAGE_OVERLAP`
- `UNSAFE_MARGIN`
- `FONT_TOO_SMALL`
- `TEXT_TOO_TINY`
- 缺 metadata
- 禁用 SVG 特性
- error-level issue
- blocker-class warning

可以结合 PNG 判断：

- `TEXT_CONTAINER_TIGHT`
- `TEXT_BASELINE_ESTIMATE_DRIFT`
- `DENSITY_IMBALANCE_*`
- `LARGE_EMPTY_REGION`
- `LOW_MODULE_UTILIZATION`
- `TABLE_READABILITY_RISK`

处理原则：

- 遇到 issue 时，下一轮必须优先读取 `diagnosis` 和 `recommended_fix`，不要凭感觉反复微调。
- non-blocking warning 必须结合 PNG 判断；视觉上可接受的 warning 可以记录为 `accepted_after_png_review`。
- 综合判断应写入 `_internal/04_validation/integrated_review.json`：`must_fix` 为空才可以进入用户审阅；`should_fix` 是高收益改进；`accepted_risks` 是看过 PNG 后接受的轻微风险。
- 同一页同类 issue 连续两轮仍未解决，说明不是 SVG 坐标问题，而是 PLAN 阶段的版式或内容取舍问题。必须记录原因并回到 PLAN/用户确认。

---

## 8. PPT 映射速查

| SVG 写法 | PPT 映射 |
| --- | --- |
| `x/y/width/height` | `value x (13.333 / 1920)` inches |
| `font-size` | `value x 0.5` pt |
| `<g transform="translate(dx,dy)">` | 子节点坐标累加偏移 |
| `<g transform="scale(sx,sy)">` | 子节点尺寸和字号缩放 |
| `fill` / `stroke` | 映射为 PPT 填充 / 线条色 |
| `opacity` / `fill-opacity` / `stroke-opacity` | 映射为 alpha 透明度 |
| `letter-spacing` | 映射为 `a:rPr spc` |
| `<path d="...">` | 转为 freeform；曲线折线近似 |

不要把 PPT 当主编辑面修 SVG；源 SVG 才是主编辑面。

---

## 9. 输出前检查

生成或修改 SVG 后，至少检查：

- [ ] 根节点是 `1920x1080` 且 `viewBox="0 0 1920 1080"`。
- [ ] `<svg>` 后第一行有完整 metadata 注释。
- [ ] 没有 `<foreignObject>`、`<filter>`、`<use>`、`<style>`、`<marker>`、`<mask>`、`<animate>`。
- [ ] 没有 `stroke-dasharray`、`transform="rotate(...)"`、`textLength`、`lengthAdjust`。
- [ ] 没有用 `<tspan>` 换行；多行文本拆成多个 `<text>`。
- [ ] 所有 `<text>` 都有 `x`、`y`、`font-family`、`font-size`、`fill`。
- [ ] `text-anchor="middle"` 只用于短文本。
- [ ] 正文/说明文字不低于 `20px`；任何文字不低于 `16px`。
- [ ] 所有文本没有横向或纵向溢出。
- [ ] 所有内容在 `60px` 安全边距内。
- [ ] 圆角使用 `rx` 或重叠 `rect`，不用 CSS `clip-path` 做非对称圆角。
- [ ] 箭头用 `line + polygon`。
- [ ] 普通直线/折线用 `line` / `polyline`。
- [ ] 所有 `<circle>` 的 `r >= 6`，除非该圆形不是可见元素。
- [ ] 内容完整，数字、百分比、来源、表格行列没有丢失。
- [ ] PNG 预览肉眼可读，并符合已批准 `layout_plan.json`。
