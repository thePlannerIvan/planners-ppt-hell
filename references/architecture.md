# 架构：模块、接口、缝

这份文件给**改它的人**读：每个 module 拥有什么、接口是什么、不做什么、动了会牵连谁。
它不是文件清单——这里写的是「我要改 X，该动哪里、会牵连什么」。

## 目的与全景

这个 Skill 稳定完成一件事：**把材料或上游交来的画面契约，做成有证据、可读的画面**。两个出口：

```text
材料 ──┐
       ├─ 边界（init_svg_project）→ 内容底稿 → 做画面 ↔ 渲染看图修订 → 整套审阅 → 出口
契约 ──┘                                    ↑
                                    画幅／判断框架／技术规则
```

| | 幻灯片路线 | 视频画面路线 |
|---|---|---|
| 入口 | `--source <doc>` | `--assets <包>/assets --plan <visual-plan.json>` |
| 状态序列 | CONTENT → CREATE ↔ VISUAL_REVIEW → EXPORT → EXPORT_VERIFY → COMPLETE | CONTENT → CREATE ↔ VISUAL_REVIEW → COMPLETE |
| 视觉身份来自 | 模板库／视觉参考／自主设计 | **风格库**（`video-craft/visual/themes/`）或自主设计 |
| 出口 | `final_deck.pptx` | 全部 `_internal/02_svg_source/<page_key>.svg`（**不导出 PPT**） |
| 完成 | 导出并复核过 PPTX | 全部页面 `check` 无 error，**且作者提交过整套审阅**（审阅是门） |

路线记在项目状态里（`page_manifest.json` 的 `route`），是「该跑哪一半检查、完成标准是什么」的唯一取值处。

## 模块表

一行一个 module：**它是什么／拥有什么（唯一主人）／接口是什么／不做什么**。

