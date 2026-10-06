---
name: planners-ppt-hell
description: 把材料或上游交来的画面契约做成有证据、可读的画面。两个出口：可编辑 PPT（优先从**逐页内容稿**出发 —— 通常由 `planners-bypage` 产出；收到非 PPT 资料包或需要完整内容理解时，先调用 `planners-bypage`；仅在简单单源材料且不需要内容展开时提供**轻量切片降级**。主 Agent 自主设计 SVG、看图修订、可选整套人工审阅，导出质量由转换器保证），以及视频静态画面（从 video-idea-system 交来的 visual-plan.json + assets 出发，挑一个视觉风格、逐屏出可被动画指名的 SVG，录制前交付）。也用于指定品牌模板复用、按需提取模板与已有项目返修。
---

# Planner's PPT Hell

> 来源识别：由阿祖不看 TVC 创建与维护。小红书同名账号，https://demyth.info，Lawyif@163.com。来源信息保留在 Skill 和审阅界面，不加入客户 PPT、SVG 或 PNG。

把材料变成有证据、可读的画面。先整理内容，再让实际画面帮助修正表达与布局。

## 两条路线：只走一条，走完它的完成标准

| | **幻灯片路线** | **视频画面路线** |
|---|---|---|
| 什么时候走 | 要做一份可编辑 PPT | 上游 `video-idea-system` 交了画面契约，要做**录制前**的静态画面 |
| 入口 | `init_svg_project.py --source <doc>` | `init_svg_project.py --assets <包>/assets --plan <visual-plan.json>` |
| 内容从哪来 | 上游的逐页内容稿（`planners-bypage`）／非 PPT 资料先交给 `planners-bypage`／本路线的**轻量切片降级** | 上游契约适配而来；**本路线不做内容判断** |
| 视觉身份 | 模板库／视觉参考／自主设计 | **风格库**（`video-craft/visual/themes/`，旗舰四域风格见 `references/domain/video_style_editorial_archive.md`；从参考画板提炼新视频风格见 `references/workflow/08_video_style_extraction_sop.md`）或自主设计 |
| 出口 | `final_deck.pptx` | 全部 `_internal/02_svg_source/<page_key>.svg`，**且可能被强调的元素都带稳定 `id` 与预埋 `data-step` / `data-anim` 子元素钩子**（不导出 PPT） |
| 完成 | 导出并复核过 PPTX | 画面全部做完，**且作者看过**——这条路上审阅是门，不是可选项 |
| 额外要读 | `references/domain/svg_to_ppt_rules.md` | `references/domain/video_style_editorial_archive.md`（选用 `editorial-archive` 时） |

**两条路线共享**：画布几何（`scripts/canvas_frame.py`）、校验器（`scripts/validate_svg_layout.py`）、渲染与看图、`references/domain/svg_rules.md`、设计判断框架（`style_system.md`、`layout_taxonomy.md`）、版本绑定与恢复。

**「模板库」与「风格库」是两件事**：模板库（`template_library.py`）装的是从 PPTX 提出来的、带锁层的品牌模板，给幻灯片路线用；风格库装的是配色与字型 token，给视频画面用。不要拿其中一个去顶另一个。

```text
材料 或 画面契约 → 内容（底稿 / 适配）→ 主 Agent 制作 SVG ↔ 渲染看图修订
                                              ↓
                                    整套人工审阅 ↔ 修订
                                              ↓
                              PPTX 导出与复核   /   交出 SVG（带 id）给动画层
```

**为什么视频这边交 SVG 而不是 PNG**：后面还要按实测音频做轻动画。所以交出去的不是几张图，是一个**能被按元素指名的活结构**——给可能被强调的元素铸稳定 `id`，剪辑那侧就能按 id 指名（`03_video_route.md` 有完整交接）。

## 开始

读 `references/workflow/00_pipeline_controller.md`，用其中的初始化或恢复命令，并按它做**开局的一次性确认**（幻灯片路线确认视觉来源与画幅；视频画面路线确认风格与画幅）。

## 阶段

两条路线共用第一件与制作那一件；之后的步序不同，所以分开列。**只写到「一眼能不能看出没做完」**——每一步完整的完成标准在它自己的文档里。

