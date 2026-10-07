# 维护历史：升级记在这里

**这里装升级**：一次改动做了什么、为什么、影响了哪些 module、删了什么。给**改它的人**读——发布视角（对外逐项对账）看 `CHANGELOG.md`；同一件事两边都出现时，这里只留**维护要用的那几面**（边界怎么变、动了哪些 module、删了什么）。候选（还没升级的）在 `GOTCHAS.md`。

看每一条时问三件事：**边界怎么变了**、**哪些 module 被牵动**、**删掉了什么**。

---

## 2026-10-07 · 版本只属于这一页：单页改动不再牵连整套的重看与交代

**触发**：一次真项目改稿（先挪页、再把后半段六页压成四页、最后写回作者在审阅页上手改的五处标题）之后复盘：整场会话 **71 次看图**里大部分不是审稿，而是**被迫重看没变过的图**；`ack-human-edit` 被反复重跑 9 次。

**先查事实，再改**。三处根因都拿到了可复现的证据：

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `project_state.page_version`：digest 里去掉 `'source': sha(source.md)` | `source.md` 是**全部页 content+notes 的拼接**，把它算进单页版本等于把每一页绑在整份文档上——改一页的字，全部页的批准／看图记录／直改交代一起作废 | `scripts/project_state.py`、`scripts/generate_review_html.py`（快照新增 `source_sha256`）、`scripts/test/test_v5.py` | 单页版本对整份材料的绑定（材料级绑定改由 `review_current` 承担，原意保留） |
| 新增 `project_state.source_digest()` ＋ `review_current()` 里比 `source_sha256` | 材料副本变了，**整套审阅**该失效（这是原设计的意思）；但那不是单页版本的事 | `scripts/project_state.py`、`scripts/generate_review_html.py` | —（把一件事挪到它该在的层） |
| 新增 `project_state.carry_inspection()`，`check` 渲染后按新旧 `png_sha256` 决定承接 | 版本换了但**图一个字节没变**（例如只改 `notes`）时，要求重看是没有信息量的动作；字节相同即"上一次看的就是这一版" | `scripts/project_state.py`、`scripts/orchestrate/ppt_pipeline.py`、`scripts/test/test_v5.py` | 那句无条件的"重看" |
| `review_feedback`：`root/REVIEW/VERSIONS/…` → `root/VERSIONS/…` | `VERSIONS` 已含 `REVIEW`，多拼一层使账本记的 `svg_snapshot` 指向一个不存在的路径（文件也真落在嵌套目录里） | `scripts/review_feedback.py`、`scripts/test/test_human_edit_guard.py`（断言升级为"与 PNG 快照同住 versions/"） | 双层前缀；以及那条**只断言"记录的路径能打开"**的弱断言 |
| 新增 `scripts/lib/office.py`（`soffice_argv` / `run_soffice`），三处调用点共用 | 沙箱里默认用户 profile 会让 `soffice` **启动即抛** `DeploymentException`；三个调用点里只有一个显式给了临时 profile，本 Skill 自己的 `.doc` 转换用例因此长期红着 | `scripts/lib/office.py`（新）、`scripts/prepare_source_material.py`、`scripts/template/extract_template_pack.py`、`scripts/test/test_source_assets.py`；同族改动也在 `04-office-docs/{docx,pptx,xlsx}/scripts/office/soffice.py` | 三处各写一份的 soffice 调用（其中一处自拼 profile） |

**回归**：`python -m unittest discover -s scripts/test` → 215 条全绿（改动前 1 条红，即 `.doc` 转换用例）。新增断言四条：材料重写不动单页版本、单页编辑只动这一页、同一张图承接看图记录、图换了不承接。

**没做的事**（作者点过、留待讨论）：唤醒与落文件的事务化、`reviewed` 在"旧页决策随新版本带回"下的判定。两条都记在 `GOTCHAS.md`（G-32／G-33）。

## 2026-10-06 · 唤醒从「排队」改成「插话」：一句话不再同时出现在两处

**触发**：作者再提一次：「点本页需要修改，模型会收到一次消息，同时消息排队中还会有这个消息……如果直接传给模型的消息能够收到，就不要再有消息排队了。」

**先查事实，再改**。会话日志（3 个会话、95 次提交）实测：**每次提交只有一条 `user/message`，零重复投递**。看到的是**同一条消息的两段式交接**——`agent/inbox/spliced(target=next-turn)` → `agent/inbox/spliced(target=next-step)` → `user/message`，同一个 `requestId`。所以"模型重复工作"这个担心不成立，但两个真问题成立：① `queue` 把提交压到当前回合结束之后（dock 实测队列里躺过 64 秒）；② 页面用一句笼统的"已通知模型/已进入队列"，让人没法判断到底送到没有。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `review_surface.py` 的 `wake.mode`：`queue` → **`steer`** | `queue` = `agent.followup` → `next-turn`（持久队列，回合结束才取）；`steer` = `agent.steer` → `next-step`（下一个步骤边界就取）。"现在就按这个改"才是提交的语义 | `scripts/review_surface.py`、`scripts/test/test_review_surface.py` | `queue` 这个默认（它带来的等待与"两处显示"） |
| `assets/review/review.html` 的 `wakeNote()` 按 `verified.state` 分三档 | 「排进待处理」与「已经进了当前回合」不是一回事，笼统说"已通知"是替宿主许诺 | `assets/review/review.html`、`test_review_browser.py`（三档各一条断言） | 那句把两档混在一起的「核对进入队列」 |
| 契约与文档：`planners-review-core` 的 `wake.mode` 描述、`07_visual_review.md` 的唤醒一节 | mode 是 **surface 的声明**，要写清两种投递各是什么、审阅面为什么选 steer | `00-system/planners-review-core/contracts/review-surface.schema.json`、`references/workflow/07_visual_review.md` | —— |
| 同一处声明的另外三个 Skill：`video-craft`（两个 helper）、`planners-bypage` | 一条规则一处生效不够——所有审阅面走同一个宿主，声明不一致就会"这里不排队、那里排队" | `video-craft/helpers/{review_surface,edl_review_surface}.py`、`video-craft/tests/test_visual_review_feedback.py`、`planners-bypage/scripts/review-surface.mjs` | 那三处的 `queue` |

**没动的**：dock 侧（`dsh-review-dock`）一行没改 —— `mode` 本来就读 surface 声明；`verified.state` 也早就在返回里。

**补一次"存量"（同日晚些时候，人第二次报"还是有排队消息"）**：`wake.mode` 是**生成时写进项目**的产物，所以改完 Skill 只对**新生成**的页面生效 —— 人正在审的那个项目（页 key `p01…`，不是我刚重出的那个）surface 里还写着 `queue`，点了照旧进队列。**这次的交付因此包含两件别的东西**：① 把工作区里 **17 份真实项目的 `review-surface.json`** 一起改成 `steer`（scratch/归档/旧格式不动，逐份备份到 `/tmp/surface-backup`）；② 记下"在审的项目不要为此重出页面"——宿主每次都重读 surface 文件（`loadSurface` 无缓存），改那一行就生效，而重出页面会换 `review_id`、让人白刷新一次。教训写进 `GOTCHAS` G-27：**判断"我改的是不是人在看的那个"，用唤醒语里的 unit 核（`p02` ≠ `page_02`）。**

---

## 2026-10-06 · 审阅页右栏：图片卡重做 + 两处"不报错的坏"

**触发**：作者在真实项目上截图指出两件事——「图片会把上面的文字反馈框挤掉」「图片下面那几个反馈显得没什么意义，改的应该是裁剪比例、显示方式、对齐方式」。