| module | 它是什么 | 拥有什么（唯一主人） | 接口 | 不做什么 |
|---|---|---|---|---|
| `scripts/init_svg_project.py` | 边界：把材料或契约立成一个项目 | 项目目录形状（`CANONICAL_DIRS`）、两条入口参数、**契约→底稿的唯一翻译**（`adapt_visual_plan`）、认不出的契约字段当场点名 | `init_svg_project.py <project> --source <doc>` ／ `--assets <包>/assets --plan <visual-plan.json>` | 不判断内容对错；不渲染、不校验画面；不在非空目录上初始化（报错要求恢复） |
| `scripts/orchestrate/ppt_pipeline.py` | 控制面：状态机、编排与恢复 | 各状态之间的转移判据（`next_action`，含 `next` 时的**两份收件**：页面反馈与模板反馈）、check／inspect／resolve／review／export 的编排、两个审阅面的生成与宿主开关 | 子命令 `next` `check` `inspect` `resolve` `review` `export` `export-inspect` `template` `template-review` | 不自己算版本（`project_state`）、不自己算坐标（`validate_svg_layout`／`native_svg_to_ppt`）、不评价设计 |
| `scripts/project_state.py` | 状态与版本 | `_internal/` 下的路径常量、页面版本 digest（`page_version`）、派生判据（`rendered`／`inspected`／`review_current`／`approved`／`review_recorded`）、**契约绑定**（`contract_binding`）、对外具名接口（`__all__`） | 消费方逐个具名导入；命令读写它定义的 JSON | 不写画幅（`canvas_frame`）、不做技术校验、不转换、不渲染 |
| `scripts/canvas_frame.py` | 画幅 | **1920×1080 与它的派生度量**：`FRAME_*`、`SVG_PX_TO_PT`、版式阈值（满版／容器／正文底部／页脚线） | 常量导入 | 不做判断、不渲染；没有第二份数字 |
| `scripts/validate_svg_layout.py` | 检查画面 | 技术规则的清单与**按路线取用**（`skipped_rules_for_route`）、被跳过规则的原因、元素可指名性（`MISSING_ELEMENT_ID`／`DUPLICATE_ELEMENT_ID`） | CLI `--file／--dir --route --page-mode --fidelity-template`，或 `validate_file()` | 不评价密度、字号档位、构件选择、留白、配色；不渲染；不管跨页 id 碰撞（一次只读一页） |
| `scripts/render_svg_png.py` | 渲染与看图 | 用 Chromium 把 SVG 渲成 PNG（`PLAYWRIGHT_SNIPPET`）、整套 contact sheet | 被 `check` 调用；也可单独跑 | 不做任何判断；不比较渲染结果 |
| `scripts/native_svg_to_ppt.py` | 转换 | **SVG 的唯一坐标模型**（`parse_axis_aligned_transform`／`compose_axis_aligned`）与 SVG→PPTX 转换 | CLI；`validate_svg_layout` 从这里取坐标模型 | 不判断页面好坏；不改 SVG；不决定要不要导出 |
| `scripts/review_surface.py` | 审阅面（页面审阅）·**这份 surface 的内容** | `surface_document`（业务：页面在根上、反馈写 `feedback.json`、盯 `snapshot.json`）；建文档 → 交给公共件落盘 + 校验；`open_review` 里那点前置 | 被 `ppt_pipeline review` 调用 | 不解释审阅语义（单位、决定、版本都在页面与 `project_state` 里）；**不实现宿主生命周期** —— 写/校验/起/判活/停都在 `planners-review-core/scripts/lib/review_host.py`（唯一一份，见那边的模块表） |
| `scripts/lib/planners_modules.py` | 边界：按名字找到公共件（与 bypage 的 `planners-modules.mjs` 同一套约定） | 找模块的顺序（`$PLANNERS_MODULES_HOME` → 兄弟目录 → monorepo 分类目录）、`node_binary()`（PATH → 常见位置 → **版本管理器**：宿主进程的 PATH 常常没有 node） | `resolve_module()`／`module_script()`／`node_binary()`；`python3 scripts/lib/planners_modules.py --check` | 找不到就报错并给装法，**不许静默降级成"跳过"** |
| `scripts/generate_review_html.py` ＋ `review_feedback.py` | 审阅面·页面与反馈两端 | 生成审阅页（资产一律给**相对 `dir` 的路径 + 版本**，URL 由页面向桥要）、写 `snapshot.json` 与 surface、**反馈的 Skill 侧**：形状校验、绑定核对（`consume`）、规范化写回、轮次留档（`history/round-NN.json`）、**作者直改（`svg_edits`）的账本与留档**（`applied_svg_edits.json`：逐笔内容 + 人改完那版 SVG 快照） | `generate(root)`；`consume(root)`／`validate_document()`／`save_feedback()`（旧服务器写入口）；`human_edits()`／`human_edit_state()`／`ack_human_edit()` | 不做决定、不代替作者批准；不判断画面好不好（那是看图的人与作者）；**不自动回放**人那一笔（树路径在重画后会指向别的元素） |
| `assets/review/dsh-tokens.css` ＋ `scripts/vendor_dsh_tokens.py` | 审阅面·**UI 令牌的副本与它的闸门** | vendor 自 npm 公开包 `@deepseek-ai/dsh-client-ui-theme`（BSD-3）的令牌表：两层颜色、滚动条、明暗两套，外加从发行版补出来的圆角/浮起/字阶；跑脚本重抄，**手改会漂移** | `python3 scripts/vendor_dsh_tokens.py`（缺 npm 包或缺发行版就报错退出，不写半份） | **不是组件库**：他们的 React 组件在不透明 iframe 里用不了，构件只能照着 token 仿 |
| `scripts/template_feedback.py` | 审阅面·模板侧收件 | 读页面经宿主落盘的 `template_feedback.json` → 校验（决定词表、layout 集合、返修必须留意见、全部通过的三道门）→ **重算派生量**（`approved`／`discarded_layouts`／`revision_layouts`）→ 盖章（这一版审阅页 HTML、源模板渲染页、模板包的摘要）→ 写回 | `consume(root)`；`validate()`／`stale_reason()`／`expected_layouts()` | 不做决定、不代替作者批准；批准算不算"门"由 `template_library.publish` 判 |
| `scripts/template/extract_template_assets.py` | 模板子系统·事实提取：从用户自己的 PPTX（含母版与版式）提出**事实** | 资产、原生形状、字号、重复组等候选事实的清单与出处 | `ppt_pipeline template --mode fidelity` 的提取阶段；产物喂给构建 | **不下结论**：一个形状算不算「可复用构件」留给看图自审与人工审批 |
| `scripts/template/prepare_visual_references.py` | 模板子系统·视觉参考（路线 C）：把参考件**真渲染**出来 | 参考页的逐页 PNG 与 `visual_manifest.json`（`_internal/00_project/template_visuals/`） | `python scripts/template/prepare_visual_references.py <参考件> --project <project>`（PDF／图片／目录） | 不提炼方向（那是模型读完渲染件之后的事）；不支持「只登记模式不渲染」 |
| `scripts/template/build_fidelity_template.py` | 模板子系统·构建：把事实装配成可执行的 registry | `template_registry.json`（组件、layout、锁层 hash）、`layout_canvases/*.svg`、`components.svg` | `ppt_pipeline template --mode fidelity` 的构建阶段；产物被应用与校验读 | 不提取事实（上游给的清单说什么就是什么）；不发布进库 |
| `scripts/template/layout_canvas.py` | 模板子系统·锁层与 canvas | **锁层内容与它的 hash**（`locked_sha256`）、canvas 的生成与「这一代能不能用」（`registry_canvases_ready`、`TEMPLATE_CANVAS_VERSION`） | 被构建、发布、应用与检查画面调用 | 不判断页面内容；没有 `data-template-lock` 层时不返回「空 hash」，直接报错 |
| `scripts/template/apply_fidelity_template.py` | 模板子系统·实例化：把选中的 canvas 变成一页 | 「从 canvas 到一页 SVG」这一步（清空内容层、改写图片 href 为页面相对形式） | `--project --page-key --layout-id --title --body`；做画面在第 5 步调用 | 不改锁层；不填内容（内容由模型写进 `replace` 层） |
| `scripts/template/template_library.py` | 模板子系统·发布与安装：库的闸门 | `list／publish／apply` 三个动作与它们的准入判据：人类批准凭据（`template_feedback.json`＋`review_id`）、整包哈希、内容层的完整性 | `python scripts/template/template_library.py list／apply／publish`；`apply` 由 `ppt_pipeline template` 转发 | **不批准自己**（没有作者提交的批准就不发布）；不服务视频路线 |
| `scripts/template/template_visual_gate.py` | 模板子系统·看图自审闸门 | 判据：「有没有提炼出**足够**的模板规律」——源页与 canvas 的逐页视觉对照是否完成 | 被发布（`publish`）与模板审阅收件（`template_feedback._fidelity_ready`）读到 | 不代替人审；不用页面审阅的判据（两者问的不是一件事） |
| `scripts/template/seal_template_review.py` | 模板子系统·封存证据 | 把看图自审的语义观察与**证据 hash** 绑在一起（模型不写 hash） | `python scripts/template/seal_template_review.py <project>` | 不做判断（只绑定已有观察）；不改观察内容 |
| `scripts/style/theme_tokens.py` | 风格库的唯一读取口 | 读 `video-craft/visual/themes/` 的方式：`:root` 解析、`var()` 展开、**解析不掉的 token 报出来**、目录定位（`--themes-dir`／`PPT_HELL_THEMES_DIR`／默认相对位置） | CLI `list` ／ `show <id>`（JSON） | 不把 token 复制进本 Skill；不改主题文件；不判断风格好不好 |
| `scripts/prepare_source_material.py` | 素材登记 | 源文与图片的登记、命名键去重、`source_assets.json` 的形状 | 被 `init_svg_project` 调用（`prepare_source_material`／`register_image_folder`） | 不判断图片内容；不裁剪、不改图 |
| `references/workflow/00_pipeline_controller.md` | Stage·开局与恢复 | 立项目／恢复项目的命令序列、**开局一次性确认**（视觉来源、画幅、图片）、CONTENT 状态的入口判据 | 被 `SKILL.md`「开始」与 `next` 的 CONTENT 指向；命令在 `init_svg_project.py` 与 `ppt_pipeline.py` | 不写各路线内部怎么做（那是 01／03／04）；除导入异常、源资料缺失、影响结论的歧义外不再追问 |
| `references/workflow/01_template_intake.md` | Stage·幻灯片的视觉来源与模板 | 四条来源路线（自主／模板库／视觉参考／建严格模板）的**判据、命令序列、产物清单**，以及「用」与「建」的分界 | `template_library.py list／apply`、`prepare_visual_references.py`、八步提取各脚本 | 不服务视频路线（那条走风格库）；做画面不经过提取 |
| `references/workflow/02_content_stage.md` | Stage·内容底稿 | `page_content.json` 的写法、**每页读法 `mode` 的语义**、图片取舍与 `unused_assets` 的原因、**三条通道的判据**（已批准逐页稿 / 交给 bypage / 视频契约）与轻量切片降级的边界 | 读 `source/source.md`＋`source_assets.json`；多源或含待核数字时调 `$planners-bypage`；视频路线读适配后的底稿（不重推、不改判） | 不提前冻结坐标与版式；源事实、数字与限定条件不因版面不足被删除；**降级通道不冒充正路** |
| `references/workflow/03_video_route.md` | Stage·视频画面路线（接手 → 逐屏 → 整套） | 这条路线自己的 V1／V2／V3 与完成标准、**四条视频约束**（字幕安全区／人物位置／不透明与透明／强调动画余量）、交给动画层的接口 | 读适配后的底稿与风格库（`theme_tokens.py`）；出口物被 `video-craft` 消费 | 不做内容判断、不重新编号、不套模板库、不给页面加动画 |
| `references/workflow/04_svg_stage.md` | Stage·制作与逐页自检（两条路线共用） | 逐页制作顺序、**看图是必填动作**的判据（含 `inspect` 的字段）、`design_direction.md` 里该写的秩序 | `ppt_pipeline check`／`inspect`；被 03 引用（视频路线的额外三条） | 不评价设计（判断框架在 `references/domain/`）；自检不代替人审 |
| `references/workflow/07_visual_review.md` | Stage·整套审阅与交付 | 审阅的跑法与否决语义、**交付与复核**：幻灯片路线的导出复核与证据强度措辞，视频路线的「审阅是门」 | `ppt_pipeline review`／`export`／`export-inspect`；被 `next` 的 VISUAL_REVIEW／EXPORT／EXPORT_VERIFY 指向 | 不代替作者批准；不把机器绿灯当成内容正确 |
| `references/workflow/08_video_style_extraction_sop.md` | Stage·从参考画板提炼新视频风格与预埋动效模板 | 六步提取与验证流程（一手采集与视频抽帧 → 静态/动态双路子代理拆解 → 四域×Solo/Multi 呼吸阀收敛 → 复合子元素动效契约 → 真项目 `/prototype` 压测 → 双 Skill 落盘）与 6 条实测技术避坑 | 用户提供 Pinterest 画板或视频/排版参考集、要求沉淀新视频风格模板时读 | 不替代幻灯片 PPTX 严格模板提取（那条走 `01_template_intake.md` 的 D 路线） |
| `references/contracts/*` | 机器接口清单 | 「哪个文件、谁写、谁读、最小职责」 | 被代码注释与 Stage 文档引用 | 不是设计思考问卷；不写判断方法 |
| `references/domain/*` | 判断框架与领域规则 | 设计判断（`style_system`／`layout_taxonomy`／`video_style_editorial_archive`）与技术规则的理由（`svg_rules`／`svg_to_ppt_rules`） | 被 Stage 文档指向 | 不写命令、不写字段名 |
| `SKILL.md` | 触发面与分派 | 两条路线的对照、阶段表入口、责任边界 | 模型入口 | 不复述子文档的规则（单一真相源） |
| `assets/template_library/*` | 内置模板**数据**（幻灯片路线） | 内置模板包与它的 manifest 哈希 | 被 `template_library.apply` 读 | 不是代码、不是文档；不服务视频路线 |
| `assets/video_style_references/*` | 视频风格**多模态参考图库**（视频路线） | 各视频风格（如 `editorial-archive`）的四域与 Solo/Multi 代表性原图及 7 屏实测联系表 | 制作视频 SVG 前由多模态模型 `view_file` 读图对齐 | 不进 `video-craft/visual/themes/`（避免破坏 `check_themes.py` 目录扫描） |
| `scripts/test/*` | 判据的可执行形态 | 每条规则的回归 | `python -m unittest discover -s scripts/test` | 不是规格来源（规格在 Stage 文档与 contract） |
| `evals/evals.json` | 评测用例集：十条 prompt 与它们的 `must_do`／`must_not_do`（幻灯片出口五条、视频画面路线五条）——**作者在干净会话里按它测这个 Skill 的行为** | 用例与判据本身（那是作者的测试标准） | 人读、人跑；机器**不执行**它（文件里 `status: not_run_user_will_test_elsewhere`，如实状态） | 不是自动测试（那在 `scripts/test/`）；不代替人审；改它的判据等于替作者重定标准 |

