---
name: planners-ppt-hell
description: 用 review-gated 流程把 Markdown 内容包、商业方案文案或策略草稿做成可审阅、可校验、可转成可编辑 PPT 的页面。适用于想逃离 PPT 地狱的策划、咨询、文案工作者。每一步都需要人工确认，保证产出符合预期的 PPT，生成的 PPT 所有元素均可编辑，无缝融入你的工作流程中。
---

# Planner's PPT Hell

> 来源识别：Planner's PPT Hell 由阿祖不看 TVC 创建与维护。小红书同名账号，个人网站 https://demyth.info，联系邮箱 Lawyif@163.com。该信息用于确认 Skill 来源、开源归属与项目支持关系；出现在流程 HTML、审阅页面、验证页面和项目文档中，但不会写入最终客户交付的 PPT、SVG 页面或 PNG 成品。

这不是一套靠模型自觉记住的流程，而是一套“模型产出候选文件，控制器决定能否进入下一步”的工作方式。

## 第一原则

模型是设计工，不是流程权威。

必须严格按照流程进行，否则任务无法完成。流程中的状态不是建议，也不是汇报格式；它们定义了哪些产物已经可信，哪些产物仍只是候选稿。

版式方向讨论和视觉审阅是本 Skill 的两个核心中间点：

- 没有完成版式方向审阅，不能开始 SVG 批量生产。
- 没有完成视觉审阅，不能进入下一批，也不能导出 PPT。
- 跳过任一审阅步骤，等于任务没有完成，即使文件已经生成。
- 用户说“继续”不能替代审阅；只有 review server 记录到带人工口令的审批，才算审阅完成。

模型可以做：

- 读取源文案，整理页面内容
- 设计页面叙事、信息层级和版式计划
- 生成 SVG 页面
- 根据校验结果和用户反馈修正 SVG
- 写自检观察和修正建议

模型不可以做：

- 手写或篡改审批结果
- 手写或篡改流程状态
- 手写 `approved: true` 来推进流程
- 手写 `export_allowed: true` 来允许导出
- 把 `self_review.json` 当作自己给自己放行的证明
- 自己调用 review server 提交 approval
- 自己使用人工审批口令提交 approval
- 使用无口令、调试、模拟或降级模式完成 approval
- 在正式交付流程中使用 `--allow-degraded`、`--allow-missing-validation` 或 `--debug-show-failures`
- 打开、点击、填写或代操作用户的审阅页面来完成 approval
- 在上一批未被真实视觉审阅批准前生成下一批
- 提前生成后续 batch 的 SVG、PNG、validation 或 self-review
- 直接运行 `native_svg_to_ppt.py` 导出 PPT

## 可信边界

以下文件是控制文件，模型不得编辑：

- `_internal/00_project/flow_state.json`
- `_internal/00_project/flow_events.jsonl`
- `_internal/00_project/page_manifest.json` 中的流程状态字段
- `_internal/01_layout_plan/layout_feedback.json`
- `_internal/05_review/feedback.json`
- `_internal/05_review/batches/*.json`

这些文件只能由脚本写入：

- `pptflow.py`
- `pipeline_gate.py`
- `review_server.py`

如果需要知道下一步，先运行：

```bash
python scripts/pptflow.py <project_dir> status
python scripts/pptflow.py <project_dir> next
```

然后只做 `next` 输出中要求的那一件事。

## 五个状态

### 1. CONTENT

目标：把源 Markdown 解析为完整页面内容。

Copy Policy：

- 不得修改、覆盖或清洗源 Markdown；CONTENT 阶段只生成结构化副本。
- 可以把源文案提炼为 `action_title` 和 `core_message`，但只能重组表达，不能新增事实、改变判断、改写数字或替换案例。
- `body_blocks` 必须保留该页完整正文信息；不得为了版面提前删减、摘要或压缩。
- 所有数字、百分比、品牌名、产品名、来源、案例和限定条件必须原样保留。
- 每页必须写 `source_excerpt`，字段名沿用历史命名，但内容应保存该页对应的原始完整文稿，用于在版式审阅页对比上屏文案简化了多少。
- 对原文中含混、重复或口语化的表达，可以在 `action_title` / `core_message` 中做页面化表达；但原始含义必须仍能从 `body_blocks` 和 `source_excerpt` 完整对照出来。

