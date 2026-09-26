# 转可编辑 PPT 的额外约束

**只有幻灯片出口读这一份。** 视频静态画面的出口是 PNG，下面每一条都不适用于它——这些约束唯一的理由是「转换器不能可靠处理」。通用规则在 `svg_rules.md`。

## 单位换算（写死在这里，别每次重算）

画布 1920px 对应 13.333in 宽的幻灯片，所以 **1 SVG px = 0.5pt**。32px = 16pt，48px = 24pt，96px = 48pt。字号下限按页面 `mode` 判：`讲` 页 ≥18px（9pt），`读` 页 ≥12px（6pt）。

## 转换器不能可靠处理的

禁用 foreignObject、filter、use、style、marker、mask、animate，以及 stroke-dasharray、textLength、lengthAdjust 和 marker-*。使用显式属性，不依赖 CSS。避免 rotate、skew、matrix；简单 translate / scale 也要核对转换结果。渐变、clipPath 和复杂 path 必须跑实际转换验证。用几何箭头替代 marker，不能把标签藏进图片。

标题、正文、图表数据标签和来源都要以原生可编辑 text 表达，`tspan` 换行按转换器要求书写。

## 严格模板

保留 data-template-lock 层、required components、`data-layout-id` 和 `data-template-content-layer="replace"`。指定 canvas 从脚本实例化；检查锁层与真实资产，不能用近似重绘冒充复用。

## 导出后复核

`export` 先逐页跑一遍检查画面，有「转成 PPT 会坏」的错误就拦下不出稿；`check` 里跑的那次是提前预警，方便早改。

SVG 显示正确不证明 PPTX 正确。圆弧、折线、图片裁剪、字体和透明度在最终 PPTX 渲染中再次核对——`EXPORT_VERIFY` 这一步就是干这个的。