表里两处成组的行，各自成组的理由：

- **`scripts/template/` 八条**：按我的删除测试，每一条删掉都是「复杂度被集中」而不是「搬家」——尤其 `layout_canvas` 是锁层的唯一 owner（锁层 hash、canvas 代数），`template_library` 是发布的唯一闸门（没有作者提交的批准就不发布）。整块**按原样封存、未做清理**：只在用户要真实复用自己品牌资产时启动，做画面这一步永远不经过它，视频画面路线完全不用它。
- **六个 Stage 各一行**：它们各有独立的输入、产物与完成标准；合成一行正好丢掉「以后改的时候知道每个模块干嘛」。

**删除测试量过两次**：审阅那一块的两个面（`review_surface` ＋ `generate_review_html` ＋ `review_feedback` 与 `review_surface.TEMPLATE` ＋ `generate_template_review_html` ＋ `template_feedback`）都**真的换过一次宿主**（自建 HTTP 服务器 → 公共件的 `serve-review.mjs`／`review-host.mjs`，2026-09-26 同一天先后完成），页面与 Skill 侧保留了全部语义。第二次换宿主之后，本 Skill 里**不再有任何 HTTP 服务器**：`review_server.py` 连同它的生命周期用例一起删除（迁移永远在删除之后：先让模板线在新宿主上跑通、真项目验过，才删的）。