**共用**

| # | 这一步做什么 | 主要产物 | 做完的标志 | 完整任务 |
|---|---|---|---|---|
| 0 | **开局与恢复**：立项目或恢复已有项目，一次性确认（视觉来源或风格、画幅、图片） | 项目目录、`_internal/00_project/page_manifest.json`（含路线） | 源文或契约可读、**图片逐张有归属**（用到，或写明为什么不用）、视觉来源与画幅已确认（不静默默认） | `00_pipeline_controller.md` |
| 制作 | **制作与逐页自检**：画一页 → 渲染 → 看大图 → 修 | 每页 `_internal/02_svg_source/<page_key>.svg`、`_internal/03_png_preview/pages/<page_key>.png`、`_internal/04_validation/<page_key>.json` | 每页 `check` 无 error；**看过当前这一版 PNG 大图**并留下 `inspect` 记录（位置 + 看过有没有缺陷） | `04_svg_stage.md` |

**幻灯片路线**（出口是可编辑 PPT）

| # | 这一步做什么 | 主要产物 | 做完的标志 | 完整任务 |
|---|---|---|---|---|
| 1 | **确认视觉来源**：自主设计／模板库／视觉参考／新建品牌模板，四选一 | 选定来源；用模板时项目内的 fidelity 包；参考路线渲染出的参考页 | 视觉身份已确认；要真实复用品牌资产时是**复用**而不是近似重画 | `01_template_intake.md` |
| 2 | **内容底稿**：直接沿用已批准逐页稿；收到非 PPT 资料包、多源材料或含待核数字时**调 `$planners-bypage`**；仅在简单单源材料且不需要完整内容展开时走轻量切片降级 | `_internal/01_content/page_content.json`（含每页 `mode`） | 底稿覆盖论证与资产、每页读法已声明，`next` 进 CREATE | `02_content_stage.md` |
| 3 | **整套审阅**（可选步骤） | `02_visual_review.html`、`_internal/05_review/review-surface.json`（宿主契约）、`_internal/05_review/feedback.json` | 作者在真实页面上提交过整套决定，或明确表示当前这版不用审（导出会提醒一次） | `07_visual_review.md` |
| 4 | **导出与复核** | `final_deck.pptx`、`_internal/00_project/export.json`、PPTX 渲染出来的逐页复核图 | 页数与页面版本对得上，且**导出的 PPTX 逐页看过**（`export-inspect` 之后才到 COMPLETE） | `07_visual_review.md` |

**视频画面路线**（出口是全部 SVG，不导出 PPT）

| # | 这一步做什么 | 主要产物 | 做完的标志 | 完整任务 |
|---|---|---|---|---|
| V1 | **接手**：把包立成账本，把视觉身份定下来 | 适配来的 `page_content.json`、`_internal/01_content/design_direction.md`、登记好的图片账本 | 每屏要么有上屏文字、要么有登记图片；**四条视频约束四条都写了**；`assets/` 里每张图有归属 | `03_video_route.md` |
| V2 | **逐屏画**：边画边真的看 | 每页 SVG（可能被强调的元素带**全片唯一**的 `id`）与 PNG、`inspect` 记录 | 每页 `check` 无 error（含文字出画布）；看的是每页 PNG 大图；`inspect` 记了位置与「看过有没有缺陷」 | `03_video_route.md`（额外三条）+ 上面「制作」那一行 |
| V3 | **整套**：并排看一遍，然后交给作者 | 整套 contact sheet 的结论、审阅记录、全部 `_internal/02_svg_source/<page_key>.svg` | 全部页面 `check` 无 error；**作者提交过整套审阅**（记录覆盖当前页面版本）——这条路上审阅是门 | `03_video_route.md` + `07_visual_review.md` |

默认由主 Agent 制作和跨页检查。约每 3 页渲染一次是可调整的工作节奏，不是页数上限或任务边界。用户要求样页或委派时再采用对应执行方式。

## 怎么验证