**第一个是真缺陷，不是观感**：右栏是 flex 列 + `overflow:auto`，子项默认 `flex-shrink:1`，所以内容一超高，**78px 的反馈框被压成 18px**（实测），整栏还给出一条滚动条。第二个是控件没做完：两个下拉 + 一个自由文本（`original 或 16:9`）排成一列，`original` 是什么意思、`靠上` 和 `填满` 什么关系都得猜。

**顺带挖出第二处**：改完模板跑 `review`，项目里的页面**没有重出**（`make_review` 的"已是最新"只比页面自己的 sha，而页面与快照是一起写的）。等于"Skill 升级了，用户看到的还是旧页面"，而且命令一路绿灯。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `assets/review/review.html` 右栏：`.panel>*{flex:0 0 auto}` ＋ textarea `min-height`；图片卡改成 预览（按比例成形的取景框）＋ 显示方式（分段控件）＋ 裁剪比例（预设 + 自定义）＋ 位置（九宫格）；原生 `Choose File` 换成"替换图片" | 整栏滚而不是把定高子项压扁；三个设定各用与它形状相称的控件，预览当场显示"提交后会裁成什么样" | `assets/review/review.html`（CSS ＋ `drawAssets`） | `.crop` 样式与自由文本比例输入、`asset select` 那几条"表单式"规则 |
| `review_feedback.consume` 的 `anchor` 判据由五个值扩到九个 (`*-left`/`*-right` 四角) | 控件是九宫格，只收五个值会让四个角**点得到、提交却被退** | `scripts/review_feedback.py`（一处校验） | 旧五值集合（`center`/`top`/`bottom`/`left`/`right` 仍是其中五个，老反馈不必迁移） |
| `generate_review_html.template_fingerprint()`（模板 sha ＋ 令牌表 sha）写进快照 `template_sha256`；`make_review` 短路时两个条件都要成立 | "这一版是最新的"必须同时表达"没人手改过"**和**"是按当前模板生成的" | `generate_review_html.py`、`orchestrate/ppt_pipeline.py` | 只看 `review_current` 的短路条件 |
| 新增三条回归（`test_v5`：九宫格九值可提交／九宫格外仍被挡／模板换了就重出）＋ 浏览器冒烟两条（右栏真溢出时反馈框 ≥78px、点出来的显示方式与对齐要进反馈） | 这三处都是"静默坏"，没有断言就会第二次坏掉 | `scripts/test/test_v5.py`、`scripts/test/test_review_browser.py` | —— |

**没动的**：`review_current`／`approvals` 的语义。审阅页换皮不该让已有的 31 页批准作废——那是页面的观感，不是被审的画面。

**自己看图又看出第三个**（`GOTCHAS` G-25）：`hidden` 属性被 `.field{display:flex}` 盖掉，于是"选了原始比例"时下面还挂着自定义输入框和一行红字——JS 里 `hidden=true` 明明执行了。修法：表头 `[hidden]{display:none!important}`；顺带把"空框不算错误、不合规的输入失焦时退回上一个成立的值"补上，并加进浏览器冒烟。**这三条（G-23／G-24／G-25）有同一个形状：不报错、只有看一眼页面才发现** —— 所以每条都配了一条会红对照的断言，而不是只写在文档里。

---

## 2026-10-06 · 幻灯片路线补上非 PPT 资料的 Bypage 适配入口

**边界变化**：幻灯片路线收到非 PPT 资料包，或材料需要完整内容理解时，先调用 `planners-bypage`；Bypage 独立完成资料理解、结构形成和完整逐页内容，再把 `deliverable/by-page.md` 与 `deliverable/assets/`交回本路线。轻量切片只保留为简单单源材料的降级通道。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `SKILL.md`、`references/workflow/00_pipeline_controller.md`、`02_content_stage.md`、`references/architecture.md` | 初始化前先判断内容入口，避免 PDF、表格或资料目录卡在导入器；已有目标和确认随资料交接 | 内容底稿、架构与路线入口 | 用轻量切片替代尚未完成的内容展开 |

---

## 2026-10-05 · 令牌副本"钉版本"纠错：从 npm 的 latest 改成你装的那一版

**触发**：作者问"你调用的 UI 组件是这个时间段以后的最新版吗"。

**结论：不是。** `npm view <包> version` 跟 `latest` 标签，而 `@deepseek-ai/dsh-client-ui-theme` 的
`latest` 卡在 `0.0.1-rc.1`（8-10，31 个版本里最老）。照它抄 = 抄到比运行版本老七周的副本，
**且全链路无报错**。同时纠正一个误判：库没有静止，10-03 还有 `0.2.1-alpha.1`；停的是桌面端构建。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `vendor_dsh_tokens.py` 改为**只读本机发行版**：`Info.plist` 取版本 → `app.asar` 里读 `lib/welcome/welcome.css` | 版本必须钉在"正在跑的那一版"；npm 上 0.2.0 起已经没有这份表了（只剩品牌字体） | `scripts/vendor_dsh_tokens.py` | 对 npm / `latest` 的依赖（连同"取错版本"的可能） |
| 抽出 **明 383 / 暗 193** 条，补 radius 6 / 运动 4 / 字体栈底座 2 | 底座缺失会让 `font: var(...)` 静默退回浏览器默认 | `assets/review/dsh-tokens.css`（重新生成） | 旧表（8-10 那份 223 条） |
| 写盘前两道自检：括号/引号配对、表内自洽 | 这两类错误都**不报错**，只是"看起来没上样式" | 同上 | 值长度上限（截断会切出未闭合括号，整段 CSS 失效） |

**边界**：表是副本，DSH 升级后要重跑脚本。许可随副本保留（App 内该包的 MIT，Copyright (c) 2026 DeepSeek）。
另外四个审阅面仍未动。

---

## 2026-10-05 · 审阅页 UI 采用 DSH 的设计令牌（vendor 一份副本 + 一道更新闸门）

**起因**：作者希望审阅页的观感和 DSH 应用一致。评估后按最小范围：**只改 ppt-hell 的审阅页**。

**硬约束（决定了"换"只能换一半）**：审阅页在 `sandbox="allow-scripts"` 的**不透明源 iframe** 里 —— 宿主的 CSS 变量继承不进来，外链样式表会被信任围栏打回 403，他们的 React 组件包（依赖宿主运行时）也搬不进来。**所以只能把 token 表带进页面，构件只能照着仿。**

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `assets/review/dsh-tokens.css`：vendor `@deepseek-ai/dsh-client-ui-theme@0.0.1-rc.1` 的 base/design-platform/scrollbar 三份表 + 补丁块 + BSD-3 全文 | 令牌只能随页面发；两处副本必须有一道闸门，不能手改 | `assets/review/dsh-tokens.css`（新）、`assets/review/dsh-tokens.LICENSE.txt`（新） | — |
| `scripts/vendor_dsh_tokens.py`：从 npm 包（或 `--from` 的离线目录）+ 本机发行版重新 vendor，把三个源文件的 sha256 与补丁条数写进文件头 | "更新方式只有一条命令"，凭证可核对 | `scripts/vendor_dsh_tokens.py`（新） | 手工维护那份 CSS 的可能 |
| `generate_review_html.py` 在 `<style>` 顶部注入 `__DSH_TOKENS__` | 令牌表必须**内联**（外链在 iframe 里 403） | `scripts/generate_review_html.py`、`assets/review/review.html` | — |
| 页面 95 条规则改用 `--dsw-*` 语义 token（颜色 59 → **0** 硬编码）；字层改用 `font: var(--dsw-font-*)`；控件收到他们的 28px 档 | 见 CHANGELOG 的逐项对照（字重 500、固定行高、antialiased、选中色、过渡曲线、4/8 节奏） | `assets/review/review.html` | `.rail,.panel{scrollbar-width:thin}`（它会让他们整张 `::-webkit-scrollbar*` 表失效） |

