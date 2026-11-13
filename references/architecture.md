# 职责与接口

本 Skill 把内容与视觉参考制作成可持续编辑的 SVG 画面，输出 PPT 或视频 SVG，按需固定交接快照。工作台与版本机制共用；输入适配、使用条件和输出能力按路线处理。

## 唯一主人

| 决定 | 唯一主人与接口 | 调用方的职责 |
|---|---|---|
| 内容、来源、分页与叙事 | 当前内容稿；Bypage 与 visual-plan 是可选输入适配，见 [内容接收](workflow/02_content_stage.md) | 页面设计保留事实与身份；需要拆页或改写时更新内容并保留变化，不为套样张删证据 |
| 文案表达 | slide-copy（PPT 按需调用）；视频沿用上屏稿 | 采用适合该页任务的表达，不从文案规范继承固定构图 |
| 项目用途与视觉选择 | `design_direction.md`；机器画幅保存在 `page_manifest.json.canvas`，由 `canvas_frame.py` 解释 | 记录所选视觉来源和项目调整；方向文档引用机器画幅，不维护第二份数值 |
| 模板的定义与复用范围 | [模板契约](contracts/template_package.md) | 提取流程据此生产，页面设计据此使用，不各自重定义模板 |
| 视觉身份 | 所选模板，或本 Skill 自己维护的视频风格文档（`references/domain/video_style_*.md` + 随包参考图）；共享数值在其 tokens/风格文档，SPEC 解释用途，样张表达实际效果 | 项目选择引用它；页面设计按内容重组；临时参考不必先制成模板包；不读取或注册 `video-craft` 的主题库 |
| 当前页面的构图 | 页面设计，见 [制作](workflow/04_svg_stage.md)；[视觉判断](domain/style_system.md)与[版式参考](domain/layout_taxonomy.md)供判断 | 内容、模板及技术能力是输入；原语坐标属于该原语，不自动成为全局坐标 |
| SVG 渲染与 PPT 转换能力 | 对应渲染器/转换器实现与测试；`validate_svg_layout.py` 执行路线检查 | 技术文档说明用法与限制；不定义配色、留白或页面骨架 |
| 图片槽位与源图比例测量 | `image_diagnostics.py`；frames 与 validator 共用 | 只报告预计裁切/填充和测量限制，页面设计结合实际图判断 |
| 页面文案对表 | `copy_audit.py` 读取内容入口确认的 page_content 与既有来源绑定 | 不另造权威稿；只提示疑似新增文字，未确认明确 unchecked |
| 页面集合、页序、版本、用户保护、资产与快照 | `workbench_store.py`，add_page / delete_page / order、checkout → save / snapshot；save 输出 changes；人保存时按请求排队 `render_revision.py` 重渲该页位图（只写回仍是当前版本的那一次） | 浏览器、模型与导出使用同一接口，不写兼容视图代替提交 |
| 模板包校验、确认与入库 | `template_library.py` 与模板审阅接口 | 普通制作不承担入库流程；入库批准绑定当前包 |
| 模板版式目录与选择 | `template/layout_index.py` 只读包；工作台任务携带 `template_id` / `layout_id` | 画廊不复制第二份版式清单，执行归页面设计；版式是参考不是锁层 |
| 原生 layout 目录与模板脚手架 | `template/layout_catalog.py` 读 PPTX master/layout；`template/scaffold_template_pack.py` 写 tokens/SPEC/shell/layouts | 只写有据可依的值；设计哲学与 primitive 归模型，最终仍走模板人工审阅 |
| 视频合成及动效字段 | 可选：作者明确要做元素级动效时才按 Video Craft 的 composition / SVG animation 契约准备元素与分组 | 默认不要求 id / step / anchor；没有这些，Craft 按整页画面使用或自行重排。实际动画、时间轴与声音归 Craft |

## 两条路线

PPT：材料或逐页稿 → 内容适配 → 画面设计 → store → PPT 能力检查 → PPTX 与实际渲染复核。
视频：材料/上屏稿或 visual-plan → 内容适配 → 画面设计 → store → SVG 与关联素材 → Craft（固定版本交接按需快照）。
直接输入同样可制作；没有上游核查或录音绑定时如实标记，不制造生产包。独立视频快照可用于画面审阅，进入录音合成前由下游建立脚本与时间绑定。

两路共享项目方向、页面设计、保存与快照；PPT 可编辑性限制不套到视频。输入适配定义怎样读取既有产物，不要求用户先运行某个 Skill。

## 数据流与修改范围

视觉参考 → [提取流程](workflow/01_template_intake.md) → 模板；内容与项目选择 → 模板辅助的页面设计 → 保存 → 按路线检查和输出。
检查器读取项目画幅，冻结输出读取快照画幅；改变模板不改变历史 SVG。模板内部 tokens 是数值来源，SPEC 引用其语义，SVG 是实现，PNG 是视觉证据。
修改主题只影响主题；修改转换能力只影响对应出口；修改版本机制服务两路。`SKILL.md` 负责导航，不复制这些所有权。工程与测试入口见 [ARCHITECTURE](../docs/ARCHITECTURE.md)。
