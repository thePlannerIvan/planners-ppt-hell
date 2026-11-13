---
name: planners-ppt-hell
description: 制作与持续修改 SVG 页面工作台，从逐页内容稿或 video-idea-system 的 visual-plan.json 与素材出发，输出可编辑 PPT 或视频 SVG 文件。用于直接材料或生产包的页面制作、返修、视觉参考复用及需人工确认的模板提炼入库。
---

# Planner's PPT Hell

由阿祖不看 TVC 创建与维护。https://demyth.info · Lawyif@163.com。
署名保留在 Skill 与工作台，不加入客户 PPT、SVG 或 PNG。

SVG 工作台持续存在。用户改字与模型候选共用版本存储；PPT 与视频快照是可重复输出，不是项目终态。普通页面没有批准门；模板入库保留独立的当前包人工确认。

## 1. 接收

职责与接口见 [架构](references/architecture.md)。读 [00_pipeline_controller.md](references/workflow/00_pipeline_controller.md)，初始化或恢复同一项目。
幻灯片可接收 Bypage 逐页稿，也可从用户材料、已有稿件或需求直接整理内容；按复杂度调用 Bypage，不把它设为前置门。见 [02_content_stage.md](references/workflow/02_content_stage.md)。
视频可适配 visual-plan.json 与 assets，也可直接接收上屏稿或材料；已有 screen ID 保持不变。见 [03_video_route.md](references/workflow/03_video_route.md)。
接收 Bypage 成品时沿用其 canonical 来源索引和已绑定的事实核查；内容改写后的核查时机与范围见内容输入文档，不把原 audit 扩大为新页面已核查。
结束条件：来源可读、稳定页面身份可定位、资产已登记且没有静默遗漏。

## 2. 定方向

一次确认画幅与视觉来源，用户已指明的直接执行。共同秩序写入 _internal/01_content/design_direction.md。
通用判断读 [style_system.md](references/domain/style_system.md)；选择信息关系时读 [layout_taxonomy.md](references/domain/layout_taxonomy.md)。模板含义以 [模板契约](references/contracts/template_package.md) 为准；开画前读取所选模板或视频风格文档并实际查看样张；没有模板时查看本次参考，具体构图由当前内容决定。
模板是「主题 + 一组具名版式」：主题定 tokens、底壳与 SPEC，版式是某一页的参考骨架。工作台里整套选模板、逐页选版式都只是给模型的一条请求，不是页面自动重绘。
提取生产（PPTX / PDF）：`extract_template_pack.py` 现在同时产出原生 `layout_catalog.json`；`scaffold_template_pack.py` 写 tokens/SPEC/shell/layouts；`template-select` 由人勾选结构家族，`apply_layout_selection.py` 收窄 `layouts.json`；模型只做被选中的 primitive，最后 `template-review` 批准。
幻灯片复用参考、选择库模板或提炼入库时读 [01_template_intake.md](references/workflow/01_template_intake.md)；只有入库分支需要模板人工确认。
结束条件：方向和画幅明确，必要的源参考已经实际查看。

## 3. 工作台

读 [04_svg_stage.md](references/workflow/04_svg_stage.md)。模型可以通过 store CLI 新增或删除页面；新增页提交完整 candidate 与 page 元数据，删除页提交 page_key、base_revision 与 base_order。已有页先 checkout 当前页，编辑返回的候选，再提交 author=model、candidate、base_revision。_internal/02_svg_source 是可重建兼容视图，不是生成脚本写入位置。
读取 notes、protected 与待办 tasks；冲突时保留候选并重新读取。遗漏用户操作会被拦下，明确改写范围只来自浏览器任务授权。
工作台的「模板 / 版式」是请求入口：整套模板与逐页参考版式跟意见一起提交成 store 任务（任务 `template_id`、页面 `layout_id`）。DSH 当场唤醒模型；本地宿主只把任务落盘，等模型下次读到。模型按任务 checkout 该页，以所选版式为参考重排，保存时带 `layout_id`，在回执里说明保留与偏离。版式是参考，不是锁层：内容放不下时，这页的主张与证据优先。
用 check --summary 批量检查本轮页面，再逐页查看当前 PNG、记录实际 inspect。打开工作台与反馈恢复见 [07_visual_review.md](references/workflow/07_visual_review.md)；反馈不是批准，未完成反馈不阻止独立输出。运行在 DSH 时用 `review_open` 自动加载同一工作台到侧栏；非 DSH 自动启动或复用 `planners-review-core` 本地宿主。两路共用同一份 Workbench Store、草稿和命令回执。
结束条件：本轮提交有保存回执，技术问题与实际看图结果可查。工作台可继续修改，没有永久 COMPLETE。