**边界**：只换了 token 层（颜色/字/圆角/浮起/滚动条/密度）。**构件形态是仿的**，不是引他们的组件 —— 他们改版时这层要重看。另外四个审阅面未动。页面里凡"内容"（缩略图卡、幻灯片本体）不套 UI token。

**怎么升级**：DSH 改版 → `python3 scripts/vendor_dsh_tokens.py` → 重出审阅页 → 看一眼明暗两档。脚本在缺 npm 包或缺发行版时**直接报错退出，不写半份文件**。

---

## 2026-10-05 · 草稿自动落盘：把「我改了东西」和「告诉模型可以动手」拆开

**起因**：作者问「我的意见、框选、直改应该自动落盘，为什么还需要提交？点重新加载时就应该全部自动落盘」。

**根**：`feedback.json` 是唯一的落盘路径，而「提交」＝写它＋唤醒模型。所以没提交的东西只活在页面内存里 —— 刷新即丢。**这是把两件事绑成了一个动作**，不是保存按钮的缺失。

**为什么不直接把打字过程写进 `feedback.json`**：模型那一侧按轮次收件（读成一个 round、生成待办、同页同话永久关闭）。边打字边写，模型会在半句话上动手，轮次也会碎成"每敲一个字一轮"。所以拆开、不是合并。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| 公共契约加可选字段 `draft`；桥加 `review.draft(payload)`；两种宿主各加一条路由；校验器加「draft 在 project_root 内」「draft ≠ feedback」 | 草稿需要一个**和决定分开**的落点，而落点属于"宿主把字节搬到哪"，不属于业务 | `planners-review-core`：`contracts/review-surface.schema.json`、`assets/review-bridge.js`、`scripts/serve-review.mjs`、`scripts/lib/review_host.py`、`scripts/validate-surface.mjs`、`evals/run.mjs`；`dsh-review-dock`：`lib/index.js`（`/api/review.draft` + 能力）、`lib/client.js`（中继） | 无 |
| surface 声明 `draft: 'draft.json'` ＋ 能力 `draft`；页面自动存（`status()` 是所有变更路径的汇合点，停手 0.8 秒写）与读回 | 「改了」自动存、「定了」才提交 | `scripts/review_surface.py`、`scripts/generate_review_html.py`（把路径注进页面 `data`）、`assets/review/review.html` | 无 |
| 「重新加载」先刷草稿再刷新（`askReload` 走 `saveDraft()`）；弹窗只在草稿存不进时兜底 | 刷新不再需要人做决定；而没有草稿能力的面不能又变回静默丢弃 | `assets/review/review.html` | — |
| 提交成功后清空草稿 | 已提交的东西不该在刷新后被当成"没提交的"恢复回来（那由「上一轮你说的」只读显示） | `assets/review/review.html`（`push()`） | — |

**边界**：恢复的硬规矩是**直改按页版本判定** —— 模型重出过的那一页，旧直改丢掉（`review_id` 是元素树路径，重画后同一路径指向别的元素）；意见/框选/图照常恢复。草稿**永远不唤醒模型、也永远不进 `feedback.json`**，模型只认决定。

**踩到的**：`evals/run.mjs` 里那句"宿主断言总数"是手写的（"宿主 29 条"），加两条断言就过期了 —— 已改成数出来的。手写的计数会让人以为自己看到的是全部。

---

## 2026-10-05 · 「重新加载」静默丢掉未提交的东西；缩略图整场是破的（同一个根：启动顺序）

**起因**：作者在画布上改完一句、点「重新加载」，那句就没了。截图同时暴露左侧 11–16 页缩略图全是破图 —— 他大概正是为了这个才点重新加载。

**根**：`boot()` 里 `render()` 排在 `connectWithTimeout()` **前面**。

- **破图**：建轨道时 `review === null`，`assetFor()` 只能给同源降级地址。无插件宿主下它是对的；**插件模式下页面在 `/api/review.page?…` 上，它必然 404**，且之后再没人重取（`onHostChanged` 只换版本变过的页）→ 缩略图整场是破的。
- **丢东西**：「重新加载」是裸 `location.reload()`。意见/框选/直改/图**只活在内存里**，只有「提交」才落盘 → 重读磁盘＝全丢。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| 桥接上之后重建一次轨道（`drawRail()`） | 轨道本来就跑在握手之前；插件模式里那批图的地址是错的，不重取就永远是破的 | `assets/review/review.html`（`boot()`） | — |
| `assetFor()` 的降级分支不写缓存 | 缓存会把 404 的地址钉死一整场，桥接上以后也换不回来 | `assets/review/review.html` | — |
| 「重新加载」→ `askReload()` + `#reloadDialog`：先说清丢什么，由人选「先提交再重新加载／丢弃并重新加载／返回」；没有未提交内容时直接刷新 | 人写的东西不能被静默丢掉；而"保存了就该看得见"在直改这条路上不成立，所以要在弹窗里讲明白 | `assets/review/review.html` | 那一句裸 `location.reload()` |
| 用页面自己的 `<dialog>`，不用 `window.confirm` | 插件的不透明 iframe 没开 `allow-modals`，原生弹窗被 sandbox 静默拦掉 —— 那等于又变回静默丢弃 | `assets/review/review.html` | — |
| 回归两条，都验过对照组 | `test_reload_does_not_silently_discard_unsubmitted_work`（改回裸 reload → 红 `False is not true`）；`test_thumbnails_are_fetched_again_once_the_bridge_is_up`（去掉重建 → 红 `2 != 0`） | `scripts/test/test_review_browser.py`（两条新用例） | — |
| 当前页记在**地址 hash** 上（`#<page_key>`）：`render()` 写它、`hashchange` 读它、`boot()` 按它定位 | 刷新后不该弹回第 1 页（作者反馈）。**不能用 `localStorage`**：插件的不透明 iframe 里读它会直接抛，而且那个源每次加载都是新的 —— hash 是唯一能跨刷新带走的东西。让 hash 当「当前是哪一页」的唯一来源（写+读双向），而不是再加一份跟着同步的副本 | `assets/review/review.html` | 无（`index` 仍是内存里的当前位置，hash 是它的持久面） |
| 回归 `test_reload_keeps_you_on_the_same_page` | 切到第 2 页（验 hash=`#omega`）→ `reload()` → 必须仍在 `2 / 2`；再改 hash 反向验切页。对照组（去掉按 hash 定位）实测红 `'2 / 2' not found in '1 / 2 · alpha'` | `scripts/test/test_review_browser.py`（新用例） | — |

**边界**：`askReload()` 的「先提交再重新加载」只落盘、**不唤醒** —— 要不要叫模型由人自己决定。而且**直改的那几处即使提交了也不会立刻回到页面上**（页面里的画面是生成时烘进去的），要等模型重出这一页；弹窗里写明了这一点，免得人以为又丢了。

---

## 2026-10-05 · 打字时左侧缩略图一直在动：状态变化不该重建整条轨道

**起因**：作者反馈「在右边写反馈打字的时候，左边的缩略图会自动往上移」。

