# 视觉参考与模板提取

模板含义与包内容以 [模板契约](../contracts/template_package.md) 为准。先明确当前是使用参考，还是生产可复用模板；用户已说明时直接执行。

## 使用已有视觉来源

- 自主设计：根据内容形成方向并试做，不要求先造模板。
- 库模板：`python scripts/template/template_library.py list`，选择后 `apply <project> --template-id <id>`。查看 SPEC 与代表样张，按其已验证用途选用、重组原语。
- 当次参考：实际查看图片/源页，记录要继承的特征，直接进入页面制作。需要提取文件时运行 `python scripts/template/extract_template_pack.py <source> --project <project>`；它只整理来源与候选材料，不等于已经生成有效模板。

共同方向只记录本项目的视觉来源、复用方式与调整。需要严格复刻时明确对应样张；页面和素材不是逐项强制清单。

## 工作台里选择整套模板与逐页版式

应用模板后，工作台的「模板」列出整套候选，「版式」列出当前模板的具名版式（从 `primitives/` 或 legacy `layouts` 读出的索引）。选中先停在页面上，点「提交整套修改」才合成任务：任务带 `template_id`（整套模板）与每页 `layout_id`（参考版式）。DSH 当场唤醒模型；本地宿主只把任务落盘，回对话让模型读。

版式只作参考：模型以它为起点组织这一页，内容放不下时保留主张与证据，并在回执里说明偏离。整套换模板不重排已有页；只有明确给了 `layout_id` 的页才改。

索引读法见 [模板契约的版式索引](../contracts/template_package.md#版式索引)。它只读包，不改哈希，也不另存第二份清单。

## 提取生产（PPTX / PDF）

源是 `.pptx` 时先用原生 master/layout；PDF 没有母版，按文字/图片块推测结构家族。两者都产出同一份 `layout_catalog.json`，不再只靠看渲染页：

```bash
python scripts/template/extract_template_pack.py <source.pptx> --project <project>   # 渲染页 + 事实 + layout_catalog.json
python scripts/template/scaffold_template_pack.py --project <project>                # tokens / SPEC / shell / layouts.json / previews / anchors
python scripts/orchestrate/ppt_pipeline.py <project> template-select --surface-only  # 人勾选要收的结构家族
python scripts/template/apply_layout_selection.py <project>                          # 收窄 layouts.json
# 模型按 layouts.json 的槽位与代表源页做 primitives；再 template-review 逐版式批准
```

`layout_catalog.json` 记录每个源 layout 的名称、占位符几何与使用页（PDF 是代表页的文字/图片块）；`layouts.json` 是**发布版式索引**，同时被工作台的版式画廊、最终模板审阅和模型执行消费。脚手架只写有据可依的值（色彩、字号、安全边距、版式目录），设计哲学与 primitive 仍由模型补。旧包没有 `layouts.json` 时继续从 primitives 派生，不走这条新链。纯图片目录仍走“当次参考”模式：没有文字/块结构可提取，不硬造版式目录。

## 提炼可复用模板

1. **观察与选样**：实际查看来源，选出能表达视觉身份和不同页面任务的代表图。分清反复出现的共同特征与单张图的偶然内容；参考不足时缩小模板覆盖范围。
2. **形成简短定义**：在候选 SPEC 中说明视觉身份、样张用途和可变化部分。保留原图作为主要视觉依据，只把确有复用价值的数值提入 tokens。
3. **迁移试做**：先还原代表效果，再换真实内容试做，检验标题长度、图文体量和证据关系变化后的表现。计划覆盖完整方案时试做不同密度与任务；局部模板只验证其声明用途，不凑固定页数。
4. **目标出口验证**：查看实际 PNG。PPT 样张还要试转 PPT 并查看真实 PPT 渲染，记录可编辑范围和失真；图表形状可编辑不等于原生数据图表可编辑。视频走 [视频提取](08_video_style_extraction_sop.md) 的结构与下游验证。有技术限制时调整实现或明确能力缺口，不把失败样张标成可用。
5. **收敛候选包**：根据试做删掉无效规则和原语，保留视觉锚点、实现、适用说明与验证结果。模型推断的视觉特征与用户明确要求分开表述。
6. **审阅与入库**：按下方现有接口展示当前包，消费用户对该版本的决定。

## 人工审阅与发布

```bash
python scripts/orchestrate/ppt_pipeline.py <project> template-review
python scripts/template/template_library.py publish <project> --template-id <id> --name '<名称>'
```

四件套和 legacy 各按其格式审阅。作者逐底壳/原语（legacy 是 layout）决定通过、舍弃或返修，确认模板名称。发布版本与替换规则见模板契约。普通页面反馈与模板入库确认分开。