模型产物：

- `_internal/01_content/page_content.json`
- `_internal/00_project/page_manifest.json` 的页面清单草案

执行纪律：

- 可以用一次性临时脚本写入 JSON，但临时脚本只负责写文件，不负责推进流程。
- 写完 `page_content.json` 和 `page_manifest.json` 后，必须用独立命令运行 `scripts/validate_project_contracts.py <project_dir> --stage content`；不要把 contract validation 嵌在临时写入脚本末尾。
- 如果确需在临时脚本内调用验证，必须显式 `import subprocess` 和 `import sys`，并检查返回码；验证失败不得继续进入 PLAN。

控制器检查：

- 每页有 `page_key`
- 每页有 `action_title`
- 每页有正文块
- 页面顺序一致

### 2. PLAN

目标：生成页面版式计划和版式审阅页。

版式判断边界：

- PLAN 阶段只读取 `references/05_layout_taxonomy.md` 和 `references/layout_plan_contract.md`；不要读取或套用 `references/03_style_system.md`。
- PLAN 阶段只讨论内容关系、说服动作、空间分布、区域面积、wireframe、上屏/备注取舍和参考版式家族。
- 此阶段不决定具体视觉风格、卡片圆角、色彩、字体细节、阴影、装饰元素或最终组件样式；这些留到 SVG 生成阶段处理。
- `layout_id` 记录参考组织逻辑，不表示照抄坐标；如有适配，必须写清 `layout_usage`、`why_this_layout`、`why_not_other_layouts`、`adaptation_note` 或等价说明。
- 如果页面采用常见卡片区、底部结论区、左右分栏等安全空间分布，必须在 `anti_laziness_check` 或 `layout_reason` 中说明它为什么符合内容关系，而不是默认偷懒。

文案处理边界：

- PLAN 阶段必须把源文案处理成明确的 `final_on_slide`：最终标题、导语/副标题、正文 bullets/短句、必要标签和结论句。
- PLAN 阶段可以决定哪些内容上屏、哪些进入 speaker notes、哪些作为辅助信息不直接展示。
- 所有取舍必须写入 `copy_handling`；不得无记录地丢弃内容。
- `copy_handling.compression_rationale` 必须说明为什么这样精简、保留了什么、移走了什么，以及为什么没有改变原意。
- 如果需要压缩上屏表达，只能压缩重复铺垫、口语化解释、次要背景和长修饰；事实、数字、来源、限定条件、风险和核心判断不得压缩失真。
- 用户批准版式后，DRAFT/SVG 阶段不得再改写 `final_on_slide`；如果放不下，必须回到 PLAN/用户确认。

模型产物：

- `_internal/01_layout_plan/layout_plan.json`
- `01_layout_direction.html`
- `_internal/01_layout_plan/layout_capacity_report.json`

容量预检：

- 版式审阅前必须生成轻量容量预检，用于判断每页 wireframe 区域是否能承载计划上屏文字。
- 容量预检只做物理估算，不替模型自动排版；它用于提前发现 `overfull`、`tight`、`too_empty` 风险。
- 如果容量预检显示关键区域 `overfull`，模型应在版式审阅前先调整 `copy_handling`、wireframe、拆页或移入 notes，不应等到 SVG 阶段才用小字号硬塞。
- 容量预检可以作为审阅页的辅助信息，但不得替代人工版式方向审批。

推荐命令：

```bash
python scripts/estimate_layout_capacity.py <project_dir>
python scripts/generate_layout_html.py <project_dir>
```

可信审批：

- 必须通过 `review_server.py` 提交版式反馈
- `layout_feedback.json` 必须带有 review server provenance
- approval 必须同时满足 `approval_key_required: true` 和 `approval_key_verified: true`
- 模型不得直接写 approval

### 3. DRAFT

目标：生成当前批次 SVG，并完成脚本校验。

视觉风格边界：

