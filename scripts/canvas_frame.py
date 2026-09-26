#!/usr/bin/env python3
"""画幅：一套页面到底多大。**这个决定归「做画面」。**

默认 16:9（1920×1080），开局与用户确认一次（见
`references/workflow/04_svg_stage.md`）。视频不是另一个画幅，而是同一张
16:9 页面上留一个给人物窗口的**排版选择**（见
`references/domain/style_system.md`）。

这里是画幅及其派生度量的**唯一 owner**。此前同一个数字被检查画面、
转换 PPT、渲染、模板 runtime 和状态版本各持一份，只在值不变时才一致；
现在改画幅只需要改这一个文件，其余模块一律从这里取值。

不要在本模块之外新写 1920/1080/13.333 这类字面量。
"""

# ── 画幅本体 ──
FRAME_LABEL = "16:9"
FRAME_W = 1920.0
FRAME_H = 1080.0
FRAME_W_INT = int(FRAME_W)
FRAME_H_INT = int(FRAME_H)
FRAME_VIEWBOX = f"0 0 {FRAME_W_INT} {FRAME_H_INT}"
FRAME_SIZE_ATTRS = f'width="{FRAME_W_INT}" height="{FRAME_H_INT}"'

# 画布 px → 幻灯片 pt 的换算：1920px 对应 13.333in 宽，所以 1px = 0.5pt。
# 见 references/domain/svg_rules.md。
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
SVG_PX_TO_PT = SLIDE_W_IN * 72 / FRAME_W

# ── 画幅派生的版式度量 ──
# 下面这些数字只在当前画幅下有意义，所以和画幅放在一起：改画幅时必须一起复核。
FULL_BLEED_W = 1780.0    # 达到这个尺寸的矩形算整页底／满版块，不计入等面积容器
FULL_BLEED_H = 1040.0
CONTAINER_MIN_W = 200.0  # 小于这个尺寸的矩形不算容器
CONTAINER_MIN_H = 120.0
BODY_TEXT_MAX_Y = 1000.0  # y 超过它的 text 归页脚／页码，不计入正文底部
FOOTER_RULE_Y = 986.0     # 页脚规则的基线位置；正文底部与它之差就是底部空档
SMALL_TEXT_MAX_PX = 22.0  # 不超过它的字号算小字，参与跨页基线统计