**先说被证伪的那条**：第一直觉是 `drawRail()` 的 `replaceChildren()` 把滚动位置冲掉了。对照实验把它否掉：16 页与 29 页真图两种 fixture、四种视口、`overflow-anchor:none`、并拦下 `scrollTop` 赋值与 `scrollIntoView` —— 打字期间**没有任何代码碰过轨道的滚动位置**；同步清空再补齐时浏览器来不及重排，`scrollTop` 不会丢。据此写的那条测试**没有修复时也通过**，是假绿，已删（教训：先写对照组，再宣布修好）。

**真因**：`#feedback` 的 oninput → `autoState()` → `drawRail()`，**每敲一个字**把整条轨道销毁重建，并连带**重新取回每一页缩略图**（插件模式：每页一次桥往返 + 一个新 blob）。左栏一直在动，正在写的意见被打断。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| `drawRail()` 只负责整条建（换页 / 换新快照）；新增 `updateRail()` 原地改圆点与 `N框 N改` 标签，9 处状态变化路径改走它 | 一个决定变了只需改那一个按钮，不需要重建 28 个按钮、重取 28 张图 | `assets/review/review.html` | 状态变化路径上对 `drawRail()` 的 9 次调用 |
| 缩略图标签改为常驻 + `.rail-tag:empty{display:none}` | 常驻才能原地更新；`drawRail()` 里"有内容才创建"的写法只适合重建 | `assets/review/review.html` | — |
| 回归 `test_review_browser.test_typing_feedback_does_not_rebuild_the_rail` | 给每个缩略图打标记再敲一个字：标记还在＝没重建。对照组（还原 9 处）实测红 `0 != 2`；同时断言活动页确实变 `revise` | `scripts/test/test_review_browser.py`（新用例） | — |
| **随后收紧**：`updateRail(keys)` 支持只更新点名的页，两条**逐字符**路径（本页意见框、画布「改字」输入框）改传 `[当前页]` | 原来一个字符要写 N 个按钮的类名；打字只会改变当前页的状态 | `assets/review/review.html` | 逐字符路径上的整条更新 |
| **随后收紧**：`drawRail()` 建 `page_key → {按钮, 标签, 序号}` 登记表，`updateRail()` 查表；表空时先整条建 | 去掉每页一次 `querySelector`；也堵住"首屏 `render()` 之前调 `updateRail()` 会静默什么都不做"这个自己新开的口子 | `assets/review/review.html` | `updateRail()` 里逐页的 DOM 查询 |
| **随后收紧**：资源 URL 按「路径 + 版本」记住（`assetUrls`） | 每次重建轨道都重取整套缩略图（插件模式：每页一次桥往返 + 一个新 blob）。键带版本 → 模型重出这一页仍取到新图；取失败不缓存 | `assets/review/review.html` | — |
| **一处事实一个来源**：宿主推「画面已更新」时手写的类名规则删掉，改走 `updateRail()` | 那段和 `railClass()` 是同一套规则的两份写法，改一处漏一处 | `assets/review/review.html` | 重复的类名/标题赋值 |
| 加断言「一个字符只写 1 个按钮的类名」；新增 `test_switching_pages_does_not_refetch_every_thumbnail` | 两条都验过对照组：还原成整条更新 → 红 `2 != 1`；去掉缓存 → 红 `3 != 0` | `scripts/test/test_review_browser.py` | — |

**边界**：`drawRail()` 仍保留给 `render()`（换页、换新快照）—— 那时结构真的变了。若某天 `data.pages` 的页数会就地变化，必须在变更处显式调 `drawRail()`。`assetUrls` 以「路径 + 版本」为键，所以**只要版本如实反映内容**它就不会给出旧图 —— 若有任何绕过版本号原地覆盖同一路径的写法，这里会拿到旧 URL。

---

## 2026-10-05 · 作者在审阅页上直接改的那一笔，不许被整页重写静默覆盖

**起因**：作者在审阅页上直接改字、拖位置、删元素（`svg_edits`）。这一步本身是对的 —— `consume` 会确定性写回 `_internal/02_svg_source/<page_key>.svg`，写进去就是那一页的定版。问题是同一页有**两个写手**：作者的直改，和模型的生成脚本。脚本一跑就是**整份 SVG 重写**（`generate_all_*.py` 结尾是无条件的 `for key in pages: 写文件`，连"只写某一页"的参数都没有），作者那一笔不在脚本里，于是静默消失。作者的原话是「我白改了」「按理来说我直接改了源文件，那都应该以我为主的」。

**根因不是"检查太少"，是生成的作用域没有规则**：模型被要求改 A 页时跑了整批脚本，把 B、C 页一起重写；而被点名的 A 页也是整份重写。所以修法分两半：**规则**（一次只写被点名的页）＋ **一条闸门**（人改完那版还是不是现在这版）。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| **生成作用域写进 `04_svg_stage.md`**：脚本必须能被点名、**不点名就一个字节都不写**（不是写全部）、没点名的页不许动、作者改过的页以作者那版为基版 | 这是根因本身。默认全写这个默认值就是错的；只要它还在，任何一次"只改一页"都会顺手覆盖别的页 | `references/workflow/04_svg_stage.md` | — |
| **账本扩容**：`applied_svg_edits.json` 每条新增 `edits`（逐笔内容，不只是 digest）、`svg_sha256`、`svg_snapshot`；写回时把人改完那版 SVG 快照到 `_internal/05_review/versions/<page_key>-<version>.svg` | 原来只存 `edits_hash`，连"人到底改了什么"都查不回来，模型想"以人为基版"也无从下手；PNG 早有 `versions/` 待遇，**源文件反而没有** | `scripts/review_feedback.py`（`apply_pending_svg_edits`） | — |
| **一条闸门**：`human_edits()`／`human_edit_state()`／`ack_human_edit()`；`next` 报 `human_edits_lost`、`check` 把那页标 `fix`、导出时的检查画面直接拦下 | 不问画面风格，只问一件事实：**人改完那一版，还是现在这一版吗？** 人在页面上的决定只能由人撤，不能由重画顺手抹掉 | `scripts/review_feedback.py`、`scripts/orchestrate/ppt_pipeline.py`（`human_edit_problems`、`_attach_human_edits`、`ack-human-edit` 子命令） | — |
| **`ack-human-edit --page X --note '...'`**：交代按**版本**记账，再画一次闸门重新立起来 | 覆盖可以，但必须先说清怎么处理的（带进新版／被新版替掉／恢复）。和 `resolve` 同一条规矩：空话不算 | `scripts/orchestrate/ppt_pipeline.py`、`references/workflow/07_visual_review.md` | — |
| **回归 `test/test_human_edit_guard.py`（5 例）** | 关键断言要能证伪：直改落 SVG 且内容入账、重画被抓、空 note 不放行、交代只对当前版本有效、没被改过的页永不误报 | `scripts/test/test_human_edit_guard.py`（新） | — |

**刻意没做的一件事**：**自动回放**人那一笔。`svg_edits` 按**元素树路径**（`0.5.4.0`）定位，页面重画后同一路径指向另一个元素，自动套回去会改坏别的东西。所以这条路只能"停下来 + 重新落一遍"，快照是给人看的还原底本，不是自动补丁。

**踩到并修掉的坑**：闸门最初对**全量页面**无脑算 `page_version`，而 `page_version` 要读 SVG —— CREATE 阶段页面还没写出来，于是 `next` 在 video 路线上从"给出下一步动作"退化成 `FileNotFoundError`（`test_video_route_pipeline` 当场变红）。现在只对**账本里真有人改过、且 SVG 已存在**的页去看。

**边界**：闸门只对**账本里有记录**的页生效；从没被人改过的页永不误报（有回归钉着）。误报的代价是模型多写一句交代，漏报的代价是人白改一场 —— 所以宁可报。

---