- DRAFT/SVG 阶段才读取 `references/03_style_system.md` 和 `references/04_svg_rules.md`。
- 此阶段不重新选择版式家族，不重新打开 `05_layout_taxonomy.md` 做版式讨论；必须服从已批准的 `layout_plan.json`、`layout_feedback.json` 和当前 batch 范围。
- 模型要做的是在已批准的 wireframe 和内容分布上，细化标题系统、字体层级、色彩语义、组件语言、留白节奏、图片/图表处理和页面精致度。
- 如果视觉实现证明已批准版式无法承载内容，只能通过修订记录说明原因，并回到版式反馈/用户确认；不得在 SVG 阶段静默改版式。

批次纪律：

- DRAFT 阶段只允许处理 `pptflow.py next` 输出的当前 batch。
- 只能生成当前 batch 的 SVG、PNG、validation 和 self-review。
- 不得提前生成后续 batch 的任何产物；这不是加速，而是破坏反馈闭环。
- 后续页面必须吸收当前批次视觉审阅反馈后再生成。

模型产物：

- `_internal/02_svg_source/page_XX.svg`
- `_internal/04_validation/self_review.json`
- `_internal/04_validation/integrated_review.json`
- 如果本轮是在修正视觉反馈，必须写 `_internal/05_review/revision_notes.json`，记录上一轮要求、本轮已改、未改原因和仍需确认项

控制器和脚本产物：

- `_internal/04_validation/validation_summary.json`
- `_internal/03_png_preview/page_XX.png`

正确命令必须带 batch：

```bash
python scripts/pipeline_gate.py <project_dir> batch-svg-ready --batch <current_batch>
python scripts/render_svg_png.py <project_dir>/_internal/02_svg_source --manifest <project_dir>/_internal/00_project/page_manifest.json --batch <current_batch>
python scripts/validate_svg_layout.py <project_dir>/_internal/02_svg_source --manifest <project_dir>/_internal/00_project/page_manifest.json --batch <current_batch> --output <project_dir>/_internal/04_validation/validation_summary.json
python scripts/pipeline_gate.py <project_dir> preview-ready --batch <current_batch>
```

推荐顺序不可调换：先确认当前批次 SVG 存在，再直接渲染 PNG；随后完成静态 validator，并结合 PNG 写 `_internal/04_validation/integrated_review.json`。不要看到单个 warning 就立刻碎修；先综合判断，再决定一次性修哪些 SVG 问题。validator 是模型内部修复依据，不是用户侧审美建议来源。

视觉自检的目的：

- 看实际 PNG，而不是想象中的 SVG，判断页面是否真的可读、成熟、符合已批准版式。
- 综合 validator 的阻断项和非阻断 warning，决定哪些需要模型先修，哪些只是用户可接受的设计取舍。
- 把真正影响观感、理解和业务判断的问题转化为少量设计建议；不要把 warning code 直接推给用户。

多模态能力判断：

- 如果当前模型/运行环境可以读取或查看 PNG 预览，就必须做视觉自检，并在 `self_review.json` 写 `vision_available: true`、`vision_check_method`、每页 `png_reviewed: true`。
- 不得因为“用户之后会看”而跳过模型视觉自检；视觉自检是进入用户审阅前的质量过滤。
- 只有运行环境确实不能检查图片时，才允许写 `vision_available: false`、`human_review_required: true`、`vision_unavailable_reason` 和空的 `pages: {}`；不得输出页面 `pass/revise/blocked` 结论。
- 默认 `preview-ready` 会拒绝 `vision_available: false`。若确实无多模态能力，必须显式运行 `pipeline_gate.py preview-ready --allow-vision-unavailable --batch <current_batch>`，这相当于声明“本模型不能看图”，不能给 Gemini、Claude、GPT 等有图像能力的运行环境使用。

Validator 结果必须进入自检：

- 视觉自检必须读取 `_internal/04_validation/validation_summary.json`，并先写 `_internal/04_validation/integrated_review.json`。
- 如果 validator 有 error 或 blocker-class warning，必须先修复并重新渲染/重新校验，不能进入用户审阅。
- 如果 validator 只剩 non-blocking warning，也必须先在 integrated review 中结合 PNG 判断：能高收益修的先修；视觉上可接受的 warning 才能在 `validator_assessment.action_taken` 中标记为 `accepted_after_png_review`。
- 只要当前 batch 有 validation warning，`self_review.json` 必须写 `validator_revision_pass.attempted: true` 和本轮处理摘要。

