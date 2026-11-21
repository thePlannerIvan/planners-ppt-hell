# 视觉参考、模板提取与维护

模板包结构契约以 [模板契约](../contracts/template_package.md) 为准。先区分当前属于以下哪一种场景；用户已指明时直接执行：

---

## 场景 1：当次参考快提（`Reference Intake` —— 零网页审批，最快开画）

适用于“拿一份客户旧 PPTX / PDF / 参考截图模仿它的视觉感觉做今天这批页面”，不入库、不走网页选择和审阅审批：

1. **选用既有库模板**（最快）：`python scripts/template/template_library.py list` → `apply <project> --template-id <id>`，实际查看 `SPEC.md` 与样张后直接做页。
2. **自主设计**：直接根据内容形成方向并写进 `design_direction.md`，遵循 [通用视觉构图力学](../domain/style_system.md) 与 [拓扑版式原型](../domain/layout_taxonomy.md) 开画。
3. **从参考文件快速取样**：
   ```bash
   python scripts/template/extract_template_pack.py <source.pptx|source.pdf|img_dir> --project <project>
   ```
   打开生成的 `_internal/00_project/template_visuals/contact_sheet.png`（及单页 `page_001.png`）并读取 `template_pack/extraction_facts.json`（可见色板、字体字阶、母版复用资产），把提取出的颜色、字阶与构图特征写入 `_internal/01_content/design_direction.md`，即可直接进入页面制作，无需生成或审批入库包。

---

## 场景 2：外部 PPTX / PDF 提炼可复用模板入库（`External Pack Extraction`）

适用于专门要把一份参考文档沉淀为后续多项目复用的正式 `Template Pack`：

```bash
python scripts/template/extract_template_pack.py <source.pptx|source.pdf> --project <project>   # 渲染页 + 事实 + layout_catalog.json
python scripts/template/scaffold_template_pack.py --project <project>                             # tokens.css / SPEC.md / shell / layouts.json / previews / anchors
python scripts/orchestrate/ppt_pipeline.py <project> template-select [--surface-only]              # 人勾选要收的结构家族
python scripts/template/apply_layout_selection.py <project>                                       # 收窄 layouts.json 并清理未选中占位
# 模型按 layouts.json 槽位与代表源页制作 primitives/*.svg 并补齐 SPEC.md；再用真实内容试做验证
python scripts/orchestrate/ppt_pipeline.py <project> template-review [--surface-only]              # 逐版式人工审阅
python scripts/template/template_library.py publish <project> --template-id <id> --name '<名称>'
```

- `layout_catalog.json` 记录源 layout 名称、占位符几何与使用页（PDF 按文字/图片块推测结构家族）；`layouts.json` 是发布版式索引，被工作台画廊、最终模板审阅与模型执行共用。
- 纯图片目录没有文字/块结构，走场景 1 当次参考模式；只有在最终 `template-review` 全部通过并填妥模板名称后，才执行 `publish`（同 ID 替换加 `--replace` 保留 `.history`）。

---

## 场景 3：存量库模板直接维护（`Library Pack Refresh`）

当直接修改了 `assets/template_library/<template_id>/` 中的 `primitives/*.svg`、`SPEC.md`、`tokens.css` 或 `layouts.json` 时，运行一条命令同步原语清单并重算 `manifest.json` 哈希，再用 `verify` 验过全库门禁：

```bash
python scripts/template/template_library.py refresh <template_id>
python scripts/template/template_library.py verify
```

---

## 工作台里选择整套模板与逐页版式

应用模板后，工作台顶部的「模板」列出整套候选，「版式」列出当前模板的具名版式（由 `layout_index.py` 只读派生）。用户在工作台选择后点击「提交整套修改」，系统生成带 `template_id`（整套模板）与每页 `layout_id`（参考版式）的 Store 任务：

- 收到任务后，按 [页面制作](04_svg_stage.md) 的指引读取 `layout_id` 对应 `primitive`，以其为起点组织页面，内容冲突时优先保住本页主张与证据，并在 `resolve` 回执里说明偏离。
- 整套换模板不自动重排已有页；只有明确指定了 `layout_id` 的页才按版式重排。模型 `save` 时写入 `layout_id` 才会在左侧轨标示为已应用。
