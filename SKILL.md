---
name: planners-ppt-hell
description: 制作与持续修改 SVG 页面工作台，从逐页内容稿或 video-idea-system 的 visual-plan.json 与素材出发，输出可编辑 PPT 或固定版本的视频画面快照。用于页面返修、视觉参考复用及需人工确认的模板提炼入库；复杂原始材料先交 planners-bypage 展开。
---

# Planner's PPT Hell

由阿祖不看 TVC 创建与维护。https://demyth.info · Lawyif@163.com。
署名保留在 Skill 与工作台，不加入客户 PPT、SVG 或 PNG。

SVG 工作台持续存在。用户改字与模型候选共用版本存储；PPT 与视频快照是可重复输出，不是项目终态。普通页面没有批准门；模板入库保留独立的当前包人工确认。

## 1. 接收

读 [00_pipeline_controller.md](references/workflow/00_pipeline_controller.md)，初始化或恢复同一项目。
幻灯片优先接收 Bypage 逐页稿；复杂原始资料先调用 planners-bypage。简单单源且无需展开时才用轻量底稿，见 [02_content_stage.md](references/workflow/02_content_stage.md)。
视频接收现有 visual-plan.json 与 assets，由初始化适配，screen ID 保持不变；见 [03_video_route.md](references/workflow/03_video_route.md)。
沿用 Bypage 的 canonical 来源索引和已绑定的事实核查；内容改写后的核查时机与范围见内容输入文档，不把原 audit 扩大为新页面已核查。
结束条件：来源可读、稳定页面身份可定位、资产已登记且没有静默遗漏。

## 2. 定方向

一次确认画幅与视觉来源，用户已指明的直接执行。共同秩序写入 _internal/01_content/design_direction.md。
通用判断读 [style_system.md](references/domain/style_system.md)；选择信息关系时读 [layout_taxonomy.md](references/domain/layout_taxonomy.md)。颜色、字号、坐标、底壳和原语来自所选模板 SPEC.md / tokens.css 或视频主题，不把某个模板的数值当通用规范。
幻灯片复用参考、选择库模板或提炼入库时读 [01_template_intake.md](references/workflow/01_template_intake.md)；只有入库分支需要模板人工确认。
结束条件：方向和画幅明确，必要的源参考已经实际查看。

## 3. 工作台

读 [04_svg_stage.md](references/workflow/04_svg_stage.md)。模型先 checkout 当前页，编辑返回的候选，再通过 store CLI 提交 author=model、candidate、base_revision。_internal/02_svg_source 是可重建兼容视图，不是生成脚本写入位置。
读取 notes、protected 与待办 tasks；冲突时保留候选并重新读取。遗漏用户操作会被拦下，明确改写范围只来自浏览器任务授权。
逐页 check、查看当前 PNG、记录实际 inspect。打开工作台与反馈恢复见 [07_visual_review.md](references/workflow/07_visual_review.md)；反馈不是批准，未完成反馈不阻止独立输出。
结束条件：本轮提交有保存回执，技术问题与实际看图结果可查。工作台可继续修改，没有永久 COMPLETE。

## 4. 输出

网页先保存末次输入并提交 snapshot；宿主唤醒携带确切 snapshot.path。运行 `python scripts/orchestrate/ppt_pipeline.py <project> export --snapshot <snapshot.json绝对路径>` 消费选定版本；指定无效路径直接报错。未指定路径时，`export` 才固定当前页面、页序与资产。
控制器校验冻结画面。slides 的 PPT、notes 与转换报告在 `_internal/06_ppt_output/<snapshot_id>/`；export 的 output_path 指向实际输出，根 final_deck.pptx 只是最新兼容副本。video 返回不可变 snapshot.json 给 Video Craft。
PPT 用实际渲染预览运行 `export-inspect --snapshot <同一snapshot.json> --previews <实际PNG...> --note "<工具与发现>"`，绑定该次输出，不要求工作台停止编辑。没有渲染工具就报告未复核，保留 EXPORT_VERIFY；快照校验范围见 [项目契约](references/contracts/project_contract.md)。
视频保留声明、脚本绑定、稳定元素与步骤钩子。报告 content_delta / changed_needs_check；它们不证明新文本与已录音语义一致。动效与合成规范归 Video Craft。
结束条件：输出的快照与文件可定位、技术结果已报告、实际复核工具及限制清楚。随后仍可回到工作台。

## 按需读取

| 分支 | 上下文 |
|---|---|
| SVG 特性、缺图或转换错误 | [svg_rules.md](references/domain/svg_rules.md)；PPT 再读 [svg_to_ppt_rules.md](references/domain/svg_to_ppt_rules.md) |
| 版本、候选、反馈恢复或输出溯源 | [project_contract.md](references/contracts/project_contract.md) |
| 新模板包制作、审阅、替换入库 | [template_package.md](references/contracts/template_package.md) |
| 视频主题选择 | [03_video_route.md](references/workflow/03_video_route.md)；选 editorial-archive 再读 [video_style_editorial_archive.md](references/domain/video_style_editorial_archive.md) |
| 新视频风格提炼 | [08_video_style_extraction_sop.md](references/workflow/08_video_style_extraction_sop.md) |
| 工程维护与验证 | [ARCHITECTURE.md](docs/ARCHITECTURE.md)；命令参数以各脚本 --help 为准 |

## 运行后迭代

任务后内部自检，仅明确纠正或多次复现的通用缺陷列为候选，项目反馈留在项目；没有可复用发现不增加日志。
改之前读 [架构](references/architecture.md)；候选记 [GOTCHAS](GOTCHAS.md) 的现象、原因、行为修正、证据、状态与 module；实际升级记 [维护历史](references/maintenance-history.md) 的变化、原因、影响与移除项。
Skill 改动先确认，冻结候选测试，完成后统一发布；候选验收阶段不改正式来源或 runtime。