## 2026-09-30 · 幻灯片（PPT）全链路升级（v6.0）：多模态四件套模板包、SVG→PPTX 转换器与校验器协同、极简 PPT 式审阅工作台

**起因**：视频路线（`route == "video"`）稳定后，幻灯片（PPT）路线（`route == "slides"`）暴露出四大瓶颈：① 原模板提取只机械抠取 XML 边缘装饰，产出空壳 `<g data-template-content-layer="replace"></g>`，完全丢失内部版式骨架与比例；② 领域规则偏抽象哲学，换模型或长链路下极易退化为千篇一律的「三等分描边卡片 + 边框套边框」；③ `native_svg_to_ppt.py` 不支持 `<style>`/`:root` `var(--...)`、`<tspan dy>` 多行段落、叶子节点 `transform`、`1px` 细分割线、文字/分组 `opacity` 与 `<linearGradient>`，反向倒逼模型写冗长死板的内联 SVG；④ 审阅页交互弱（框选后画布无常驻标记、模型不知道框中了哪个 SVG 节点、改一个错字或删一个色块也得唤醒模型重画整页）。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| **多模态模板提取与四件套模板包契约（v2）+ 2 套内置 90 分旗舰模板包** | 用一条命令完成多模态预处理（`extract_template_pack.py`），将模板包收敛为「`tokens.css` + `skyline_shell.svg` + `primitives/*.svg`（7 套无碰撞版式原语）+ `SPEC.md`/`anchors/`」四件套，并内置 `agency-social-proposal`（社媒种草提案风）与 `consulting-product-strategy`（咨询产品战略风）两套旗舰包 | `scripts/template/extract_template_pack.py`（新）、`scripts/template/template_library.py`（v2 四件套 + v1 兼容）、`assets/template_library/agency-social-proposal/*`（新）、`assets/template_library/consulting-product-strategy/*`（新）、`references/workflow/01_template_intake.md`、`references/contracts/template_package.md` | 新建模板时繁琐的八步中间 JSON 手工拼装（旧 v1 仍保留向后兼容以通过历史回归） |
| **去玄学化四大领域规则文档** | 将好 PPT 的规律固化为可量化的「5 条黄金铁律 + 6 条反丑红线」（Card-in-Card 禁令、75:20:5 色彩配比、12 列栅格、连续同构禁令、数据页去装饰框）与 7 类可执行版式原语配方 | `references/domain/style_system.md`、`references/domain/layout_taxonomy.md`、`references/domain/svg_rules.md`、`references/domain/svg_to_ppt_rules.md` | 旧 `svg_to_ppt_rules.md` 中因旧转换器缺陷导致的 `<style>`/`:root`、`stroke-dasharray`、`<linearGradient>`、`<tspan dy>` 历史禁令 |
| **`native_svg_to_ppt.py` 六大能力升级与 Bug 修复 + `validate_svg_layout.py` 三项硬拦截** | 转换器原生支持 `<style>`/`:root` `var(--...)` 展开、`<tspan dy>` 多段落拆行、全部叶子节点 `transform` 合成、`1px` `<rect>` 细分割线保真、`<text>`/`<g>` `opacity` + `letter-spacing * FONT_SCALE` + `dominant-baseline` + `rgba()`、以及 `<linearGradient>` → 原生 DrawingML `<a:gradFill>`；校验器新增 `LINE_CROSSES_TEXT`、`EMOJI_IN_SLIDE_TEXT`、`TEXT_OVERFLOWS_CONTAINER` | `scripts/native_svg_to_ppt.py`、`scripts/validate_svg_layout.py`、`scripts/project_state.py`、`scripts/test/test_slides_upgrade.py`（新） | — |
| **极简 PPT 式视觉审阅工作台（画布常驻编号框 + 元素命中 + 舞台直改/按键删除写回）** | 在完全保留 `planners-review-core` 接缝的前提下，升级为顶部单行防变形工具栏 + 画布常驻带编号框（`① ②`）+ 自动命中 `data-review-id` 节点 + 舞台直改（改字、`A-/A+` 调字号、拖拽位移、`Delete`/`Backspace` 删除元素），`consume(root)` 收件时确定性写回 `.svg` 并重算 hash，纯微调可 0 轮直接通过导出 | `assets/review/review.html`、`scripts/generate_review_html.py`、`scripts/review_feedback.py` | 页面上冗余的工程连接话术、节点树路径标签（`#0.4.1` / `<rect>`）与百分比坐标串 |

## 2026-09-29 · 新增 `editorial-archive` 四域视频风格、预埋子元素动效交接与新风格提取 SOP

**起因**：视频路线此前虽能读取 `video-craft/visual/themes/` 的配色 token 并给元素加 `id`，但缺少两件关键能力：① 面对同一条视频里的不同信息形态（金句、流程模型、图文证据、历史原件），模型容易画出毫无起伏的三行文字表或把每页塞得过满；② 静态 SVG 没有在制作时按动作拆好子元素层级（`.anim-*`）与路径（`pathLength="1"`），导致下游 `video-craft` 只能做生硬的整块浮现或被迫重画。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| 新增 `references/domain/video_style_editorial_archive.md` 与 `assets/video_style_references/editorial-archive/`（11 张多模态参考图 + 7 屏实测联系表） | 将 34 个 Pinterest 样本收敛为「文字凸显 / 模型构建 / 图文混排 / 图片为主」四域 × `Solo（独奏极简）/ Multi（群像展开）` 密度矩阵，确立 6 条反杂乱与防刺眼护栏（重音反转屏用深炭墨底 `#181715` + `≤12%` 氧化砖红 `#C8553D`，严禁满屏刺眼红；全片 Solo 屏 `≥30%`），并保留原图供多模态模型直接对齐 | `references/domain/video_style_editorial_archive.md`（新）、`assets/video_style_references/editorial-archive/*`（新）、`references/workflow/03_video_route.md`、`SKILL.md` | — |
| 升级视频路线 SVG 交接要求：支持预埋 `data-step` + `data-anim` + `.anim-*` 复合子元素动效钩子 | 与 `video-craft/references/svg-animation-contract.md` 对齐，在静态 SVG 生成时一步写好子元素类名、`pathLength="1"` 与绝对坐标（`<g data-step>` 严禁挂定位 `transform`），下游按实测音频零返工驱动 3~4 阶段复合动效 | `references/workflow/03_video_route.md`、`SKILL.md` | 「页面里完全不加任何动画结构说明」的旧口径（改为不写死毫秒时长，但预埋声明式 `data-step` / `data-anim` 子元素钩子） |
| 新增 `references/workflow/08_video_style_extraction_sop.md` | 把本次从参考画板逆向提取视频风格与预埋动效模板的完整六步流程（采集抽帧 → 双路并行拆解 → 四域×Solo/Multi 收敛 → 复合子元素动效契约 → 真项目 `/prototype` 压测 → 双端落盘）及 6 条实测技术避坑沉淀为标准 SOP，供后续提取更多视频模板复用 | `references/workflow/08_video_style_extraction_sop.md`（新）、`references/architecture.md` | — |


## 2026-09-26 · 宿主生命周期搬进公共模组（只留一份）

接入 `planners-review-core` 时留下的债：缝集中了**宿主**（`serve-review.mjs`），没集中**宿主的
生命周期**，于是 ppt-hell 与 video-craft 各写一份 `review_surface.py`，并且已经漂移过（僵尸判据、
SIGKILL 升级、身份比对只在一家修过）。现在收进 `planners-review-core/scripts/lib/review_host.py`。