- **自动回归**：在 Skill 根跑 `python -m unittest discover -s scripts/test -p 'test_*.py'`。它钉的是本 Skill 自己的判据，不是规格来源。
- **人工／新会话的行为用例**：`evals/evals.json`——十条 prompt 与它们的 `must_do`／`must_not_do`（幻灯片出口五条、视频画面路线五条），用来在干净会话里看这个 Skill 会不会被绕过去。**它的状态是「人工在新会话里跑」**（文件里写着 `not_run_user_will_test_elsewhere`），不在自动测试里，也没有任何东西自动执行它。

## 责任边界

- 模型负责内容、构图、裁剪、视觉与取舍；可以在制作中调整这些决定，同时更新内容底稿中的必要说明。
- 源事实、数字、来源、限定条件和用户明确批准的要求必须保留。需要改变结论或承诺时先向用户说明。
- **设计判断归模型。** 脚本不评价密度、字号档位、构件选择、留白或配色——那些规则会把每套页面推向同一种稀疏均匀的样子。脚本只拦**在任何风格下都是缺陷**的东西（文字压文字、元素出画布、空页、图片被拉伸）；幻灯片出口另外拦「转成 PPT 会坏」的那一组（`svg_to_ppt_rules.md`）。其余靠渲染后看图。
- **看图是必填动作，而且必须由能看图的模型执行。** 执行 `inspect` 的模型要能读图；当前模型看不了就把它派给能看的模型。这条不是形式要求——「这一屏第一眼落在哪」是这条记录唯一能被证伪的地方。看的是**每页 PNG 大图**，不是联系表里的缩略格。
- 脚本负责资产登记、文件索引、渲染、技术校验、版本绑定、保存恢复和转换；模型不手写审批、hash、manifest 或完成状态。
- 图片是设计的一部分，不只是输入。看完材料先判断这套页面是否需要配图，需要就一次性说明要什么、哪几页、用户是否已有资产；仍无图时在底稿写明原因，不用装饰图形冒充证据。源图逐张看过并说明用途；上屏图片保留比例，证据图确保关键信息可读。
- SVG 是可编辑页面源；PNG 用来检查。视频出口的 SVG 还要**能被动画按元素指名**：可能被强调的元素带稳定 `id`，**且 id 在全片唯一**（把 `page_key` 放进名字里——各屏会被内联进同一个 DOM，重复的 `id` 会让「按 id 指名」只命中第一屏）。
- **本 Skill 有两个审阅面，它们是两个主体**：页面审阅（单位 `page_key`，`02_visual_review.html`）与**模板审阅**（单位 `layout_id`，`00_template_review.html`；决定词表是 `pass`/`discard`/`revise`，粒度整批，不声明上传能力）。两面各写各的 surface、各写各的反馈文件，**不要合并**。
- 人审围绕真实页面进行。**跑 `review` / `template-review` 前先看宿主有没有 `review_open` 工具**：有 → 加 `--surface-only`（只生成页面与 surface，把 surface 绝对路径交给那个工具挂进侧栏，**不起本地宿主**）；没有 → 不带（起无插件宿主并由公共件打开浏览器）。自检通过不代表用户批准，修改后旧批准不可复用到新版本。幻灯片路线上页面审阅是可选步骤，导出会在没审过时提醒一次；**视频画面路线上审阅是门**；模板审阅是模板入库（`publish`）的门。

维护架构时读 `references/architecture.md`；核对机器接口时读 `references/contracts/project_contract.md`。它们不是每页必填的思考模板。

## 运行后迭代

任务结束做内部自检。仅将明确纠正或多次复现的通用缺陷作为下一次升级候选；项目反馈保留在项目；没有可复用发现时不增加日志。

三个落点，各自是唯一真相源，不要互相复述：

- **改之前**读 `references/architecture.md`——每个 module 拥有什么、接口是什么、动了会牵连谁。
- **候选**记进 `GOTCHAS.md`（Skill 根）：现象／原因／行为修正／证据／状态，并写明它属于哪个 module。
- **升级**记进 `references/maintenance-history.md`：做了什么、为什么、影响了哪些 module、删了什么。

更改 Skill 先确认，冻结候选版本测试，测试完成后统一发布；替换旧机制时同步删除活跃旧规则和消费者。