## 4. 输出

PPT 输出或需要固定版本交接时，网页先保存末次输入、页序和页面集合并提交 snapshot；宿主唤醒携带确切 snapshot.path。运行 `python scripts/orchestrate/ppt_pipeline.py <project> export --snapshot <snapshot.json绝对路径>` 消费选定版本；指定无效路径直接报错。未指定路径时，`export` 才固定当前页面、页序与资产。
控制器校验冻结画面。slides 的 PPT、notes 与转换报告在 `_internal/06_ppt_output/<snapshot_id>/`；export 的 output_path 指向实际输出，根 final_deck.pptx 只是最新兼容副本。视频默认直接交付已保存的 SVG 与关联素材，见视频路线；需要固定版本交接时可生成快照。
PPT 用实际渲染预览运行 `export-inspect --snapshot <同一snapshot.json> --previews <实际PNG...> --note "<工具与发现>"`，绑定该次输出，不要求工作台停止编辑。没有渲染工具就报告未复核，保留 EXPORT_VERIFY；快照校验范围见 [项目契约](references/contracts/project_contract.md)。
视频交付当前保存版本的 SVG、关联素材、页序与 notes，不要求额外 export；元素 id、步骤钩子、脚本绑定都是可选增强，不要求。如使用快照，报告 content_delta / changed_needs_check；它们不证明新文本与已录音语义一致。动效与合成规范归 Video Craft。
结束条件：交付文件与对应版本可定位、技术结果已报告、实际复核工具及限制清楚。随后仍可回到工作台。

## 按需读取

| 分支 | 上下文 |
|---|---|
| SVG 特性、缺图或转换错误 | [svg_rules.md](references/domain/svg_rules.md)；PPT 再读 [svg_to_ppt_rules.md](references/domain/svg_to_ppt_rules.md) |
| 版本、候选、反馈恢复或输出溯源 | [project_contract.md](references/contracts/project_contract.md) |
| 新模板包制作、审阅、替换入库 | [template_package.md](references/contracts/template_package.md)；提取生产流程见 [01_template_intake.md](references/workflow/01_template_intake.md) |
| 视频风格选择（私有风格库挂载与开源通用降级） | [03_video_route.md](references/workflow/03_video_route.md)；运行 `python3 scripts/resolve_video_vault.py --style <style_id>` 读取 `~/.config/planners/video-vault/styles/<style_id>/page.md` 与 `anchors/`（无私有库时自动降级为 `default-clean`） |
| 新视频风格提炼 | [08_video_style_extraction_sop.md](references/workflow/08_video_style_extraction_sop.md) |
| 工程维护与验证 | [ARCHITECTURE.md](docs/ARCHITECTURE.md)；命令参数以各脚本 --help 为准 |

## 运行后迭代

任务后内部自检，仅明确纠正或多次复现的通用缺陷列为候选，项目反馈留在项目；没有可复用发现不增加日志。
改之前读 [架构](references/architecture.md)；候选记 [GOTCHAS](GOTCHAS.md) 的现象、原因、行为修正、证据、状态与 module；实际升级记 [维护历史](references/maintenance-history.md) 的变化、原因、影响与移除项。
Skill 改动先确认，冻结候选测试，完成后统一发布；候选验收阶段不改正式来源或 runtime。
