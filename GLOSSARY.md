# Planner's PPT Hell

一个以持久化 SVG 视觉工作台为核心交付物的幻灯片与视频关键帧制作系统；人机在同一个页面修订库中共创、排布、批注与呈现，按需冻结快照输出可编辑 PPTX 或视频关键帧 SVG。

## Language

**Workbench**（视觉工作台）:
人机共同编辑、查看大图、拖动排布、提交局部反馈与演示页面的持久浏览器交互面；它是本系统的主交付物与默认工作终点。
_Avoid_: Review Gate, Approval Page, Preview Server

**Store**（版本库）:
唯一持有页序、不可变 SVG 修订版、冻结资产、人工修改守卫、待办任务与冻结快照的持久化修订仓库。
_Avoid_: Live SVG Directory, Working Copy

**Revision**（页面修订版）:
单个页面在某一时刻的不可变快照，绑定其 SVG 源码、备注、引用资产与当次使用的版式标识。
_Avoid_: Draft File, Version Number

**Guard**（人工修改守卫）:
用户在工作台直接修改某个元素文字时，系统同步对该元素的文本内容与几何坐标（`x`、`y`、`transform`）施加的自动保护锁，防止整页重画时静默覆盖人类意图。
_Avoid_: Lock Layer, Read-Only Flag

**Template Pack**（模板包）:
一套可复用的视觉皮肤与骨架资产包，由 **Theme** 与 **Layouts** 两层组成。
_Avoid_: Fidelity Template, Style Pack, Theme Library

**Theme**（主题）:
模板包中跨页共享的视觉身份层，包含色彩与字阶令牌（`tokens.css`）、画布底壳（`skyline_shell.svg`）与视觉规范说明书（`SPEC.md`）。
_Avoid_: Master Slide, Color Scheme

**Layout**（版式）:
模板包内单个具名页面的空间骨架参考（由 `layout_id` 与参考 `primitive` SVG 组成），作为排版的参考起点而非强制锁层。
_Avoid_: Wireframe, Canvas Lock

**Universal Mechanics**（通用构图力学）:
与具体视觉皮肤无关的跨项目信息组织法则，决定单页核心主张、单一视觉焦点与高密/低密双模式调度，但不越权覆盖已选模板包的视觉风格。
_Avoid_: Global Style Rules, Fixed Coordinate Standard

**Snapshot**（冻结快照）:
在用户显式要求导出可编辑 PPTX 或下游视频需要固定版本交接时，从 Store 按当前页序与页面修订版生成的不可变只读数据包。
_Avoid_: Final State, Project Completion