**depth 的两处对照**（为什么这两个接口故意小）：`canvas_frame` 只有一个常量面，后面是「画幅只属于做画面」这条判断；`theme_tokens` 只有 `list`／`show` 两个动词，后面是「风格库怎么读」的全部细节。反过来，`references/domain/*` 是浅的：它按主题列判断框架，读的人要自己拼——所以 **Stage 文档必须给指向与顺序**，不能只丢一个文件名。

## 缝与适配器

缝 = 谁交出什么、谁消费什么。有 adapter 的写清它翻什么、谁读它。

1. **上游契约 → 本 Skill 的底稿**（adapter：`adapt_visual_plan`，在 `init_svg_project.py` 里）
   `video-idea-system` 交出 `visual-plan.json` 5.0 ＋ `<包>/assets/`；适配器翻成 `page_content.json`（`screen_id` 原样成为 `page_key`；上屏内容进 `content` 并按来源分组去重；理由与来源进 `notes`；认不出的字段当场点名）。
   **这是两套词汇之间唯一一处翻译。** ppt-hell 的核心（状态、校验、审阅、转换）不认识 `visual-plan.json`——要加字段就改这里与三份 `PLAN_*_KEYS` 清单，别把上游词汇漏进核心。
2. **本 Skill → `video-craft` 的动画缝**（没有 adapter，靠契约）
   交出：全部 `_internal/02_svg_source/<page_key>.svg`，其中可能被强调的元素带**稳定且全片唯一**的 `id`；图片 href 保持页面自己的相对形式；页面里不加动画。画布 `viewBox="0 0 1920 1080"` 与视频像素一致。
   消费：导入器逐字内联页面、**只改写图片 href 前缀**、按 `id` 指名元素（不用 DOM 序号）、动效只加在外层；三个合成事实（`composite`／`personWindow`／`captionSafe`）从 `design_direction.md` 读——**这三个键的字段契约在 `03-design-delivery/video-craft/references/composition-facts-contract.md`**（键名与取值域以那一份为准），本 Skill 这边只负责在 `design_direction.md` 里点名要求它们，不自己造字段。
   为什么是 `id`：重渲时多一个 `<text>`，按序号指的元素就会静默错绑（票 19 实测）。为什么**全片唯一**：各屏会被内联进同一个 DOM，重复的 id 让 `#caption-1` 只命中第一屏（报告 §11.4）。
