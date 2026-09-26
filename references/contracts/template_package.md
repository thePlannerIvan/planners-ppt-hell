# 可复用模板子流程接口

只在新建严格模板包时使用。模型完成视觉选择，现有 builder / template library 消费下列文件；自主视觉不进入此协议。

所有模板工作文件位于 `_internal/00_project/`。

1. `prepare_visual_references.py <source> --project <project>` 生成 template_visuals；按实际 --help 核对参数。查看全部渲染页，结合结构提取的候选判断什么是稳定品牌身份。
2. `extract_template_assets.py` 提取 template_profile.json 的 structural_extraction 候选。原始 XML 和坐标只提供事实；用实际画面确认，而非把它们当设计结论。
3. 模型补充 profile 的 design_direction 和来源；写 template_asset_registry.json 的 reviewed_source_ids，完整列出 structural_extraction.assets 的 asset_id 与 native_shapes 的 candidate_id，approved/rejected 条目及原因。确保现有背景和标志真实复用。
4. 模型写 template_worker_result.json（保留这一名称以匹配模板库消费者，并不要求子 Agent）：

```json
{"status":"completed","mode":"fidelity","approved_components":[{"component_id":"brand_accent","source_id":"实际候选ID","role":"decoration","placement":"background","geometry_policy":"fixed","text_handling":"strip"}],"layouts":[{"layout_id":"content_base","required_components":["brand_accent"],"optional_components":[]}]}
```

builder 使用源 geometry 和 style 自动换算坐标；改动 geometry_override 必须说明 override_reason，不能把源形状改成另一种东西。content_base 必须开放正文；只锁定真实品牌身份，不锁业务关系和示例文字。一份源候选只定义一个 component。

5. 运行 `scripts/template/build_fidelity_template.py --project <project>`，再运行 `scripts/render_svg_png.py <project>/_internal/00_project/fidelity_template/layout_canvases <project>/_internal/00_project/fidelity_template/canvas_previews`。
6. 查看源页、canvas 大图与两套 contact sheet。模型写 template_canvas_self_review.json 的语义观察：status="completed"、vision_available=true、source_contact_sheet_viewed=true、canvas_contact_sheet_viewed=true、inspection_rounds、source_pages_reviewed（visual manifest 中 image 的文件 stem）、layouts（每个 ID 的 canvas_png_reviewed、compared_source_pages、usable、visual_similarity="pass"、must_fix=[]、retained_features）。这些观察必须源自实际看图。运行 seal_template_review.py <project> 由机器绑定证据 hash。
   **这一步的判据与逐页审阅不同**：逐页审阅问「这个 PPT 做得好不好」，这里问「有没有提炼出足够的模板规律」。别套用同一句结论。
7. `ppt_pipeline.py <project> template --mode fidelity`，然后 `template-review` 打开人审（它是**独立的一个审阅面**：单位 `layout_id`、决定词表 `pass`/`discard`/`revise`、粒度整批、不声明上传能力——与页面审阅逐条独立判过，见 `review_surface.TEMPLATE`）。生成审阅页时写 `template_review_snapshot.json`（review_id、生成时的 template_version、审阅页 HTML hash、**被审的 layout 集合**），页面提交必须带该 `review_id`；**收件层（`template_feedback.consume`）与发布都对照这份快照**，因此旧标签页不能批准新版本。用户逐 canvas 通过／舍弃／返修并命名，结果经宿主原样落盘成 `template_feedback.json`，由 `ppt_pipeline next` 收件、校验、重算派生量并盖章；按所有反馈修订后重建与审阅。
8. 全部通过后 `scripts/template/template_library.py publish <project>`。库发布会验证当前批准与全部证据，其中 **`template_feedback.json` 是唯一的批准凭据**（写者：review server；读者：本发布命令），且它的 `review_id` 必须对应当前这一版审阅页。没有可安全复用的品牌组件时明确说明，用户选择参考模式或新模板，不静默假装 fidelity 成功。

保留：素材、锁层、required components、源页与 canvas 的视觉比较、当前版本人审。无需内容 Layout 审批。模板库发布是显式模板任务的一部分；普通制作不自行扩充库。