| 动了什么 | 为什么 | 影响了哪些 module | 删了什么 |
|---|---|---|---|
| 写/校验 surface、`host_state`、`host_alive`、`start_host`、`stop_host`、`_pid_alive`、`_startup_report`、`_port_of`、`open_review` 全部改从模组 import | 一份实现，两处调用；再漂移就会两边不一致 | `scripts/review_surface.py`（只剩 `surface_document` 与薄壳）、`scripts/lib/planners_modules.py`（只剩"找模组"）、`scripts/test/test_review_surface.py`（生命周期调用改指模组、传 surface 路径；两处 mock 目标改到 `review_host`） | 本 Skill 里那 7 个函数的实现；适配器里的 `node_binary()`（归模组，覆盖变量统一成 `REVIEW_CORE_NODE`） |

测试 183 条不变（唯一的 error 是既有的 `test_source_assets` soffice 转换失败，与本轮无关）。
`--surface-only`（只报 surface 路径、不起宿主）那条分支留在 `ppt_pipeline.review_open` —— 它要的
`entry`/`feedback_path` 是本 Skill 的产物位置，属于业务。

## v5.5 补丁（B8.3）—— 审阅面交出去了：surface ＋ 桥，宿主是公共件

**为什么**：页面审阅此前由本 Skill 自己端（`review_server.py`）、自己收反馈、自己判死活。这套东西每个带审阅的 Skill 都要写一遍，而且**没插件时能审、有插件时能挂进 DSH 侧栏**这件事根本不在 Skill 的能力范围里。公共件 `planners-review-core` 落地后，这条缝的所有权换人：显示、serve 资产、落文件、唤醒模型归宿主；**审什么、能下什么决定、怎么绑版本仍然归 Skill**。

**边界怎么变了**

- **Skill → 宿主 的东西变成一份 surface**（`_internal/05_review/review-surface.json`）：入口、被 serve 的 `dir`、反馈文件、唤醒文案、能力。契约里**没有**单位／决定／版本——那些是审阅语义，宿主不解释。
- **页面与宿主之间只剩三种动作**：`await review.asset(rel,{v})`、`await review.write(整份状态)`、`await review.wake({unit})`（＋声明了能力才有的 `upload`）。页面里**不放桥的副本**，只留 `{{REVIEW_BRIDGE}}` 注入点。
- **写反馈的人从服务器变成页面。** 于是 `save_feedback`（写盘前校验）的角色拆开：宿主原样落盘 → **`consume`（`next` 时）**校验、规范化写回、留档。绑定判据仍是 `review_id`，但盖章（每页版本与 PNG hash）从"提交时由服务器盖"变成"收件时由 Skill 盖"——页面自己写什么都不算数。
- **陈旧提交的拒绝位置变了**：页面提交前比 `review_id`，对不上就**不写**（人看到「这一页已更新，先复核」）；模型侧 `consume` 认得出它是上一版并报 `stale`（不算批准，items 仍可读）。以前是服务器 409 一步拒绝，现在分成人看到的那一步与 Skill 认权威的那一步。
- **`dir` 只能取项目根**：审阅页生成在项目根，渲染图／上传件／素材分散在 `_internal` 的几处，最近公共祖先是根。搬页面进子目录会改项目契约的产物位置，不在这一轮做（宿主仍逐路径 realpath 包含性校验）。
- **`review_server.py` 只剩模板审阅那条线**（`template-review → server(root,'template')` 仍用它）。页面审阅的那三条路由退出运行路径，但**本轮没删**：删它们要动模板线共用的 `_with_provenance`／`_png_hashes`，按边界留着等派单。

**被牵动的 module**：新增 `scripts/review_surface.py`（surface ＋ 宿主生命周期 ＋ 死活判据）、`scripts/lib/planners_modules.py`（按名字找公共件 ＋ `node_binary()`）；`scripts/generate_review_html.py`（写 surface、页面数据给**相对路径＋版本**、`previous*` 保留、`?v=` 改成页面向桥要）、`scripts/review_feedback.py`（`consume`／`validate_document`／幂等留档／`save_feedback` 保留给旧服务器）、`scripts/project_state.py`（`approvals()` 认 `review_page` 来源）、`scripts/orchestrate/ppt_pipeline.py`（`review_open` 换宿主、`next` 收件并报 `review_intake`）、`assets/review/review.html`（页面脚本整体换桥）、`references/workflow/07_visual_review.md`、`references/contracts/project_contract.md`、`references/architecture.md`、`scripts/test/`（166 → 177，含真浏览器冒烟改成驱动新接缝）。

**第二个审阅面：模板审阅（同日，核清单时发现漏派）**：模板审阅是独立主体（单位 `layout_id`、`pass`/`discard`/`revise`、粒度整批、无上传需求、watch 盯快照），字段逐条独立判过（`review_surface.TEMPLATE`），页面接缝化（裸注入点、服务端渲染的卡片与 canvas、资产走桥、三档状态行、永久 ⟳、不碰本地存储），新增 Skill 侧收件 `template_feedback.consume`（校验 + **重算派生量** + **盖章** + 幂等）与 `template_review_intake`。**顺手修掉一个真 bug**：expected_layouts 原来按 manifest 推、页面按 registry 渲染 → 真项目上一份合法提交被判死（G-21）。发布闸门原来只认旧服务器的 provenance（G-22）。**补一格从未运行过的分支**：发布闸门"全通过 → 放行"此前**没有任何测试执行过**（磁盘上也没有项目能走到它：闸门要 `template_visuals/*.png` 非空，唯一的真项目是库模板路径）—— 而这一片刚在两处红里被证明最容易藏"只认旧写者/只认旧来源"。现在用**夹具**把它跑到（完整自审 + 非空源模板页 + 预览清单 + 锁层 canvas），连打包一起跑到（库根指到临时目录，绝不写进随 Skill 发布的库）；测试里标明这是**夹具层**的验证，结论那一层仍然只有真项目才算数。

**退役**：`review_server.py` 与它的生命周期用例、`ppt_pipeline` 的三个宿主函数、`review_feedback.save_feedback`、那处 `webbrowser.open` —— 全部在新路径真项目验过**之后**才删；本 Skill 不再有任何 HTTP 服务器。

**桥是增强，不是氧气（同日，video-idea 那一路"扫同类"报出）**：本页原来把 `render()` 排在 `connect()` 之后、并且两个提前 `return` 都在它前面 —— 插件里没桥/握手不落地时整页空白且零报错。改成：**先用自己的 data 画完，再握手**；握手加 2500ms 上限，不落地按"没有桥"降级并自述"只读"；无桥时资产回退同源相对地址、提交入口明说存不进去。四条判据里有一条是**结构性**的（`render()` 必须排在第一个 `await` 之前），另加一条**常驻红对照**（把渲染退回旧顺序 + 握手不落地 → rail=0）。记 G-20。

**重发那一档 + 注入点独立成行（同日）**：① 同一次提交被重发（宿主报 `duplicate`）时，页面照宿主给的那句说"已在路上"，不再套"并已通知模型…"（**页面说的必须是实际发生了什么**，这是"只说自己核过的事"的另一面）。② 公共件把 `{{REVIEW_BRIDGE}}` 换成**整段注入**后，页面原来 `<script src="{{REVIEW_BRIDGE}}">` 的写法把标签撑破、桥 404 —— 改成注入点独立成行、只出现一次；`host_alive()` 也改成与注入形态解耦（比"注入点以外逐字节相同"，不比注入那一段）。两条都记进 GOTCHAS（G-18/G-19）。