3. **`script.md` 缝（本 Skill ↔ `video-craft`）**
   稿子与契约同在 `deliverable/` 里。**两边都核** `script_hash`：这里核**来得及**（作者是对着画面录的），剪辑那一步核**只能事后发现**。真的找不到时明说「无法核对」，不报成功。
   **口播不作为输入进来**——本 Skill 不拿口播稿判断画面内容、也不把它抄进 `content`；契约旁边那份 `script.md` **只用于核对哈希**。所以「这一路不做内容判断」与「这一路核 `script_hash`」不矛盾：一个是内容，一个是版本绑定。
4. **`--assets` 缝（上游交付包 vs 作者的素材库）**
   交付包是 `<包>/assets/`，恰好等于契约引用的那几张；作者的素材库不是交付包。`--assets` 指向素材库时报错会点名未被引用的图，并**明令禁止为过闸删源素材**。
5. **审阅缝（人 → 机器）**
   作者在浏览器里逐页给意见；页面经宿主把整份状态写进 `feedback.json`，`consume`（`next` 时）把它绑到当时的 SVG／图片／内容／PNG／HTML／自检记录（`review_id` ＋ 快照）。改过的页面旧批准不再算数（`approvals()` 按版本比）。写盘的人从本 Skill 的服务器换成了宿主 → 校验与留档搬到 Skill 侧的收件口。
