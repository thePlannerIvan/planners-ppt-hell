---
name: planners-ppt-hell
description: 制作与持续修改 SVG 页面工作台，从逐页内容稿、直接材料或 video-idea-system 的 visual-plan.json 出发，输出原生可编辑 PPTX 或视频静态关键帧 SVG，并支持从既有 PPTX/PDF 提炼模板包入库。
---

# Planner's PPT Hell

> 来源：阿祖不看 TVC · [demyth.info](https://demyth.info) · `Lawyif@163.com`。署名保留在 Skill 与审阅工作台，不写入客户最终 PPTX、导出 SVG 或 PNG。

本 Skill 以持续可编辑的 **SVG 工作台 (`WORKBENCH`)** 为核心：用户直改与模型候选共用版本存储（`workbench_store.py`），可编辑 PPTX 与视频快照是按需冻结的可重复输出。

## 同一主线下的任务切入（`Non-linear Playbook`）

所有任务共享**「1. 接收 → 2. 定方向 → 3. 工作台制作与审阅 → 4. 输出」**同一条主线，按当前任务与已有半成品从对应环节切入：

| 当前任务 | 走哪几个阶段 | 按需加载的模块 (Disclosed References) |
|---|---|---|
| **从零 / 从 Bypage 做可编辑 PPT** | `1 → 2 → 3 → 4` | [02_content_stage.md](references/workflow/02_content_stage.md) → [01_template_intake.md](references/workflow/01_template_intake.md) → [04_svg_stage.md](references/workflow/04_svg_stage.md) + [svg_to_ppt_rules.md](references/domain/svg_to_ppt_rules.md) |
| **做视频静态关键帧 SVG** | `1 → 2 → 3 → 4(直交 SVG)` | [03_video_route.md](references/workflow/03_video_route.md) → [04_svg_stage.md](references/workflow/04_svg_stage.md) + [svg_rules.md](references/domain/svg_rules.md) |
| **处理工作台返修 / 换模板与版式** | 直接进 `3`（`next` 读任务） | [04_svg_stage.md](references/workflow/04_svg_stage.md) + [07_visual_review.md](references/workflow/07_visual_review.md) |
| **网页点选快照后导出 PPTX** | 直接进 `4`（`export --snapshot`） | [project_contract.md](references/contracts/project_contract.md) |
| **从 PPTX / PDF 提炼新模板入库** | 独立走 `2` 的模板提取链 | [01_template_intake.md](references/workflow/01_template_intake.md) + [template_package.md](references/contracts/template_package.md)（视频风格见 [08_video_style_extraction_sop.md](references/workflow/08_video_style_extraction_sop.md)） |

## 核心深模块 CLI（`Deep-module Tools`）

在 Skill 根目录运行，路径用绝对路径，具体参数以 `--help` 为准：

| 工具 CLI | 职责与调用时机 (Seam) |
|---|---|
| `python3 scripts/init_svg_project.py` | 初始化项目画布与目录（`--source <稿件> --route slides\|video [--width W --height H]`，或 `--assets <dir> --plan <visual-plan.json>`）。已有项目直接恢复原目录。 |
| `python3 scripts/orchestrate/ppt_pipeline.py <project> <cmd>` | 全流程编排器：`next --json`（查当前状态与待办任务）、`frames`（测图片槽位）、`check --summary`（渲染 PNG 并跑布局校验）、`inspect`（登记实际看图结论）、`review [--surface-only]`（打开审阅工作台）、`export [--snapshot <path>]`（冻结快照并转 PPTX）、`export-inspect`（绑定 PPTX 实图复核）、`template-select` / `template-review`。 |
| `python3 scripts/workbench_store.py --root <project> --command-json` | 页面版本与任务唯一写入口（JSON stdin）：`state`、`get`、`checkout`、`save`（保护用户直改文字与位置 `guards`，支持记录 `layout_id`）、`add_page`、`delete_page`、`order`、`task`、`resolve`。 |
| `python3 scripts/template/template_library.py` | 模板库管理：`list`、`apply <project> --template-id <id>`、`publish`、`verify`（校验包完整性与 `manifest.json` 哈希）。配合 `extract_template_pack.py`、`scaffold_template_pack.py`、`apply_layout_selection.py`、`layout_index.py` 完成模板提取与版式索引。 |
| `python3 scripts/resolve_video_vault.py --style <style_id>` | 解析视频风格包（优先挂载 `~/.config/planners/video-vault/styles/<style_id>/`，无私有库自动降级为 `default-clean`）。 |

---

## 1. 接收（`Intake & Resume`）

- **恢复或新建**：已有项目直接跑 `ppt_pipeline.py <project> next --json` 恢复状态；新项目按输入源运行 `init_svg_project.py`（详情与 Bypage 衔接见 [02_content_stage.md](references/workflow/02_content_stage.md)）：
  - **Bypage 逐页稿**：现行 `planners-doc/2` 交付（`.planners/by-page.md` + `by-page.assets.json` + `fact-audit.json`）用 `--source <Project>/.planners/by-page.md --route slides` 初始化，将正文、制作说明与登记图片整理进 `_internal/01_content/page_content.json`，并沿用同一 `project-memory.md`、权威 `source-index.json` 与 `fact-audit.json`；旧版 `bypage-production/1` JSON 包使用 `python3 scripts/import_bypage.py <project> --production <bypage-production.json>` 导入。
  - **直接材料**：按复杂度直接整理进 `page_content.json`，或多源研究时先委派 `planners-bypage`。
  - **视频关键帧**：有 `visual-plan.json` 用 `--assets` + `--plan` 初始化并保持 `screen_id` 不变；仅有已定稿上屏稿用 `--source <上屏稿.md> --route video`（未形成上屏稿的新片退回 `video-idea-system`）。详见 [03_video_route.md](references/workflow/03_video_route.md)。
- **Completion Criterion**：来源与画幅可读，每页拥有稳定 `page_key` 与 `page_content.json` 记录，全部源图片已登记且零静默遗漏。

## 2. 定方向（`Direction & Template`）

- **确认秩序**：一次确认画幅与视觉来源（用户已指明则直接执行），将本次实际选择写入 `_internal/01_content/design_direction.md`。
- **选用或提取模板**：
  - 模板由**主题**（`tokens.css`、底壳、`SPEC.md`）与**具名版式**（`layouts.json` / `primitives/*.svg`）两层组成，契约见 [template_package.md](references/contracts/template_package.md)。
  - **幻灯片**：选用内置模板包（`template_library.py apply`）、当次参考图，或从 PPTX/PDF 提炼新模板包入库，按 [01_template_intake.md](references/workflow/01_template_intake.md) 执行；只有「新模板入库」分支需要 `template-review` 人工批准门。
  - **视频**：运行 `resolve_video_vault.py --style <style_id>` 读取对应 `page.md` 与 `anchors/` 参考图（见 [03_video_route.md](references/workflow/03_video_route.md)）。
  - 开画前必须实际查看所选模板/风格的 `SPEC.md` 与样张图片，结合 [style_system.md](references/domain/style_system.md) 与 [layout_taxonomy.md](references/domain/layout_taxonomy.md) 规划版面。
- **Completion Criterion**：`design_direction.md` 已落盘，所选模板/风格文档及样张已实际查看。

## 3. 工作台制作与审阅（`Workbench & Review Loop`）

按 [04_svg_stage.md](references/workflow/04_svg_stage.md) 与 [svg_rules.md](references/domain/svg_rules.md)（PPT 另读 [svg_to_ppt_rules.md](references/domain/svg_to_ppt_rules.md)）逐页制作与返修：

1. **Checkout → 编辑候选 → Save**：通过 `workbench_store.py` 执行 `checkout` 获取候选路径、基版与 `protected` 守卫（用户改过的文字与坐标几何均受保护，生成器重建整页时必须按 `human_edits_lost` 返回的 `guards` 原位保留），编辑候选 SVG 后 `save`（附 `author="model"`、`base_revision`，参考了版式时附 `layout_id`）。
2. **版式与反馈任务**：工作台里用户提交的框选意见、整套模板（`template_id`）与逐页参考版式（`layout_id`）均作为 pending task 存入 store。先读任务，按参考版式组织该页（版式是参考骨架而非死锁层，内容冲突时优先保住本页主张与证据，并在回执说明偏离），保存后调用 `resolve` 绑定结果 revision。
3. **Check → 实图目检 → Inspect**：运行 `ppt_pipeline.py <project> check --pages ... --summary` 检查技术防线（切字、重叠、越界、未定义 CSS 变量、Emoji、文案对表），**逐页打开渲染出的 PNG 大图实际目检**，再运行 `inspect --render-token <token>` 记录第一眼焦点与视觉发现。
4. **打开审阅工作台（`Human-in-the-loop`）**：按 [07_visual_review.md](references/workflow/07_visual_review.md) 打开工作台——DSH 环境跑 `ppt_pipeline.py <project> review --surface-only` 后交 `review_open` 挂入侧栏；非 DSH 跑 `ppt_pipeline.py <project> review` 启动 `planners-review-core` 本地宿主。

- **Completion Criterion**：本轮所有变更均取得 store 保存回执（非 `no_change`），`check` 零硬错误，已逐页查看最新 PNG 并完成 `inspect` 登记，待办 `task_id` 已 `resolve`，工作台已打开或刷新供用户审阅。

## 4. 输出（`Export & Delivery`）

- **可编辑 PPTX 出口（`slides`）**：
  - 网页点击导出唤醒（携带 `snapshot.path`）或命令行导出时，运行 `ppt_pipeline.py <project> export [--snapshot <snapshot.json绝对路径>]`。产物写入 `_internal/06_ppt_output/<snapshot_id>/`（根目录 `final_deck.pptx` 为最新兼容副本）。
  - 使用可用渲染工具导出逐页预览 PNG，实际查看文字折行、层级与裁切后，运行 `export-inspect --snapshot <同一snapshot.json> --previews <PNG...> --note "<工具与发现>"`。缺少渲染工具时如实报告未复核并保留 `EXPORT_VERIFY`。详见 [project_contract.md](references/contracts/project_contract.md)。
- **视频静态关键帧出口（`video`）**：
  - 默认直接按 store `order` 交付 `get_page` 返回的当前已保存 SVG、关联素材与 `notes` 给 `video-craft`，**无需运行 `export`、也不生成 PPTX**。仅当下游需要冻结整套版本时才运行 `export` 生成 `snapshot.json`（详见 [03_video_route.md](references/workflow/03_video_route.md)）。
- **Completion Criterion**：交付文件与版本快照路径可定位，技术检查与实图复核结论（或限制）已如实报告；输出后工作台仍保持可继续编辑状态。

---

## 协同能力与工程维护

- **同行 Skill 协同**：修改页面文案表达调 `slide-copy`；补充论证视角调 `planners-method-wiki`；页面改写改变了数字、主体、时间、单位或限定条件时，在交付前按 [02_content_stage.md](references/workflow/02_content_stage.md) 调用 `planners-fact-check` 复核受影响页。
- **架构与升级**：模块唯一主人、接口契约与测试门禁见 [references/architecture.md](references/architecture.md)。升级或维护本 Skill 时遵循 `planning-before-create-skill`，候选问题记入 [GOTCHAS.md](GOTCHAS.md)，正式变更记入 [references/maintenance-history.md](references/maintenance-history.md)。