**页面不再替宿主作没核过的证（同日，真人使用）**：宿主"接受了通知"与"agent 看到了通知"是两件事（插件宿主会去会话日志里核对并回 `verified`，无插件宿主不回）。页面原来一律说"已通知模型"，把两者抹平。改成按 `review.wake()` 的返回分档说（核过 / 未核对各一句），并把核验结果补写进 `provenance.wake`（同一份 payload、同一个 `submitted_at`，不是第二轮提交）。

**纠正"意见的生命周期"（同日，用户本人打回）**：用户的原话是"我给你意见，你改完了，就是结束了，这个意见也不该有了"。原来 `resolve` 只是把条目从"未决"里摘掉，同一句话再出现仍会生成新条目，于是人得回头清空自己的意见才算数——**把模型的收尾工作转嫁给人**。改法：`resolve` 时把该意见的**内容身份**记进 `resolutions.json` 的 `closed`；`consume` 跳过已关闭的同页同话（并报 `review_intake.suppressed`，不静默）；"有意见不许批准"只约束人刚写下的新意见；整套批准后 `items` 为空、`next` 报 `EXPORT`。**边界**：换说法＝新意见（防过度抑制，有测试钉住）。

**纠正 B8.2（同日，真人使用打回）**：上一轮的意见原来是**预填进参与判定的输入**的，于是同一段字同时是"上一轮我要过什么"与"本轮我有什么意见"——页面判成 `revise`、整套提交跳过该页、`items` 再生一条与上一轮相同的待办。改成**只读上下文**（面板一块，显示文字/框选/图片改动，不进 `feedback`/`annotations`/`assets`）：这类页初始 `pending`、一次点击可批准、整套提交能覆盖、不再产生重复条目。同时**逐页唤醒语自带决定**（整句覆盖：`"<page_key> 要求修改：<要点> —— 只重出这一页…"` / `"<page_key> 已通过。"`），模型不用先翻文件。教训记 G-15。

**B8.5 前置（同日）—— `review` 两种模式**：Q11 裁定"有插件就用插件"，所以 `review` 加了 `--surface-only`（别名 `--no-host`）：只生成页面 + 写 surface + 校验，报 surface 绝对路径给宿主的 `review_open` 工具，**不起宿主**（起了会有两套界面写同一个 `feedback.json`）。默认那条仍是无插件时的路。判据（"宿主有没有那个工具"）写进 `SKILL.md` 与 `07_visual_review.md`，不靠环境探测。

**B8.4c（同日）—— 那条链的最后一环**：页面接住 `review.on('changed')`，自己读 `snapshot.json`、自己 diff，**只换版本变过的那几页的 `<img>`**，把它们退回 `pending`，并更新内存里的 `review_id`（不更新就会被 Skill 判上一版）。surface 因此多了 `watch: ["snapshot.json"]`（宿主只 stat，不解释）。**不整页重载**是硬要求：重载会丢人写了一半的意见、框选与滚动位置。另加「变化戳：N 次 · 最后 HH:MM:SS」状态行，把"宿主没推"与"页面没处理"分开。上传控件改为按 `review.capabilities` gate（公共件修好后它可靠）。踩到的时序坑：**戳是变化驱动的，加载后的第一个采样周期只建立基准**（G-14），测试要先等基准。

**跟进（同日）**：公共件修掉"`review.capabilities` 在无插件模式下恒为空"之后，上传控件改成**按能力 gate**（并让冒烟断言能力真的到了页面手里）；整套提交补上 `wake` 的**整句覆盖**（`{unit:'整套', text:…}`），不再"整套提交不唤醒"；`review_server.py` 的三条页面审阅路由加退役注释，**推迟到模板线 surface 化时一起删**。

**删掉/退役**：本 Skill 自己的页面审阅宿主路径（`review` 不再起 `review_server.py`）；页面里的 `/review-asset`、`/review-feedback`、`/health` 调用；页面里的 `assetUrl`（换成 `await asset`）；宿主的"逐行解析启动 JSON"（公共件打印的是美化 JSON，逐行永远解析不到——见 GOTCHAS）。

---

## v5.5 补丁（B8.2）—— 逐页重出之后，上一轮的意见去哪了

**为什么**：审阅是跨回合的（人写意见 → 模型重出一页 → 人再打开审阅页），而 `feedback.json` 只有一份、每次提交**整份覆盖**。于是「模型按意见改完一页」这件事本身会把那一页的意见从下一页面上抹掉：客户端 state 初始化为 `feedback:''`／`annotations:[]`／`assets:[]`，页面只带 `decision`。同一轮里还有第二件事：页内素材是**同名原地替换**的，`<img src>` 不带版本时浏览器给的是缓存里的旧图——页内素材与页面大图两种投递方式不一致。

**边界怎么变了**

- **审阅面的读法多了一条「带回来的意见」**：审阅页的每页数据只在「这一页的版本在反馈之后变过」时才带 `previous*` 四个字段（`generate_review_html.previous_page_feedback()`）。**版本没变的页不带**——那里的批准本来就走 `approvals()`，两条通道不重叠。判据是版本不同，不是「有没有意见」。
- **「清空 = 确认」成为页面的确认动作**：带回来的意见仍然算意见（非空即 `revise`，`save_feedback` 这条没动），所以人要么清空它、要么补充它。**语义上它回答的是「上一轮提的改到位了吗」，不是「这一轮要不要改」。**
- **`feedback.json` 之外多了一个回查口**：`history/round-NN.json` 装**被覆盖的那一轮**。`feedback.json` 仍是「当前这一轮」的唯一真相，`review_id` ＋ `review_current()` 的 stale 保护一个字没改。
- **素材有了和页面大图同一种版本表达**：`assets[].version`（sha256 前 12 位）＋ `src` 上的 `?v=`。页面大图的 `?v=<页版本>` 早就是这样，这次只是把页内素材拉平。

**被牵动的 module**：`scripts/generate_review_html.py`（`asset_records()`／`previous_page_feedback()`／每页数据多四个字段）、`scripts/review_feedback.py`（`archive_round()`、提交返回与 `flow_events` 带 `archived`）、`assets/review/review.html`（`assetSrc()`／`assetVersion()`、`#previousNote`、state 初始化、上传后带 `sha256`）、`references/contracts/project_contract.md`、`references/workflow/07_visual_review.md`、`references/architecture.md`、`scripts/test/test_v5.py`（162 → 166）。

**删掉/退役**：无。**没动的**：提交仍是整份覆盖、批量批准只作用于未处理页、`review_server.py`（它本来就把 query 剥掉再解析路径，服务端零改动）。

---

## v5.5 —— 两条路线各有一等公民待遇，闸门补在产出侧

**为什么**：一次视频路线的全链实测（`<项目>/_测试报告.md`）暴露出一类共同缺陷——**规则写下来了，但没有东西在产出侧核它**：出口契约要求 SVG 带稳定 `id`、要求作者看过整套画面，代码里却没有任何检查；校验器对文字出画布只给提示级；`inspect` 填三个 `ok` 就能过；视频路线的唯一终态是导出 PPTX。同一轮里还有三处「声明与实物不一致」的静默缺陷。

**边界怎么变了**