6. **环境缝**：渲染与看图依赖 `playwright`／`PIL`／`pptx`／`lxml`——本仓统一用 `02-skills-library/.venv/bin/python`。

## 与相邻 Skill 的关系

| 相邻 Skill | 它交什么 | 本 Skill 交什么 | 什么不归本 Skill 管 |
|---|---|---|---|
| `video-idea-system`（上游） | `visual-plan.json` 5.0（逐屏声明）＋ `<包>/assets/`；上游**已经过**念稿审阅——那不是包里的文件，记录在上游自己的 `_idea/reviews/script/` | 交接后的技术确认（能不能落地、缺什么字段） | 不判断内容对不对、不改写上屏文字、不重新编号 |
| `video-craft`（下游） | —（它是最终成片的消费者） | 全部页面 SVG（带唯一 id）＋ 三个合成事实的来源（`design_direction.md`） | 不做动画、不做剪辑、不管音频与时间轴 |
| `planners-bypage`（上游，幻灯片路线） | 逐页内容稿 ＋ 图片资产 | 技术确认 | 不做叙事与事实审计 |
| 模板提取（本 Skill 内的重组件） | — | 可复用的严格模板包 | 不由做画面这一步触发（做画面永不经过模板提取） |

## 同一件事的两个真相源

分开放是**故意的**；每一条都要说清谁读谁、谁不读谁。

