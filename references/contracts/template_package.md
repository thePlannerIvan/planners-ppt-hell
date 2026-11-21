# 模板定义与包契约

模板是以视觉样张为核心、能迁移到新内容的设计语言，包含可复用页面解法与适用说明。它服务两处：提取时确定产物，制作时提供起点。

## 设计内容

- **视觉样张**：保留可实际查看的原始参考和试做结果；字体尺度、图文关系、疏密和视觉重心通过样张传达。
- **简短定义**：SPEC 说明共同视觉特征、每种样张适合的任务、可变化部分与已验证范围。共享数值引用 tokens，不维护第二套数值表。
- **可用实现**：可复用 SVG、tokens 和必要资产。原语坐标是局部实现，底壳是可选用的页面解法，不自动约束每页。

同一视觉语言可以包含高密度证据页与低密度表达页。覆盖范围由真实试做证明；只验证封面的包就是封面模板。用户要求严格复刻时记录所选样张及保留部分，否则按内容重组。项目画幅与输出要求由项目决定；样张标明自身制作条件，使用时适配而非覆盖项目选择。

## PPT 包存储

沿用 `_internal/00_project/template_pack` 的现有格式，库条目根等于完整包内容：

- `tokens.css`：共享颜色、字体及其他确有复用的数值。
- `skyline_shell.svg` 与 `assets/`：示例底壳及必要资产；文件存在不表示每页必须套壳。
- `primitives/*.svg`：可渲染的代表页面或局部解法。
- `SPEC.md` 与 `anchors/*.png`：适用说明和视觉证据。

工具检查包是否可读取、是否有原语和视觉锚点，不按固定原语数量推断覆盖面。参考用于当次页面时可直接使用图片与项目方向，不要求补齐入库包。提取与迁移试做见 [提取流程](../workflow/01_template_intake.md)。

## 版式索引

模板包分两层：**主题**（tokens、底壳、SPEC）与**版式**（这一页的参考骨架）。版式索引由 `scripts/template/layout_index.py` 读出来，工作台画廊、模板审阅与模型任务共用同一份：

- `layouts.json`（新包）：每个条目是 `layout_id / name / family / use_for / usage / source_layouts / source_pages / slots / preview / primitive / selected`。脚手架生成草案，人用 `template-select` 勾选家族，`apply_layout_selection.py` 收窄；模型按 `primitive` 制作。索引优先读它。
- v2 旧包：每个 `primitives/*.svg` 是一个版式；缩略图依次取 `previews/pages/<stem>.png`、`previews/<stem>.png`、`anchors/<stem>.png`。
- legacy：`fidelity_template/template_registry.json` 的 layouts；缩略图取 `canvas_previews/pages/<layout_id>.png`。

索引只读，不改变包哈希与批准。新包发布前严格校验（tokens 是合法单值、SPEC 无空表格、每个版式有预览与 primitive、primitive 不引用未声明 tokens）；旧包不回溯。整套模板的切换、逐页版式请求与执行见 [页面制作](../workflow/04_svg_stage.md) 与 [工作台](../workflow/07_visual_review.md)。

视频关键帧风格的视觉来源与规范见 [视频静态关键帧路线](../workflow/03_video_route.md)（由 `~/.config/planners/video-vault` 或内置 `default-clean` 基线提供），不再与商业 PPT 模板包共用同一契约或强迫同包格式；动作与合成字段仍引用 `video-craft` 契约。

## 审阅版本与发布

四件套审阅面展示底壳、原语、tokens、SPEC 与锚点；legacy fidelity 保留源页与 canvas 对照、候选审计和原视觉检查。旧包的锁层只用于其明确的严格复刻方式，不推广为自由制作规则。
批准绑定当前 review_id、HTML、template_version 与包文件哈希。改包、预览或源参考后重新审阅；manifest 默认为 candidate，技术校验不赋予批准。
同 ID 替换用 --replace 并保留 .history；发布先复制 staging，核对批准的字节，再切换。当次参考无需入库，publish 消费当前包真实确认。