进入用户视觉审阅前，模型必须根据 PNG、validator 和可用的视觉自检结果先修到没有阻断性错误。非阻断 warning 不再直接推给用户；模型应综合画面判断，转化为少量真正有意义的设计建议。

阻断规则：

- SVG 缺失，阻断
- validation `status: "fail"`，阻断
- error-level issue，阻断
- blocker-class warning 阻断，例如 `TEXT_OVERFLOW_MAJOR`、`FOOTER_ZONE_INVASION`
- non-blocking warning / info 不阻断；它们只作为模型内部参考，不直接变成用户勾选项
- validation 通过后 PNG 缺失或 self-review 缺失，阻断进入 REVIEW

Validator 修复纪律：

- `validate_svg_layout.py` 是内部诊断器，不是用户审阅清单生成器。它负责帮助模型发现不可交付的结构问题，并辅助视觉自检形成最终设计判断。
- issue 分为四类：error / blocker-class warning 必须在用户审阅前修；non-blocking warning 必须结合 PNG 判断；info 只作为提示。
- 若 issue 带有 `recommended_fix.priority: "fix_before_review"`，下一轮必须优先处理该建议，再做审美性调整。
- 对 `TEXT_OVERFLOW_MAJOR`、`TEXT_OVERLAP`、`TEXT_IMAGE_OVERLAP`、`UNSAFE_MARGIN`，不得只凭感觉微调坐标；必须按诊断中的宽度、重叠、越界信息重排文本/模块。
- 对 `TEXT_CONTAINER_TIGHT`、`TEXT_BASELINE_ESTIMATE_DRIFT`、`LARGE_EMPTY_REGION`、`LOW_MODULE_UTILIZATION`、`TABLE_READABILITY_RISK`、`DENSITY_IMBALANCE_*`，只允许做一轮高收益修复；若 PNG 预览可接受，应进入视觉审阅，不得为了轻微 warning 反复打磨坐标。
- 同一页同类 issue 连续两轮仍未解决时，必须升级处理：记录原因并回到 PLAN/用户确认；不得在 SVG 阶段静默改版式、减少上屏文字、拆页，或继续压低字号和小幅挪动元素。
- 情绪页可以自由构图，但不能突破可读性、越界、重叠和安全边距底线。

### 4. REVIEW

目标：让用户在浏览器中看当前批次 PNG，并提交视觉反馈。

控制器产物：

- `02_visual_review.html`

正确命令必须带 batch：

```bash
python scripts/generate_review_html.py <project_dir> --batch <current_batch>
python scripts/pipeline_gate.py <project_dir> visual-approved --batch <current_batch>
```

可信审批：

- 必须通过 `review_server.py` 提交视觉反馈
- `feedback.json` 必须带有 review server provenance
- `review_server.py` 会把最新视觉反馈写入 `_internal/05_review/feedback.json`，并按批次归档到 `_internal/05_review/batches/<batch_id>.json`
- 用户提交视觉反馈只表示“人工反馈已收到”；必须再运行 `pipeline_gate.py <project_dir> visual-approved --batch <current_batch>`，由 gate 更新 manifest 中的 `visual_approved` / `export_allowed`，才算该批次完成
- approval 必须同时满足 `approval_key_required: true` 和 `approval_key_verified: true`
- 用户勾选的“设计建议”表示下一轮必须优先修正；未勾选的设计建议视为人工接受或暂不处理
- 如果用户勾选了设计建议，不能同时批准该页；应先回到 DRAFT 修正
- 用户未批准则回到 DRAFT 修正
- 不得在 `visual-approved` gate 成功前开始下一批；即使用户已经在浏览器提交“全部通过”，manifest 未更新也不能继续

### 5. EXPORT

目标：全部批次通过真实审阅后导出可编辑 PPT。

控制器检查：

- 每页 SVG 存在
- 每页 PNG 存在
- 每页 layout approved
- 每页 visual approved
- 每页 export allowed
- 每页 validation 已完成，且无 validation fail

通过后运行：

```bash
python scripts/pptflow.py <project_dir> export
```

不得直接运行 `native_svg_to_ppt.py`。导出必须由 `pptflow.py export` 先确认 `export-ready`，再调用转换器。