1. **模板库 vs 风格库**：模板库（本 Skill，`scripts/template/`）是从 PPTX 提出的带锁层品牌模板，**只给幻灯片路线**；风格库（`video-craft/visual/themes/`）是配色与字型 token，**只给视频画面路线**。拿其中一个顶另一个会直接坏掉画面（锁层里烤着满幅不透明矩形与压在字幕安全区上的页脚线）。token 的唯一来源是风格库，本 Skill **不复制第二份**，只通过 `theme_tokens.py` 读。
2. **两个审阅面**：页面审阅（单位 `page_key`，`pending`／`approved`／`revise`）与模板审阅（单位 `layout_id`，`pass`／`discard`／`revise`）是两个主体，共用一个进程与传输层，各有自己的页面、决定词汇与快照。**不要合并**。
3. **上游契约 vs 项目内底稿**：`visual-plan.json` 是上游的真相（只读、原样适配）；`page_content.json` 是适配后的运行真相（模型可以补充说明，但不改写上游声明）。
4. **内容与理由**：`content` 是上屏内容本身（分组、去重），`notes` 只放理由与追溯。笔记进 PPTX 的 speaker notes，**绝不进画面**。
5. **模型与脚本的分工**：模型负责内容、构图、裁剪、视觉与取舍；脚本负责资产登记、索引、渲染、技术校验、版本绑定、恢复与转换。设计判断不进脚本阈值。
6. **`CHANGELOG.md` vs `references/maintenance-history.md`**：前者是发布记录（对外），后者是**维护视角**（改它的人读：动了哪些 module、边界怎么变）。同一件事只写一次事实，两边视角不同。

## 动了 X 会牵连什么

| 你要改 | 该动哪里 | 会牵连什么 |
|---|---|---|
| **画幅** | `scripts/canvas_frame.py` 一处 | 渲染尺寸、校验器的出画布与安全区、转换器的 pt 换算、模板 canvas、PNG 与 contact sheet。注意 `page_version` **不含画幅**，改完不会自动让旧页面失效——必须重新 `check` 并重渲 |
| **契约字段** | `scripts/init_svg_project.py` 的 `PLAN_SCREEN_KEYS`／`PLAN_SAMPLE_KEYS`／`PLAN_ASSET_KEYS` 与 `adapt_visual_plan` | 认不出的字段当场点名（不硬失败）；契约文件一变，`contract` 里 `visual_plan_sha256` 变 `warning`；`script_hash` 与稿子不符是 `error` |
| **校验规则** | 只在 `scripts/validate_svg_layout.py` | 必须同时决定它属于哪一半（`skipped_rules_for_route`），否则新规则会在另一条路线上悄悄跑或悄悄不跑；规则编号进入 `check` 的输出，解析它的人要跟着看 |
| **id 命名** | `references/workflow/03_video_route.md`、`04_svg_stage.md`、`SKILL.md`、校验器提示（`STABLE_ID_HINT`） | 已交付页面的 id 改名会让下游合成脚本按旧 id 指名失败——这类改动等于重新交接，要重渲全部页面并通知下游 |
| **`design_direction.md` 的要求** | `ppt_pipeline.require_direction` ＋ `03_video_route.md` | 它进 `page_version`：**写它或改它会让全部页面版本失效**，页面要重做 |
| **终态／路线判定** | `project_state.route` ＋ `ppt_pipeline._next_action` | 每条路线自己定终态；共用一个终态会把某条路线推向下游不要的产物（视频路线曾经必然走向导出 PPTX）。加第三条路线时两处都要给答案 |
| **内置模板包** | `assets/template_library/...` | 库里的 `manifest.json` 哈希与 canvases 必须同步重建（`apply` 的第一道检查就是包哈希）；换 canvas 代数会让旧页面报锁层／版本错——那是「画面要重画」的正确提示 |
| **风格库 token** | 在 `video-craft` 那边，本 Skill 只读 | 页内引用了没定义的 token 会被检查画面点名（`UNDEFINED_CSS_VAR`）；写回退值也拦（它让这一处不再跟着主题走） |

## 退役

旧机制不在运行路径里，留着只会误导。