- **路线升成一等概念**：`route`（`slides`／`video`）记进项目状态，成为「跑哪一半检查、完成标准是什么」的唯一取值处。此前两条路线共用一套检查与一个终态。
- **校验器按出口拆成两半**：通用那组两条路都跑（文字压文字、元素出画布含文字、空页、文字缺填色、`font-weight`、图片必须是真实项目内文件且不被拉伸）；「转成 PPT 会坏」那组只跑幻灯片（字号下限、禁用元素与属性、`rotate`／`skew`／`matrix`、`tspan` 换行、锁层）。**被跳过的规则连同原因写进 `skipped_rules`**。
- **视频出口多了一组只属于它的闸门**：`MISSING_ELEMENT_ID`、`DUPLICATE_ELEMENT_ID`（含根 `<svg>` 的 id）。
- **契约绑定进入本 Skill**：顺着契约所在目录核 `script.md`，并把每一项核对结果留成正面记录（`ok`／`warning`／`error`／`unchecked`）。
- **新建 module `scripts/style/theme_tokens.py`**：风格库（`video-craft/visual/themes/`）的唯一读取口，`list`／`show` 两个动词，负责把 `:root` 与 `var()` 展开并报出解析不掉的 token。

**被牵动的 module**：`init_svg_project.py`（分组去重、剥标记、当场点名、`--assets` 口径、路径报错、状态记 route 与契约摘要）、`project_state.py`（`route`／`project_root_of`／`parse_position`／`contract_binding`／`review_recorded`／`inspected` 新判据）、`ppt_pipeline.py`（视频路线终态、审阅是门、`next` 给动作不给 errno、审阅服务生命周期、`require_direction`）、`validate_svg_layout.py`（按路线取用、`TEXT_OUTSIDE_CANVAS`、id 两条、`UNDEFINED_CSS_VAR`、样式表取法）、`template/layout_canvas.py` 与内置模板数据、`references/` 全部（`architecture.md` + 三份 workflow + 两份 domain + 两份 contracts）、`SKILL.md`、`scripts/test/`（52 → 161 条）。

**删掉/退役**：适配器里那个只进不出的「未映射字段（待裁决）」收集器；「跨页重复的元素沿用同一族前缀」这条 id 规则；视频路线上的「转成 PPT 会坏」那组检查（及随之而来的静默跳过）；用端口探测判断审阅服务死活。三个静默缺陷一并修（`locked_sha256` 无锁层时报错、`data-template-canvas-version` 被真的读、`footer_bar` 从 `rect` 改声明为 `line`）。

### 同一版本内的三个补丁（第三轮验收带回来的）

- **N-1 风格 token 与校验器互相打架**：文档教 CSS class + `var()` 落地，校验器只认显式属性（首跑 43 error + 43 warning）。**改校验器**：视频路线认三种取法（元素属性／元素 `style`／class 命中的同页 `<style>` 规则），并新增 `UNDEFINED_CSS_VAR`。选择器只认由 class 组成的简单／后代选择器——保守方向，宁可要求显式属性。
- **N-2 `contract: []` 分不清「核过没问题」与「没核」**：每项核对留一条带 `level` 的记录，视频路线永远至少一条。
- **N-3 端口假阳性没被修掉，只是被绕过了**：`review_server.py` **没有缺陷**（活着的服务上 `curl` 与 `urllib` 一致：`/review 200 / 43 bytes`、`/health 200 / 190 bytes`；死端口才空响应）。所以不改代码，改说法：CHANGELOG 与 `07_visual_review.md` 写清「保证本 Skill 不被端口探测骗；不保证外部清进程后残留 socket 的假 OPEN」。

### 第四轮补丁：id 全片唯一

- **为什么**：作者在真实链路上跑通了动画（4 屏 55 个 id 全部按 id 指名、`hyperframes check` passed），证明出口契约成立；但 `hyperframes check` 把 `#caption-1` 对到了一个落在第 3 屏的时刻（报告 §11.4）——**同一族 id 在 4 个 clip 里各有一个**，而下游会把各屏内联进同一个 DOM。
- **改了什么**：三处措辞（`SKILL.md` 责任边界、`03_video_route.md` V2 与末尾、`04_svg_stage.md` 制作第 5 条）＋ 校验器提示（`STABLE_ID_HINT` 本身也是规则）＋ 新增 `DUPLICATE_ELEMENT_ID`；随后把重复判定的范围扩到**含根 `<svg>` 的 id**（`MISSING_ELEMENT_ID` 仍不算根——两条判据回答的问题不同）。
- **牵动的 module**：`validate_svg_layout.py`、三份文档、`scripts/test/test_route_rules.py`。

---

## v5.4 —— 视频路线的入口

**为什么**：上游把已批准的逐屏画面契约 `visual-plan.json` 5.0 直接交进来（一平铺文件夹的散图就是全部素材），需要一个**没有源文档**的入口。

**边界怎么变了**：新增入口 `init_svg_project.py <project> --assets <图片文件夹> --plan <visual-plan.json>`；`screens[].screen_id` 原样成为 `page_key`（不改名、不重新编号）；上屏内容进 `content`、理由与来源进 `notes`；散图走同一套共享登记器，未被任何一屏引用的图点名报错。同时 `page_version` 不再因缺 `source.md` 崩溃，并允许一屏只有画面、没有文字（空页判据从元素计数改成「既无文字也无图」）。

**被牵动的 module**：`init_svg_project.py`（新增 `adapt_visual_plan` 这一处 adapter）、`project_state.py`（版本计算）、`validate_svg_layout.py`（空页判据）、`references/workflow/00`、`CHANGELOG`、测试。

**删掉**：`page_version` 对 `source.md` 的硬依赖；`visible < 3` 的元素计数空页判据。

## v5.3 —— 能力解耦

**为什么**：把 ppt-hell 从「一个做 PPT 的流程」收成「一个做视觉画面的 Skill」，让板块之间不再互相搅。本轮只做边界与归属。

**边界怎么变了**：

- 「用参考」与「建参考」分开：做画面开局直接读风格参考库挑一个，不再被八步提取流程当前置；八步提取仍原样打包，只在用户要真实复用品牌资产时启动。
- **画幅归一 16:9 并收进唯一 owner `scripts/canvas_frame.py`**（原先散在 `project_state.py` 里的 `1780/1040/1000/986.0/22/200/120`）；校验器、转换器、渲染器、模板 runtime 一律从这里取值。
- **检查画面与转换 PPT 共用同一套坐标几何**：校验器直接调用转换器的 `parse_axis_aligned_transform`／`compose_axis_aligned`，不再自己实现一份（两份曾对同一输入差 100px）。
- **检查画面的权威运行点移到导出时**（幻灯片路线）：`export` 先逐页跑一遍，有「转成 PPT 会坏」的错误就拦下不出稿；`check` 里那次是提前预警。
- 状态与版本合一：`project_state.py` 声明 `__all__`，消费方逐个具名导入，不再 `import *`。
- 模板审阅拿到「必须看过当前版本」保护（快照 + `review_id`）。

**被牵动的 module**：`canvas_frame.py`（新 owner）、`project_state.py`、`validate_svg_layout.py`、`native_svg_to_ppt.py`、`render_svg_png.py`、`template/*`、`references/workflow/01`、`04`、`SECURITY.md`、测试。

**删掉**：`SECURITY.md` 的审批口令要求；测试里「`export` 必须抛 `ValueError('human review')`」的断言；「整页位图不算页面／元素必须是原生文本与图形」这条规则。

**同时修掉三个真 bug**：`estimate_text_box` 忽略 `text-anchor`（右对齐／居中文字会误报越界与重叠）、`check` 对未变页面不回 `issues`（全量扫描看不到告警分布）、`check_rhythm` 是无人写入 metadata 的死代码。

---

## 更早

v5.2.1（描边保真：删掉描边上的 `* 0.6` 系数，新增低于 0.5pt 的告警）及更早的改动只记在 `CHANGELOG.md`。**更新这一节之前先看 `references/architecture.md` 的「动了 X 会牵连什么」**——边界变了就同步改它，然后把这次改动记到这里。
