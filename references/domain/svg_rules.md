# SVG 画面的技术规则

模型负责画面判断；这里只写技术规则，用来防止渲染事故。**两个出口——可编辑 PPT 与视频静态画面——都读这一份**；只有幻灯片出口才需要的额外约束在 `svg_to_ppt_rules.md`。

## 画幅

默认 16:9：`width="1920" height="1080"`、`viewBox="0 0 1920 1080"`，开局与用户确认一次，同一套保持一致。机器取值只有一个 owner：`scripts/canvas_frame.py`（归做画面），改画幅只改那里。

## 基础表达

使用 rect、line、circle、ellipse、polygon、path、text、image 及少量 g。文字显式写 x、y、font-family、font-size、font-weight、fill；深色背景上的文字显式给颜色，不依赖组继承。中文长句显式换行，每行独立 text，预留足够行距。

**视频静态画面可以额外用 `<style>`、动画和视觉效果**——它的出口是 PNG，承载得住；可编辑 PPT 的出口承载不住，那些约束归 `svg_to_ppt_rules.md`。风格 token 以内联 `:root` 块 + `var(--…)` 取值的方式落进画面，取值的落点是页内 `<style>` 的 class 规则（或元素自己的 `style`／属性），见 `03_video_route.md`；页里引用了没定义的 token 会被检查画面点名。

标题、正文、图表数据标签和来源都是可编辑 text；图形以原生 SVG 表达。无需额外写布局类型、密度或设计理由 metadata。

## 纵向构造

页内纵向位置从 `design_direction.md` 里定下的**一条纵向步长**导出，而不是先摆元素再让它们看起来齐（中文的字面方块天然构成这种步长，见 `style_system.md` 规则 13）。跨页重复的元素——页眉、页脚、页码、栏目名——各页使用**同一组坐标**，让它们落在同一条水平线上。

中西文混排会打断纯方块网格，这是正常的；要稳定的是**行的对齐关系**（段首、段末、栏目起点），不是让每个字符落在网格上。

## 图片

```xml
<image href="../00_project/source/assets/asset_001.png"
       x="100" y="220" width="900" height="600"
       data-asset-key="evidence" preserveAspectRatio="xMidYMid meet"/>
```

使用项目内文件，完整显示用 meet，填满用 slice，可用 xMin/xMid/xMax 与 YMin/YMid/YMax 选择焦点。禁止 none 拉伸。`data-asset-key` 用于最终审阅中的换图与裁剪；全页位置以实际 SVG 为准。

## 技术检查与视觉判断

**检查画面**（`validate_svg_layout.py`）只拦**在任何风格下都是缺陷**的那些：文字压文字、**元素出画布（含文字）**、空页、`<text>` 缺填色或 `font-weight` 非法、图片必须是真实存在的项目内文件且不得被拉伸。它**不**评价密度、字号档位、容器选择、留白多少或配色——那些是设计决定，由你看渲染图判断。

字号可读性在视频出口上由你看渲染图判断：屏幕上的字号合不合适，取决于这一屏要让观众读到什么，脚本不替你定档。

它和转换 PPT **共用同一套坐标几何**：校验器直接调用转换器的坐标模型（`native_svg_to_ppt.parse_axis_aligned_transform` / `compose_axis_aligned`），不自己再算一份。

因此：技术报告干净不等于页面好看。**实际查看每页 PNG 大图**——不是联系表里的缩略格——核对阅读层级、截断、重叠、图表标签、图片主体和来源；再看整套 contact sheet 检查构图重复与节奏。`OUTSIDE_SAFE_MARGIN` 是提示级（满版出血是正当的设计手法），不要为消除提示改设计。

遇到容量不足，重排、断行、拆页、调整内容，不以不断缩字解决。关键事实、来源和限定条件仍受保护。修订后检查新渲染；只要有实质进展就继续，不限制一次修复。