最终 PPT 必须输出在项目根目录，例如 `<project_dir>/final_deck.pptx`。`_internal/06_ppt_output/` 只保存转换报告和过程资产。

## 默认工作方式

1. 初始化项目骨架。
2. 运行 `pptflow.py status` 和 `pptflow.py next`。
3. 模型只产出当前状态要求的候选文件。
4. 运行对应脚本校验。
5. 到版式审阅或视觉审阅节点时，模型必须先启动 `review_server.py`，再把 server 输出的 URL 和一次性审批口令告诉用户。
6. 用户审批只能通过 review server 页面提交；模型不得操作审批页面，只能读取审批结果并提示用户重新提交。
7. 通过当前 gate 后，再进入下一状态。

启动审阅服务器：

```bash
python scripts/review_server.py <project_dir>
```

`review_server.py` 会在终端打印：

- 版式审阅 URL：`http://127.0.0.1:<port>/`
- 视觉审阅 URL：`http://127.0.0.1:<port>/review`
- 一次性审批口令：`One-time approval key: ...`

模型必须把对应审阅 URL 和一次性审批口令转告用户。用户在浏览器审阅页面输入这个口令并点击提交，才会生成有效 approval。

如果用户明确希望自定义口令，也可以这样启动：

```bash
python scripts/review_server.py <project_dir> --approval-key '<用户指定口令>'
```

模型可以启动 server、转告口令、读取审批结果；不得用口令替用户提交审批，不得保存或复用旧口令。
正式流程不存在 no-key approval；任何 `approval_key_required: false` 都不是有效审批。

## 设计要求

- SVG 固定 `1920x1080`
- 不使用 `<foreignObject>`
- 所有文字必须显式声明 `fill` 和 `font-family`
- 每页 SVG 必须包含 metadata 注释：`page_key`、`data-layout`、`page_mode`、`visual_density`、`reason`
- 页面顺序以 `page_content.json` 为准
- 多页 deck 默认每批 3 页
- 生成用户审阅页前必须完成 PNG 渲染、SVG 静态校验、integrated review、模型视觉自检，并通过 `preview-ready`
- 用户审阅页只处理设计建议、内容取舍和业务判断；技术阻断项必须先修，非阻断 warning 不直接暴露给用户

## 资源

- 内容契约：`references/page_content_contract.md`
- 版式契约：`references/layout_plan_contract.md`
- 页面状态契约：`references/page_manifest_contract.md`
- 风格系统：`references/03_style_system.md`
- SVG 规则：`references/04_svg_rules.md`
- 版式思考参考：`references/05_layout_taxonomy.md`
- 质量清单：`references/06_quality_checklist.md`
- 修订记录契约：`references/revision_notes_contract.md`
- 综合审阅契约：`references/integrated_review_contract.md`

## 脚本

### 核心流程脚本

- `scripts/init_svg_project.py`：初始化项目
- `scripts/pptflow.py`：查看状态、下一步和可信事件
- `scripts/generate_layout_html.py`：生成版式审阅页
- `scripts/estimate_layout_capacity.py`：基于内容和 wireframe 做轻量容量预检
- `scripts/review_server.py`：本地审阅服务器，唯一可信用户反馈入口
- `scripts/render_svg_png.py`：渲染 SVG 为 PNG
- `scripts/validate_svg_layout.py`：校验 SVG，并为溢出、重叠、越界、密度失衡等问题输出 `diagnosis` 和 `recommended_fix`
- `scripts/generate_review_html.py`：生成视觉审阅页
- `scripts/pipeline_gate.py`：阶段门控
- `scripts/native_svg_to_ppt.py`：底层转换器，只能由 `pptflow.py export` 调用

### 可选辅助脚本

仅在当前任务明确需要时使用：

- `scripts/validate_project_contracts.py`：检查 content/layout/manifest 三份契约是否一致
- `scripts/validate_self_review.py`：检查 `_internal/04_validation/self_review.json`
- `scripts/analyze_reference_svg.py`：有参考 SVG 时提取结构线索
- `scripts/template_analyzer.py`：有 PPT 模板时提取主题色和字体
- `scripts/archive_page_version.py`：需要展示修订前后对比时归档页面版本