- Layout JSON scaffold、预布局 HTML、capacity gate、wireframe label、旧 make／finalize task 协议、强制并发策略与 batch 配额。
- 校验器里的设计启发式：`FONT_SIZE_TIERS`、20px 正文字号警告、`HIGH_TEXT_DENSITY`、`HIGH_CANVAS_COVERAGE`、`DENSITY_IMBALANCE_*`、`LARGE_EMPTY_REGION`、`LOW_MODULE_UTILIZATION`、`TABLE_READABILITY_RISK`、`FOOTER_ZONE_INVASION`、`MISSING_IMAGE_SLOT`、`MISSING_CROP_RATIO`、`NONSTANDARD_IMAGE_RATIO`、`CIRCLE_TOO_SMALL`、`TEXT_ANCHOR_MIDDLE_LONG`、`FONT_FAMILY_DRIFT`、`REPEATED_LAYOUT_RHYTHM` 与页面 metadata 概念。
- `SECURITY.md` 的审批口令要求（服务器早已丢弃该字段）；「整页位图不算页面／元素必须是原生文本与图形」这条规则（画面本来就是真的 SVG）。
- **适配器里那个只进不出的「未映射字段（待裁决）」收集器**：全项目没有消费者；认不出的字段改为当场点名。
- **「跨页重复的元素沿用同一族前缀」这条 id 规则**：它制造碰撞（各屏内联进同一个 DOM 后 `#caption-1` 只命中第一屏）；改为「全片唯一，把 `page_key` 放进名字」。
- **在视频路线上跑「转成 PPT 会坏」那一组检查**：视频出口是 PNG，`<style>` 与动画都承载得住；这些规则只跑幻灯片路线，并且**跳过时必须写明原因**（`skipped_rules`），不再静默。
- **用端口探测判断审阅服务死活**：`nc -z` 会在进程已死、socket 仍接受 TCP 时假报 OPEN；判断一律用 HTTP GET ＋ `/health` 身份比对。
- **`examples/minimal_deck/`（历史资产，不在运行路径）**：v2 时代的 smoke fixture——`source.md` 用的是已退役的词汇（`Layout: L01 Cover`／`Density: airy`／`Page mode`），`expected/` 里是当时的产物样例（**与 `source.md` 的内容并不对应**，是一份通用小样）。运行路径上零消费者，只有 `docs/history/` 提到它（当时的名字是 `examples/minimal_deck_work`，且发布包排除）。**保留作历史，不要拿它当 fixture 或范式。**
- **`docs/`（历史归档，不在运行路径）**：`UPGRADE-v5.md` ＋ `docs/history/**`（约 20 个文件）是 v5 升级与更早的设计、审计、验证记录。`docs/README.md` 把它标成「不进入运行上下文」——这里点名，是为了让读者知道**有这么一处归档**可查，而不是去里面找现行规则。
- 旧运行须使用外部归档版本，不在活跃包中保留兼容状态机。

## 相邻 Skill 的架构文档

这份只写本 Skill 内部的 module。接缝的另一端在别处——改缝之前先读对面那一份：

| 相邻 | 它的架构文档 | 与本 Skill 的缝 |
|---|---|---|
| `video-idea-system` | `02-content-assembly/video-idea-system/references/architecture.md` | 它交出 `visual-plan.json` 5.0 ＋ `<包>/assets/`，本 Skill 的 `adapt_visual_plan` 是两套词汇之间唯一一处翻译；它旁边的 `script.md` 由本 Skill 核一次 `script_hash`（来得及的那一次） |
| `planners-ppt-hell` | （本 Skill） | — |
| `video-craft` | `03-design-delivery/video-craft/references/architecture.md` | 本 Skill 交出全部 `<page_key>.svg`（元素 id 全片唯一、图片 href 保持页面自己的相对形式、页面里不加动画）；对面逐字内联、只改 href 前缀、按 id 指名、动效只加外层，并按 `references/composition-facts-contract.md` 读那三个合成事实 |

## 读这份之后应该能回答

```text
□ 一个没参与设计的人，只看 SKILL.md，能不能说出整条流程有哪几步、每步产出什么、什么算做完？
□ 每个 module 的作用、接口和「不做什么」，能不能在 Skill 里读到？
□ 跨 module／跨 Skill 的缝，能不能读到「谁交出什么、谁消费什么」？
□ 一条新 gotcha 该记在哪、一次优化该动哪个 module，能不能读到？
```

答不上来时缺的是 writing，不是功能。gotcha 的候选与升级分在两个地方：`GOTCHAS.md`（Skill 根）与 `references/maintenance-history.md`。
