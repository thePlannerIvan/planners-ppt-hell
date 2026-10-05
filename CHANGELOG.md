# Changelog

## 2026-10-05 — 作者在审阅页上直接改的那一笔，是定版；不许被整页重写覆盖

起因：作者在审阅页上直接改字、拖位置、删元素。改是改进了 `.svg`（`consume` 确定性写回），但同一页还有第二个写手 —— 模型的生成脚本，脚本一跑就是**整份 SVG 重写**，作者那一笔不在脚本里，于是静默消失。作者的原话是「我白改了」。根因不是检查太少，是**生成的作用域没有规则**：`generate_all_*.py` 一次跑写十四页，连"只写某一页"的参数都没有。

- **规则（根因）**：`04_svg_stage.md` 新增「生成的作用域」——脚本必须能被点名；**不点名就一个字节都不写**（不是写全部）；没被点名的页不许动；作者改过的那一页，**作者改完的 SVG 就是基版**，要在它之上叠加，不许从自己的脚本重新长出来。
- **账本**：`applied_svg_edits.json` 每条现在存**逐笔内容**（`edits`，原来只有 digest，连改了什么都不知道）、`svg_sha256`、`svg_snapshot`；写回时把人改完那版 SVG 快照到 `_internal/05_review/versions/<page_key>-<version>.svg`（PNG 早有这个待遇，源文件反而没有）。
- **一条闸门**：`human_edits()`／`human_edit_state()`／`ack_human_edit()`。只问一件事实 —— **人改完那一版，还是现在这一版吗？** 不是、又没人交代过，`next` 就在入口报 `human_edits_lost`（带逐笔内容与快照路径），`check` 把那页标 `fix`，导出时的检查画面直接拦下不转换。
- **交代**：`ppt_pipeline.py <project> ack-human-edit --page <page_key> --note '...'`，要写清实际怎么处理的（带进新版／被新版替掉／恢复），空话不算。交代按**版本**记账：再画一次这一页，闸门重新立起来。
- **刻意不做自动回放**：`svg_edits` 按元素树路径定位，页面重画后同一路径指向另一个元素，自动套回去会改坏别的东西。快照是给人看的还原底本，不是自动补丁。
- **回归**：`scripts/test/test_human_edit_guard.py`（5 例）——直改落 SVG 且内容入账、重画被抓、空 note 不放行、交代只对当前版本有效、从没被改过的页永不误报。全量 200 例通过（余 1 例是 `soffice` 环境缺失，与本改动无关）。

## 2026-09-26 — v5.5 补丁：第二个审阅面（模板审阅，`layout_id`）上缝；`review_server.py` 退役

起因：核清单时漏了 **ppt-hell 的模板审阅面**（全量 14 个面里的第 2 个；文档里明说它与页面审阅**不要合并**）。它顺带收掉本 Skill 最后一处 `webbrowser.open` 与最后一台自建 HTTP 服务器。

- **面独立判过（R10）**：单位 `layout_id`、决定词表 `pass`/`discard`/`revise`、粒度**整批**（页面上只有一个提交动作，唤醒语按"几通过/几返修/几舍弃 + 哪些 layout"整句覆盖）、**不声明 `asset-upload`**（只读对照 + 决定 + 命名，没有上传需求）、`watch` 盯 `template_review_snapshot.json`（**重建即整页作废**，这里没有"原地换图"，盯快照是为了让开着的那一页立刻自证过期）。这些理由逐条写在 `review_surface.TEMPLATE` 旁边，**没有一条是从页面审阅抄来的**。
- **页面接缝化**：`{{REVIEW_BRIDGE}}` 裸标记独占一行；卡片与 canvas 仍是**服务端渲染**（没有桥也看得全）；资产改成相对 `dir` 的地址 + `data-asset`（有桥走桥换成帧内 blob，没桥同源相对地址照样显示）；提交走 `review.write(整份状态)` + `review.wake(整句)`；状态行按"宿主已核对 / 未核对 / 同一次提交重发"三档说实话；持久 ⟳ 出口常驻；不碰本地存储。生成器顺手修掉两处：**没有 `template_visuals` 的项目不再端一张坏掉的 contact sheet**（库模板路径本来就没有源模板页），卡片加了 `scroll-margin-top`（粘性页头会盖住跳转目标的决定控件，实测点击被它截走）。
- **Skill 侧收件**（`template_feedback.consume`，`next` 每次回来报在 `template_review_intake`）：校验决定词表与 layout 集合、返修必须留意见、`approve_all` 必须全通过、**全部通过的三道门**（模板命名 / 候选审计 / 视觉门）；**重算派生量**（页面写的 `approved` 不算数）；**盖章**（审阅页 HTML、源模板渲染页、模板包的 sha256）—— 发布闸门据此判定；陈旧的那一份不盖章、也不算批准。幂等（同一份提交只处理一次、只记一条事件）。
- **一处事实一个来源（修掉一个真 bug）**：expected_layouts 原来按 `page_manifest.template_intake.mode` 推（非 fidelity 只认 `reference_system`），而**页面按 registry 渲染** —— 真项目上（manifest `autonomous` + 5 个 layout 的 registry）一份合法提交被判"没覆盖全部 Layout"。现在**取快照里那份列表**（与页面同源）。见 G-21。
- **发布闸门认新写者**：`require_approved_feedback` 原来只认 `provenance.source == 'review_server'`（见 G-22）→ 现在认 `template_review_page` 并保留旧值（老项目里那份批准是人真的给过的），三份摘要改由收件层盖章。
- **退役（迁移永远在删除之后）**：模板线在新的缝上跑通、真项目验过之后才删 —— `scripts/review_server.py`、`ppt_pipeline` 的 `server()`／`start_server()`／`server_alive()`、`review_feedback.save_feedback()`、专测旧服务器的 `test_review_server_lifecycle.py` 全部删除；那处 `webbrowser.open` 随之消失（开浏览器是**一件事**，只有一套行为：公共件 `review-host.mjs` 的 `open`，`--no-open` 关掉）。**本 Skill 里不再有任何 HTTP 服务器。**
- **测试**：新增 `test_template_surface.py`（**12 条**：surface 0 警告 + 两个基准 + 页面结构 + 服务端渲染 + 无插件宿主 serve/停干净 + 收件矩阵 + 幂等 + 盖章 + 陈旧 + **旧规则红对照** + **发布闸门"全通过 → 放行"那个此前从未运行过的分支**（夹具层，连打包一起跑到；自带"绝不住随 Skill 发布的库里写东西"的库根隔离））与 `test_template_review_browser.py`（真项目副本上跑，七格证据，含反面对照与插件路径的 postMessage）。184 → **189 全绿（3 skipped）**（删掉旧服务器的用例、加上新面的回归网）。
- **文档**：`references/architecture.md`（模板侧收件进模块表、删除测试量过两次）、`references/contracts/template_package.md`（第 7 步）、`references/contracts/project_contract.md`（两个面的文件与写者）、`references/workflow/01_template_intake.md`（人审那一步）、`SKILL.md`（两个面 + 两种宿主模式）、GOTCHAS G-21／G-22。

## 2026-09-26 — v5.5 补丁：桥是增强，不是氧气（页面不许把渲染挂在握手上）

起因：video-idea 那一路按"扫同类"报了四个页面，**本 Skill 的审阅页不合格**：`boot()` 里 `if(!window.ReviewBridge){…return}` 与 connect 的 catch 都在 `render()` 之前 —— **插件里没桥、或握手不落地时，这一页就是空白**（静态骨架在、动态全空、**零报错**），与用户刚撞到的那次同形。

- **先渲染，再握手**：`boot()` 第一件事是用页面自带的 data 把自己画完（逐页卡 / 导航 / 状态与进度），**然后**才 `connectWithTimeout(BRIDGE_TIMEOUT_MS=2500)`。
- **握手有上限 + 连不上要说话**：不落地就按"没有桥"降级继续，并自述「本页只读 —— 内容可以看，反馈存不进去」（两种原因分开说：没有桥 / 握手未落地）。
- **没有桥时的兜底**：`assetFor` 回退到同源相对地址（无插件宿主下照样看得到图；不透明帧里请求不到，图不出来但不影响文字内容）；`push()`／`refreshStale()`／`readSnapshot()` 在无桥时明说而不静默。
- **本地存储**：本页**没有**顶层 `localStorage`／`sessionStorage` 读取（已用断言钉住，防以后被加回来）。永久「重新加载」出口常驻，不依赖任何告警。
- **判据**：`test_the_page_paints_itself_without_a_bridge`（渲染排第一个 await 之前 / `BRIDGE_TIMEOUT_MS` / `connectWithTimeout` / 出现"只读" / 不裸用本地存储）＋ 浏览器冒烟两条对照：**握手不落地时 rail=2 且自述只读**（绿），**旧写法在同一场景 rail=0、标题与状态皆空**（红，作为常驻对照）。记进 `GOTCHAS.md` G-20。

## 2026-09-26 — v5.5 补丁：重发说"已在路上"；注入点按契约独立成行

- **同一次提交被重发**（宿主报 `duplicate`）：页面不再说"并已通知模型…"，而是照宿主给的那句——「已写入；本次没有新增通知（同一次提交之前已送达）」。规则：**页面说的必须是实际发生了什么**——不把"没法核对"说成成功，也不把"没有新增通知"说得更满。逐页与整套提交都分这一档。
- **注入点按契约改成独立成行**：公共件把 `{{REVIEW_BRIDGE}}` 换成**整段注入**（`base` + `<script src>`，插件则内联桥源码）；页面原来把它塞在 `<script src="{{REVIEW_BRIDGE}}">` 里，整段替换会把标签撑破 → 桥 404、页面连不上（本次被浏览器冒烟当场抓到，代码一行没改就复现）。现在注入点独立成行、只出现一次，测试钉住"不在 `src=` 里"。
- **判活与注入形态解耦**：`host_alive()` 不再逐字节比较"注入点被替换成哪个 URL"，而是比"**注入点以外**逐字节相同 ＋ 注入点确实被换掉了"——否则宿主改一次注入形态就会被误判成"宿主死了"、每次 `review` 都白重启一个新端口。
- 记进 `GOTCHAS.md` G-18／G-19。测试：183 → 183（surface 测试与冒烟的断言换新），全绿。

## 2026-09-26 — v5.5 补丁：页面不再替宿主作它没核过的证

起因：真人使用时页面说「已通知模型」，用户却等不到模型。查下来宿主的**接受**（`write`/`wake` 都 ok）与 agent **看到**（宿主去会话日志里找 `agent/inbox/spliced` 并回 `verified`）是两件事，而页面那句提示把两者抹平了。

- **提示分档**：`review.wake()` 的返回带 `verified` 时 →「宿主已在会话日志里核对进入队列」；**没有时** →「宿主未核对 —— 若模型迟迟没反应，请回对话说一声」。没有插件时宿主（`serve-review.mjs`）不回这个字段，那一档说的就是实情。
- **核验结果入记录**（同一份 payload、同一个 `submitted_at` 的补写，**不是第二轮提交**）：`feedback.json` 的 `provenance.wake = {requested, verified, at}`，将来回看这一轮"通知有没有到"有据可查。补写失败不影响这次提交已经成立。
- 测试：浏览器冒烟两条都钉上——无插件宿主下提示含「宿主未核对」；把 `review.wake` 换成返回 `verified` 的形状后提示含「已在会话日志里核对进入队列」，且 `provenance.wake.verified` 落盘、决定不变。

## 2026-09-26 — v5.5 补丁（纠正意见的生命周期）：改完就结束，人不该回来清自己的意见

起因：用户本人打回——「要我清掉反馈才能通过，这个逻辑就是错的，我都全部批准了说明问题都改完了。**我给你意见，你改完了，就是结束了，这个意见也不该有了。**」

- **`resolve` 即关闭**：解决记录里多一个 `closed: [{page, key}]`，`key` 是该意见的**内容身份**（哪一页 + 那句话说的是什么，`review_feedback.content_key()`；规范化只取会改变含义的东西，所以换行排版骗不过它、换说法天然是新意见）。此后**同页同话不再生成条目**——它是历史（原件在 `history/round-NN.json` 里可回查）。收下时不静默：`consume` 报 `review_intake.suppressed` 并打印原因。
- **"有意见不许批准"只约束人刚写下的新意见**，不约束已经落实的历史：被重出的页初始就是 `pending`、**一次点击即可批准**，不需要清空任何东西；整套提交（含"批准未处理页"）也能覆盖它。
- **整套批准之后没有未决条目**：`items` 为空、`unresolved` 为空，`next` 直接报 `EXPORT`（可以导出）。
- 测试：`test_a_resolved_item_never_comes_back_and_a_new_wording_still_does`（同一句话不再成条目＋换说法仍然是新意见，防过度抑制）、`test_a_whole_deck_approval_leaves_no_items_and_next_can_export`；浏览器冒烟把四条验收都钉上（重出后初始 pending 且一次点击批准 / 整套提交覆盖它 / items 不再含那一页 / 全批准后 next 报 EXPORT）。181 → 183 全绿（2 skipped）。
- 教训并入 `GOTCHAS.md` G-15。

## 2026-09-26 — v5.5 补丁（纠正 B8.2）：上一轮的意见是只读上下文，不是本轮意见

起因：真人审阅把 B8.2 的决定打回了。用户点「整套提交（含批准未处理页）」、唤醒语是「整套已定」，但记录里那一页仍是 `revise`、框选还是**上一轮的原话**、`items` 里多出一条与上一轮完全相同（且已 `resolve` 过）的待办。根因是 B8.2 把上一轮的 `feedback`/`annotations`/`assets` **预填进了参与判定的输入**：同一段字同时是"上一轮我要过什么"与"本轮我有什么意见"，于是页面自己判成 `revise`、整套提交跳过它、管线拿到重复条目。

- **上一轮的东西改成只读上下文**：面板上显示「上一轮你说的（这一页已按它改过；只作参考，不算本轮意见）」——文字、框选、图片改动都列出来，但**不预填进 `feedback`／`annotations`／`assets`**。这类页初始就是「未处理」，**一次点击就能批准**，整套提交也能覆盖它，且**不再产生重复条目**。`previous*` 仍留在页面数据里供追溯。人要接着上一轮的话继续提意见就自己复制过去改——那是新意见，该生成新条目。
- **唤醒语自带决定**（逐页提交用整句覆盖）：要求修改 → 「`<page_key>` 要求修改：<意见要点> —— 只重出这一页，其余页不要动。」；通过 → 「`<page_key>` 已通过。」。以前统一说「X 已定」，人点的是"要求修改"时模型必须先翻文件才知道（实测踩到）。
- **验收钉在哪**：浏览器冒烟三条（重出后初始 `pending` 且一次点击批准 / 整套提交覆盖它 / `items` 不再含那一页）＋ `test_v5.test_a_resolved_round_does_not_come_back_as_a_new_todo`。181 全绿（2 skipped）。
- **教训进 `GOTCHAS.md` G-15**：预填"上一轮的意见"到参与判定的输入里，等于让一句话有两个身份。

## 2026-09-26 — v5.5 补丁（B8.5 前置）：`review` 不再强迫起宿主

起因：Q11 的裁定是**有插件就用插件**，而 `review` 此前总是「生成 + 起无插件宿主 + 开浏览器」——DSH 那条路上会同时挂两套界面，且两边都写同一个 `feedback.json`。

- **新增 `review --surface-only`**（同义别名 `--no-host`）：只做「生成页面 + 写 surface + 校验 surface」，**不起宿主、不开浏览器**，返回 `surface`／`entry`／`feedback_path` 的**绝对路径**与 `host_started: false`，交给宿主的 `review_open` 工具去挂。默认行为不变（没有插件时的那条路）。
- **判据写进文档**（`SKILL.md` ＋ `07_visual_review.md`）：宿主有 `review_open` 工具 → 用 `--surface-only`；没有 → 用不带开关的那条。**这是 Agent 侧一眼可判的事，不需要 Skill 去猜环境。**
- 测试：`test_surface_only_prepares_everything_and_starts_nothing` —— 带开关时 `start_host` 不被调用（所以没有任何端口被占）、不开浏览器、不写 host state／日志、`host_alive` 为 None，报出的 surface 是绝对路径、真实存在、且通过公共件校验器。179 → 180 全绿（2 skipped）。

## 2026-09-26 — v5.5 补丁（B8.4c）：模型改完一页，页面上的图自己换

起因：审阅是**同一页上跨回合**的——人提意见、模型重出一页、人还开着那一页。此前那条链的最后一环是断的：页面的图只在重新加载时才更新，而重新加载会丢人写了一半的意见与框选。公共件新增 `watch`（宿主只 `stat`、变了就戳页面）与 `read()/readText()` 之后，页面可以**自己读快照、自己 diff、只换变了的那几张图**。

- **surface 加 `watch: ["snapshot.json"]`**（相对 surface 文件；即 `_internal/05_review/snapshot.json`）。宿主只看元数据、不看内容，所以"什么变了"仍然由页面自己算。
- **页面接住 `review.on('changed')`**：用 `await review.readText('_internal/05_review/snapshot.json')` 读当前快照 → 找出**版本变过**的页 → 只换它们的 `<img>`（当前页的舞台图 + 轨道缩略图）、把它们的决定退回 `pending`（画面换了，旧批准不算数）、更新内存里的 `review_id`／`version`／`png_sha256`（否则下一次提交会被 Skill 判成上一版）。**不整页重载**：滚动位置、别的页已填的意见与框选、正在编辑的输入框一律不动；被重出的那页显示「这一页的画面已更新…复核后清空即可批准」，轨道上那页的圆点变蓝。
- **新增「变化戳：N 次 · 最后 HH:MM:SS」状态行**（与连接状态放一起）。真人和我们排查「模型改完了但图没变」时有三种可能：宿主没认 `watch`、宿主没推、页面没处理——**没有戳**指向宿主侧，**有戳没换图**指向页面侧。没有这一行就只能猜。
- **上传控件改成按 `review.capabilities` gate**（公共件修掉"对象属性不跟着闭包更新"之后它可靠了）：声明了 `asset-upload` 才显示「新增图片／替换图片」，没声明的宿主整块隐藏；浏览器冒烟加了断言钉住"能力真的交到了页面手里"。
- **整套提交也唤醒**：「整套提交」用 `wake({unit:'整套', text:'整套已定，可以进入下一步。'})` 的**整句覆盖**（surface 的 `wake.text` 是逐页口气，套上去会说成"整套 已定；只重出这一页"）。
- **测试**：浏览器冒烟加了第 ⑤ 步——帧实例标记（证不重载）、换图与 `naturalWidth>0`（证真换）、其他页 `src` 与舞台图不变、别的页的意见/框选原样、换图后对别的页提交**不被判 stale**；并断言 console 里没有"旧拼法"告警（桥以规范拼法 `review/changed` 为准）。踩到的时序坑记进 `GOTCHAS.md` G-14：**戳是变化驱动的，页面加载后的第一个采样周期只建立基准**，测试必须等它落定。
- 测试：179 全绿（2 skipped）＋ 浏览器冒烟绿。

## 2026-09-26 — v5.5 补丁（B8.3）：审阅页接到公共件的缝上（surface ＋ 桥）

起因：审阅页此前由本 Skill 自己用 `review_server.py`（Python HTTP）端出来、自己收反馈。这条缝要复用就得每个 Skill 各写一遍服务器；而人逐页审、模型逐页重出这件事，需要一个能挂进 DSH 侧栏、也能在没有 DSH 时照常跑的公共接缝。公共件 `planners-review-core` 落地后，本 Skill 把这条缝交出去：**页面只留一个桥的注入点，宿主负责显示、serve 资产、落文件、唤醒模型，Skill 只管自己的审阅语义**。

- **新增 `_internal/05_review/review-surface.json`**（`review-surface/2.0.0`）：`id: planners-ppt-hell/visual`、入口 `02_visual_review.html`、反馈文件、`wake: {mode: queue, text: "{unit} 已定；只重出这一页，其余页不要动。"}`、`capabilities: ["asset-upload"]`。**`dir` 取项目根**——审阅页生成在根上，而渲染图在 `_internal/03_png_preview/`、上传件在 `_internal/05_review/uploads/`、页内素材在 `_internal/02_svg_source/` 与 `_internal/00_project/source/assets/`，最近公共祖先是项目根；宿主仍对每个 serve 的路径做 realpath 包含性校验。由 `generate_review_html.generate()` 与页面一起写。
- **页面换成语桥说话。** 入口只留一个**独立成行**的 `{{REVIEW_BRIDGE}}` 注入点（宿主把它换成整段注入 —— URL 或内联源码，由宿主定；**别塞进 `src="…"`**，见 G-18），**不放桥的副本**（插件模式下页面地址是路由，相对引用的副本会 404）。所有资产走 `await review.asset(rel, {v})`（`v` 沿用上一轮的版本语义：页版本 / 素材 sha256 前 12 位），反馈走 `await review.write(整份状态)`，唤醒走 `await review.wake({unit: <page_key>})`，上传走 `await review.upload(file, rel)`。页面里不再有 `/review-asset`、`/review-feedback`、`fetch('/health')` 这些旧接口。
- **提交的语义：逐页提交才是唤醒点。** 「本页要求修改」／「本页通过」= 写整份状态 ＋ `wake({unit: page_key})`（一次只定一页，模型听到的就是"只重出这一页"）；「整套提交」= 只写反馈文件、不唤醒（surface 的唤醒文案是逐页的），人回对话说「已完成」。整份覆盖照旧，所以 `review_id` ＋ 覆盖全部页这条保护不变。
- **降级通道换成公共件**：没有 DSH 时 `python scripts/orchestrate/ppt_pipeline.py <project> review` 起 `node <公共件>/scripts/serve-review.mjs <surface> --port 0`（`scripts/review_surface.py`）。死活判据沿用 P-20(d) 的教训并更进一步：**读回页面本身，且逐字节等于磁盘上那一份入口**（把注入点还原后比对）——端口可能是别人的页面，只有内容能证明它端的是我们的；活着就复用（URL 不变，重出的页按请求读盘），死了就重启。
- **反馈的两端分家，校验搬到 Skill 侧的收件口。** 以前 `review_server` 在提交那一刻校验并写盘；现在宿主原样落盘，所以新增 `review_feedback.consume(root)`：形状校验（决定词汇、区域边界、图片操作、上传件真是图片）、绑定核对（`review_id` 对不上当前快照＝上一轮的）、**规范化写回**（补 items、盖上当前版本与 PNG hash——页面自己写什么都不算数）、**轮次留档**（`history/round-NN.json`，同一提交时刻只留一次）。`next` 每次回来都会收件并把结果报在 `review_intake` 字段里（`feedback` 那个键仍然是 CREATE 分支的"待处理条目"，两个不能同名）。条目 id 优先沿用页面写下的（规范化不能换 id，否则已经跑过的 `resolve` 会变孤儿）。
- **陈旧提交在页面这一侧就被拦住**：提交前拿当前 `snapshot.json` 比 `review_id`，对不上就显示「这一页已更新，先复核：<哪几页>」并且**不写文件**。模型侧第二道是 `consume` 的 `stale`：不算批准、但 items 仍可读。
- **`review_server.py` 只留给模板审阅那条线**（`ppt_pipeline template-review → server(root,'template')` 仍然用它），本轮**没有删也没有改**它；页面审阅的那几条路由（`/review`、`/review-feedback`、`/review-asset`）随之退出运行路径。
- **新增 `scripts/lib/planners_modules.py`**：按名字找公共件（`$PLANNERS_MODULES_HOME` → 兄弟目录 → monorepo 分类目录，与 bypage 的 `planners-modules.mjs` 同一套约定），外加 `node_binary()`——**PATH 里没有 node 是常态**（宿主进程的 PATH 实测是 `/usr/bin:/bin:/usr/sbin:/sbin`），所以要接着找常见位置与 nvm/volta/fnm。
- **跟进（同日，公共件修好 capabilities 之后）**：上传控件改成**按 `review.capabilities` gate**（声明了 `asset-upload` 才显示，没声明的宿主整块隐藏），不再"常驻 + 以拒绝为准"；**整套提交也唤醒**——它用 `wake({unit:'整套', text:'整套已定，可以进入下一步。'})` 的**整句覆盖**（surface 的模板是逐页口气，套上去会说成"整套 已定；只重出这一页"）；`review_server.py` 的三条页面审阅路由加了"已退出运行路径、待模板线 surface 化后清理"的注释（**不删**：迁移永远在删除之后）。
- **文档同步**：`references/workflow/07_visual_review.md`（住 surface／桥／逐页提交／陈旧拦截／收件留档五条）、`references/contracts/project_contract.md`（surface、`review_host.json` 进文件清单；feedback 的写者变了；页面数据字段与三种动作）、`references/architecture.md`（`review_surface`／`lib/planners_modules` 进模块表，`review_server` 降为模板线的宿主）。
- 测试：166 全绿（2 skipped）→ **177 全绿（2 skipped）**。新增：surface 由生成器写出并通过公共件校验器、越界 `dir` 被拒、入口留注入点且不带副本、宿主 serve 时替换注入点（桥本体逐字节等于公共件）、`write` 落文件 ＋ `wake` 带 page_key 落日志、上传落在 dir 内而 `../` 被 403、活着复用／死了重启、端口被占报错而不是端出别人的页面、`host_alive` 拒认不是我们的页面、node 找不到时报错；浏览器冒烟改成驱动新接缝，并在真浏览器里证明①注入点已替换②框选＋逐页提交真的写了文件并唤醒了模型③陈旧页再提交被拒。

## 2026-09-26 — v5.5 补丁（B8.2）：重出一页不丢上一轮的意见

起因：审阅是跨回合的——人写完意见、模型重出一页、人再打开审阅页。`feedback.json` 只有一份且**每次提交整份覆盖**，所以在那条路上，上一轮写在页面上的意见在下一次提交时会静默消失；同时页内素材是**同名原地替换**的，`<img src>` 不带版本时浏览器给的是缓存里的旧图。三处一起补上，未批准页的旧意见从此有一个明确的去处。

- **被重出的页带回上一轮的意见。** `generate_review_html.py` 逐页比对「旧 `feedback.json` 里那条记录的 `version`」与「这一页的当前版本」：变过的页带上 `previousDecision`／`previousFeedback`／`previousAnnotations`／`previousAssets`（新增 `previous_page_feedback()`），版本没变的页不带（它们的批准本来就由 `approvals()` 原样保留）。页面（`assets/review/review.html`）用这四个字段初始化客户端 state——此前是 `feedback:''`、`annotations:[]`、`assets:[]` 全清空——并在页级反馈框上方显示「上一轮的意见（这一页已按它改过，复核后清空即可批准）」。**清空 = 确认，带着提交仍算 `revise`**（`feedback.json` 里非空的意见一律是要求修改，这条规则没变）。
- **整份覆盖之前先留档。** `review_feedback.py` 新增 `archive_round()`：覆盖写 `feedback.json` 前把被覆盖的那一轮原文写到 `_internal/05_review/history/round-NN.json`，轮次顺延、内容与上一份留档相同就不重复写（写法照抄 bypage 的 `review-launcher.mjs`）。提交返回带 `history_path`，`message` 与 `flow_events` 的 `visual_feedback_submitted` 都带上留档位置——留档要**说出来**，不能让人自己发现旧意见去了哪。此前 ppt-hell 完全没有轮次留档。
- **素材图带版本查询串。** `snapshot.json`／审阅页数据里每条素材多一个 `version`（文件 sha256 前 12 位，`asset_records()`）；页面的 `src` 由 `assetSrc()` 生成，形如 `/_internal/05_review/uploads/<page_key>/<file>.png?v=6b619f0a9540`，刚上传/替换的图片用 `/review-asset` 回传的 `sha256` 取同一段前缀。页内素材原地替换之后，页面拿到的是新图，不吃浏览器缓存（页面大图 `png` 字段早就是这个做法）。服务端不用改：它本来就把 query 剥掉后再解析路径。
- **没动的**：`review_id` ＋ `review_current()` 的「必须看过当前版本」保护、提交仍是整份覆盖、批准仍然只认 version 与 png_sha256 都对得上的页（`approvals()`）。
- **文档同步**：`references/contracts/project_contract.md`（`history/round-NN.json` 进文件清单；审阅页每页数据的字段与「清空 = 确认」写进正文）、`references/workflow/07_visual_review.md`（重出后怎么读带回的意见、别把已落实的意见当新要求重复处理）、`references/architecture.md`（审阅面那一行的职责）。
- 测试：162 全绿（2 skipped）→ **166 全绿（2 skipped）**。新增覆盖：重出页带回旧 note／框选、未变页不带旧 note 且仍保留批准、第二轮提交把第一轮留档成 `round-01.json`（且留档的是被覆盖那一轮）、同一份内容不重复留档、素材 `version` 随同名文件内容变化。

## 2026-09-26 — v5.5（两条路线各有各的闸门与终态）

起因：一次视频路线的全链实测（`<项目>/`）暴露出一类共同缺陷——**规则写下来了，但没有东西在产出侧核它**：出口契约要求 SVG 带稳定 `id`、要求作者看过整套画面，代码里却没有任何检查；校验器对文字出画布只给提示级；`inspect` 填三个 `ok` 就能过；视频路线的唯一终态是导出 PPTX；适配器把认不出的字段塞进一个没人读的「待裁决」收集器。本条把「写了但没人核」的地方逐条补上闸门，并按出口把校验器拆成两半。

- **校验器按路线取用。** `validate_svg_layout.py` 新增 `--route {slides,video,auto}`，默认从项目状态读路线。两条路都跑：文字压文字、元素出画布（**含文字**）、空页、`<text>` 缺填色、`font-weight` 非法、图片必须是真实项目内文件且不得被拉伸。只跑幻灯片：字号下限（1px=0.5pt 的幻灯片语义）、禁用元素与属性、`rotate`／`skew`／`matrix`、`tspan` 换行、严格模板锁层。**每条被跳过的检查都写进输出的 `skipped_rules` 并说明原因**，不静默消失。
- **视频出口的文字样式可以从页内 `<style>` 取。** 视频路线按 `03_video_route.md` 把主题的 `:root` token 块内联进每页 `<style>`、元素用 class + `var(--…)` 取值；而校验器此前只认元素自身的 `fill`／`font-family`／`font-weight` 属性，照文档做的 8 屏首跑得到 43 error + 43 warning，只能给每个 `<text>` 手写属性——风格库「改一处、变一套」的价值在校验器面前失效。现在视频路线认三种取法（元素属性、元素 `style="…"`、class 命中的同页 `<style>` 规则，含 `.a, .b` 逗号选择器与 `.card .title` 后代选择器），三处都没有才算缺填色／缺字体；**并且在其中任何一处引用了同页没定义的 token 时报 `UNDEFINED_CSS_VAR`**（点名哪个元素、哪个 token、是哪种取值方式），把「token 拼错＝静默取不到颜色」变成硬错误。幻灯片路线不变：转换器要的是字面属性值。
- **`TEXT_OUTSIDE_CANVAS`（error）。** `<rect>`／`<image>` 早有出画布检查，文字只有一条 info 级安全区提示，于是一个伸出画布 640px 的 72px 标题被判 `pass, errors=0`。现在文字与另外两类共用同一套框计算与 ±5 容差；`OUTSIDE_SAFE_MARGIN` 保持 info（安全区是美术方向，画布不是）。
- **视频出口的可指名性成了闸门。** 出口契约要求「可能被强调的元素带稳定 `id`」（动画层按 id 指名，不用 DOM 序号），此前只有文档在写。现在视频路线上 `<svg>` 之下没有任何元素 `id` 就报 `MISSING_ELEMENT_ID`（error）：根 `<svg>` 的 id、`data-*-id` 属性、注释里的内容都不算数。报错给出下一步——给元素一个稳定 id，然后重渲这一页。幻灯片路线不跑这条（出口差异，不是通用缺陷）。
- **`id` 要整片唯一，不再教「同一族前缀」。** 原来的规则写的是「跨页重复的元素沿用同一族前缀」，那正好制造碰撞：页面会被**内联进同一个 DOM**（一屏一层 `<section class="clip">`），四屏各有一个 `caption-1` 时，全局选择器 `#caption-1` 只命中第一屏——「强调第 4 屏的元素」会静默打到第 1 屏，又一次是票 19 那种静默错绑。规则改为**把 `page_key` 放进 id**（`beat-04-caption-1`），三处措辞同步（`SKILL.md` 责任边界、`03_video_route.md` V2 第 1 条与「页面这一侧的责任」、`04_svg_stage.md` 制作第 5 条），校验器提示也一起改。同时新增 `DUPLICATE_ELEMENT_ID`（error，只跑视频路线）：同一页里同一个 `id` 出现两次即拦，报错说清是哪个 id、重复几次，并给出带 `page_key` 前缀的写法。跨页碰撞不在这里判（一次只读一页），那是导入器在导入前报告的事。
- **`inspect` 长牙。** 新增必填 `--position`（当前 PNG 上的一处坐标或区域，必须落在画布内）与二选一的 `--clean`／`--must-fix`；原来的 `--note`／`--first-glance`／`--design-check` 保留。判据从「三个非空字符串」改成「位置合法 + 显式选了看过有没有缺陷」——填 `ok`／`👀` 不再通过。
- **视频路线的终态不再是 PPTX。** 幻灯片路线保持原样（`final_deck.pptx` 存在且 hash 对得上、导出后复核过）；视频路线的 `COMPLETE` = 全部页面 `check` 无 error **且作者提交过整套审阅**（记录必须覆盖当前页面版本）。这条路上 `final_deck.pptx`、`EXPORT`、`EXPORT_VERIFY` 都不出现，`export`／`export-inspect` 直接拒绝并说明交付物是全部 `_internal/02_svg_source/<page_key>.svg`。审阅在这条路线上是门，`next` 不再提供「直接导出」这个选项。
- **`next` 给动作，不给 errno。** 首屏还没写时以前回的是 `[Errno 2] No such file or directory: …/beat-01.svg`。现在按状态给指令（哪些页还没写、下一步做什么），原始异常只留在 `detail` 里备查。
- **视频路线上 `design_direction.md` 是前置门。** 以前它只是「先写」的建议，而写它会让全部页面版本失效、不写没有任何代价。现在视频路线缺它就 `check` 拦下、`next` 先要它；幻灯片路线保持现状。
- **契约绑定有了核对点。** 项目状态记下路线、`visual-plan.json` 的 sha256 与它声明的 `script_hash`。契约文件变了 → **警告**；声明的 `script_hash` 与**契约旁边那份 `script.md`** 的实际内容不符 → **error**（口播稿改过，画面可能要重画）；真的找不到 `script.md` 时明说「无法核对」，不报成功。核对放在做画面这一步，因为作者是**对着画面录**的，等剪辑接手才发现就只能事后返工。
- **契约绑定每核一项都留一条记录。** 正常状态下 `contract` 是个空数组，与「这一步压根没核」在输出上无法区分，没人敢采信。现在视频路线上 `contract` 永远至少有一条，每条带 `check`（核的是哪一项）与 `level`：`ok`（核过没问题，**正面写出来**）／`warning`（契约文件变过）／`error`（hash 不符）／`unchecked`（没核成，带 `reason`）。核的是 `visual_plan_sha256`、`contract_version`、`script_hash` 三项。**字段缺失才表示这一步没跑。**
- **边界适配器不再制造沉默。** `must_show` 里「文字：」开头的条目是正文，标记剥掉后再进 `content`；`sample.assets[].label` 是审阅页图注，不进 `content`；`content` 按来源（正文／必须出现的内容／原样标签／花字）分组并去掉完全重复的条目（不强制 `exact_labels` 是 `must_show` 的子集）；认不出的契约字段**当场点名打印**（字段名 + 值 + 怎么处理），不再塞进一个全项目没人读的 `notes` 收集器。认不出字段不是硬失败——契约升级加字段不该把这条路打死。
- **`--assets` 的报错改成说清口径。** 「你给的是素材库，交付包是 `<包>/assets/`」+ **明令禁止为过闸删除源素材**；全等检查本身保留（它防的是静默丢图）。三个路径参数的报错都说清它是相对哪个目录解析出来的。初始化按路线打印交付物：视频路线上不打印 `final_deck.pptx`。
- **新增 `scripts/style/theme_tokens.py`**（视频路线的风格库读法）：`list` 报 id／name／nameZh／preview；`show <id>` 把 `tokens.css` 的 `:root` 解析成键值对、**把 `var()` 展开成实际值**，并把**解析不掉的 token 连同缺的那几个名字一起报出来**。目录不写死：`--themes-dir` > `PPT_HELL_THEMES_DIR` > Skill 根的相对位置；找不到时报错说清找过哪里、可以用什么覆盖。
- **审阅服务的死活判断只认 HTTP，不认端口探测。** 服务进程写 pidfile，stdout/stderr 走日志文件；`review` 再调用时**真的 GET 一次页面**，并对照 `/health` 报的 `project_dir` 与 `session_id`——对不上就当没有服务；死了就重启并返回新 URL。保留原有两条：起来先自证、端口被占直接报错退出，绝不端出上一个项目的旧页面。**这条保证的是「本 Skill 不被端口探测骗」**：进程被外部清掉之后，留在那个端口上的 socket 仍可能接受 TCP 连接，`nc -z` 之类会假报 OPEN，而 HTTP 请求拿到的是空响应或 `RemoteDisconnected`——那是外部清进程留下的残迹，不是本 Skill 能修的东西（连接不是它开的）。**端口探测不在本 Skill 的任何判断路径里**；`review_server.find_port` 里那个 `connect_ex` 只用来挑一个还没被占用的端口，与死活判断无关。
- **三个静默缺陷修掉。** `locked_sha256` 在没有 `data-template-lock` 层时改为报错（此前返回空串的 hash，把「锁层丢了」降级成「一致」）；写进 canvas 的 `data-template-canvas-version` 现在被读——检查画面拿页面与 canvas 对照，代数不同即 error；内置模板的 `footer_bar` 声明成 `rect` 而实际是一条 1740×2 的规则线，现改为 `line`（height 0、stroke-width 2），库里的 canvases／components.svg 与 manifest 哈希同步重建。
- **文档与接口同步：** `references/architecture.md`、`README.md`、`SKILL.md`、`references/workflow/` 各阶段文档、`references/domain/` 两份规则按出口拆开，`references/contracts/project_contract.md` 补上 `route`／`visual_plan`／`inspections.json` 的新字段与两个命令的输出。
- 测试：52 全绿（2 skipped）→ **161 全绿（2 skipped）**。新增覆盖：文字出画布、按路线取用规则与跳过原因、视频路线的可指名性与页内 id 唯一、`inspect` 的新判据、视频路线终态不要求 PPTX、内容分组与去重、认不出字段当场点名、风格 token 展开与未解析报告、视频出口的样式表取法与未定义 token、契约绑定三项的 `ok`／`warning`／`error`／`unchecked`、视频路线缺 `design_direction.md`、审阅服务的存活与重启（含「socket 还接受 TCP 但 HTTP 已死」）、内置模板的声明与实物一致。

## 2026-09-25 — v5.4（视频路线：无源文档、无文字屏）

起因：上游把已批准的逐屏画面契约 `visual-plan.json` 5.0 直接交进来（一平铺文件夹的散图就是全部素材），ppt-hell 需要一条没有源文档的入口；同时修掉版本计算对 `source.md` 的硬依赖，并按新裁决允许一屏只有画面、没有文字。上一条 v5.3 是边界解耦，本条是纯新增，两者风险形状不同，所以分开记。

- **新增视频路线入口** `python scripts/init_svg_project.py <project> --assets <图片文件夹> --plan <visual-plan.json>`：没有源文档，不写 `source.md`，底稿由上游契约适配而来。边界上只有**一个**适配器 `adapt_visual_plan` 负责两套词汇之间的翻译——ppt-hell 的核心（状态、校验、审阅、转换）不认识 `visual-plan.json`。`screens[].screen_id` 原样成为 `page_key`（不改名、不重新编号）；上屏内容（`must_show`／`exact_labels`／`sample.captions`）进 `content`，理由与来源（`question`／`must_express`／`evidence`／`beat_id`／样张说明）进 `notes`；图片走同一套共享登记器 `register_image_folder`，未被任何一屏引用的散图点名报错。
- **`page_version` 不再因缺 `source/source.md` 崩溃。** 没有源文时取固定空值；有源文的项目仍是同一个 hash，所以既有页面的 digest 逐字节不变（在真实 21 页项目上核对过）。
- **无文字屏合法。** 一屏可以就是一张画面：`page_content.json` 的 `content` 允许为空（`title` 仍必填），上游适配器也只拦「既无上屏文字、也无登记图片」的空屏。空页判据同步从元素计数（`visible < 3`）改成**既无文字也无图**——元素计数是幻灯片时代的判据，会把「一整屏就是一张图」的合法画面和只有标题的合法页面误报成空页。它仍是告警、不阻断任何流程；同一个定义落在两处：`validate_svg_layout.py`（渲染后）与适配器（契约边界）。
- 测试：32 全绿（2 skipped）→ 48 全绿（2 skipped）→ **52 全绿（2 skipped）**。

## 2026-09-25 — v5.3（能力解耦）

起因：把 ppt-hell 从「一个做 PPT 的流程」收成「一个做视觉画面的 Skill」，让板块之间不再互相搅。本轮只做边界与归属，不重画任何功能；**模板提取子系统按原样封存，未做清理**。

- **「用参考」与「建参考」分开。** 做画面开局直接读风格参考库挑一个（`template_library.py list`／`apply`），不再被八步提取流程当前置；八步提取仍原样打包，只在用户要真实复用自己品牌资产时启动。边界写在 `references/workflow/01_template_intake.md` 与 `04_svg_stage.md`。
- **画幅归一 16:9，归属做画面。** 默认 16:9，开局确认一次；视频不是另一个画幅，而是同一张 16:9 上留一个给人物窗口的排版选择。画幅及其派生度量（含原先住在 `project_state.py` 里的 `1780/1040/1000/986.0/22/200/120`）收进唯一 owner `scripts/canvas_frame.py`，`validate_svg_layout`／`native_svg_to_ppt`／`render_svg_png`／`layout_canvas`／`build_fidelity_template`／`template_visual_gate`／`project_state` 一律从这里取值。
- **检查画面与转换 PPT 共用同一套坐标几何。** 校验器此前自称「mirror 转换器模型」却独立实现，`scale(2) translate(100 50)` 上两者相差 100px。现在 `validate_svg_layout` 直接调用 `native_svg_to_ppt.parse_axis_aligned_transform`／`compose_axis_aligned`，后者也由 `add_elements` 的 `<g>` 递归共用（同一算法的唯一实现）。框计算同步改成转换器的 `offset + x*scale` 形式。
- **检查画面的权威运行点移到导出时。** `export` 先逐页跑一遍，有「转成 PPT 会坏」的错误就拦下不出稿；`check` 里那次保留为提前预警（同一算法，不会再有分歧答案）。
- **导出时提醒审阅。** 未走过整套审阅时，导出返回 `review_reminder`；审阅仍是可选步骤，不是门。
- **删除审批口令要求。** `SECURITY.md` 的 approval key 一节作废（服务器早已丢弃该字段），改述真正在起作用的凭据：审阅握手与产物绑定。
- **状态与版本合一，界面显形。** `project_state.py` 声明 `__all__`，四处 `import *`（`ppt_pipeline`／`review_feedback`／`generate_review_html` 与两个测试）全部改为具名导入；`review_server` 里六个从未使用的投影导入一并清掉。modules 不再从它里面随便拿东西。
- **模板审阅拿到「必须看过当前版本」保护。** 生成审阅页时写 `template_review_snapshot.json`（review_id + template_version + 审阅页 hash + layout 集合），提交必须带当前 `review_id`；Server 与 `template_library.require_approved_feedback` 都对照快照，旧标签页不能批准新版本。**两个审阅页仍然分开**——它们是两个主体。
- **两个自检的判据写明不同。** 逐页审阅问「这个 PPT 做得好不好」，模板审阅问「有没有提炼出足够模板规律」（`template_visual_gate.py`、两份 workflow 文档）。
- **退役两条旧规则。** 「整页位图不算页面／元素必须是原生文本与图形」删除（画面本来就是真的 SVG）；测试里 `export` 必须抛 `ValueError('human review')` 的断言删除——该门是有意移除的，测试是旧规则的遗留，改为钉住「未审阅也导出 + 返回提醒」。`template_feedback.json` 与 `template_review_snapshot.json` 补进 `project_contract.md` 与 `template_package.md` 两份机器接口清单。
- 测试：30 条（1 条已红）→ **32 条全绿，2 skipped**。

## 2026-09-13 — v5.2.1（描边保真修复）

起因：一次 21 页实测（项目在 `01-projects/Adidas-vs-Nike-WorldCup2026/04_PPT/`）导出后发现某页坐标轴线在 PPTX 里整条消失。逐像素对照才定位到 `native_svg_to_ppt.py` 的描边换算。

- **删掉描边上的 `* 0.6` 经验系数**。`shape.line.width = Pt(sw * FONT_SCALE * 0.6)` 让每根描边只有声明值的 60%（1920 画布上 1px → 0.30pt）。这与本 Skill 自己写死的规则直接矛盾：`reference/domain/svg_rules.md` 第 5 行明确「1 SVG px = 0.5pt」。更严重的是，批准稿 PNG 由 Chromium 按 SVG 声明的满权重渲染，所以这个系数让「导出稿与批准稿一致」这个 EXPORT_VERIFY 目标在数学上永远无法达成，且失败是静默的（细线只是不画出来）。
- **新增低于 `MIN_STROKE_PT`（0.5pt）时的告警**，把静默失败变成构建期提示。阈值判断留 1e-4 余量：`SLIDE_W_IN` 是 13⅓ 的近似值，1px 实际换算为 0.49999pt，不留余量会把合法发丝线全部误报。
- **补上 `scripts/test/test_converter_geometry.py` 的 3 条回归**：描边不得被额外缩放（EMU 整数比对）、1px 不得被判过细、低于 0.5pt 必须告警。
- **给另两个魔法系数补上来源与影响边界**：`estimate_text_width` 的 0.58 与文本落位的 0.85。核实结论是两者都**不影响最终视觉位置**（三种框内对齐各自自我抵消；0.85 只造成整页统一的轻微垂直偏移），因此不做替换，只写明"要精确就按实际字体取度量，不要再叠系数"。

未处理并已登记的既有失败：`test_source_assets.py` 的 `soffice --convert-to doc` 在本机失败，在未改动的副本上同样失败，属环境问题，与本次改动无关。

## 2026-09-12 — v5.2（模板流程补全与自检落地）

v5.1 之后用户指出两件事：**视觉自检没有被真正执行**，以及**模板提取与使用流程没有出现在活跃文档里**。核实结果：机械全在（八步提取脚本、模板库、canvas 实例化），但 `01_template_intake.md` 只有 9 行存根、把流程推给 `--help` 和 contract；`--mode reference` 只登记一个字段、不渲染任何参考件；自主路径从不告知模板库存在。

- **`01_template_intake.md` 从 9 行存根写成完整流程**：四条路线（自主／库模板／视觉参考／新建严格品牌模板）+ 每条的精确命令、产物、决策点与完成标准。八步提取流程从 contract 提到 workflow 层，contract 仍为机器接口。
- **视觉来源改为内容底稿后一次性确认**，不再静默默认自主设计（`00_pipeline_controller.md`、`SKILL.md`）。
- **`template --mode reference` 需要 `--reference <文件>`**，会真正调用 `prepare_visual_references.py` 渲染参考页；没有参考件直接报错。此前该模式只写 manifest 字段，参考路线在机械上是空的。
- **自检从「5 个问题」扩到覆盖 13 条规则**，并落地为必填产物：`inspect` 新增 `--first-glance`（第一眼落在哪）与 `--design-check`（对照了哪几条规则、有无违规），两者空着不通过。此前 `inspect` 只收自由文本，自检可被跳过——而它确实被跳过了。
- **`check` 每页回一组只读测量**：字号档位、最大／最小尺度比、等面积容器组、内容底部到页脚线的空档、跨页共用基线。**只报告，不判 pass/fail**，用来替代「凭印象自检」。

## 2026-09-12 — v5.1（实测后的能力重划）

起因：v5 用老的美津浓文案做了 10 页完整实测（项目在 `07-SkillLab/PPT-Skill-around/PPTTest1/mizuno-v5-test-20260912/`，报告在同目录 `skill-run-reviews/`）。工程全绿，但视觉明显不如人做的提案；差异不在字数（每页 18.6 vs 19 个文字 run），而在设计自由度。据此重划机械与设计的边界。

- **校验器从 1383 行降到 563 行。** 只保留「转成 PPT 会坏」和「任何风格下都是缺陷」两类检查；退役全部可读性／密度／构成启发式，以及页面 metadata 概念与 `REPEATED_LAYOUT_RHYTHM` 死代码。
- **新增每页读法声明 `mode`（`讲`／`读`）。** 它唯一影响的技术量是字号下限（`讲` ≥18px、`读` ≥12px），其余是设计判断的输入。这是每页一个字段的声明，替代原来那批全局硬阈值。
- **修三个真 bug**：`estimate_text_box` 忽略 `text-anchor`（右对齐／居中文字必然误报越界，且有变成假 error 的风险——实测两轮共 20 个假警告）；`check` 对未变页面不回 `issues`（全量扫描看不到告警分布）；`check_rhythm` 依赖无人写入的 metadata。
- **`style_system.md` 从「克制建议」换成设计总规则。** 13 条正面规则 + 元规则（先声明读法）+ 迁移边界，全部停在「韵律／网格／视觉重心」这一层，不写字号、颜色、组件。依据是一份带 A/B/C/D 证据分级的文献提炼（`07-SkillLab/PPT-Skill-around/planners-ppt-hell-upgrade-20260912/design-principles-research.md`）。其中 W3C clreq／jlreq 为 A 级，给出中文版面以字面方块为网格单位的规范依据；Gestalt 原始文献未核实，相关表述已撤下。
- **内容阶段增加一次图片询问**：判断这套页面是否需要配图，一次性说明需要什么、哪几页、用户是否已有资产；不逐页追问，无图时在底稿写明原因。
- **`svg_rules.md` 写明 px↔pt 换算（1px = 0.5pt）与纵向步长构造。**

## 2026-09-12 — v5

- 轻量内容底稿＋主 Agent 自主设计，合并 Layout 与 SVG 创作。
- 删除 Layout 审阅、scaffold、wireframe 契约和旧 task/finalize 调度；取消强制子 Agent 与批次配额。
- 实际页面审阅支持上传、新增、替换、裁剪和区域反馈；反馈统一返回创作。
- 每页版本绑定源内容、SVG、真实图片和视觉方向；检查缓存、旧审批失效、稳定页批准复用。
- 保留源资产提取、严格品牌模板、原生转换和严格缺图；最终 PPTX 渲染复核单独记录。
- 工程回归与实际语义测试分开；用户选择在其他任务做真实测试，本次不将其标为已通过。


## 2026-07-18 — historical release

- 支持启动时明确选择默认模板、上传提取新模板或无模板。
- 新模板逐 Layout 审阅：通过、舍弃、返修；保留单独反馈、整体反馈和模板命名。
- Template canvas 只固定视觉身份与页面边界，replace layer 保持为空。
- Layout 独占结构、最终文案、wireframe 与 canvas 选择；无精确匹配时使用 `content_base`。
- SVG task 缩减为当前 batch 的已选 canvas、最小运行时、批准文案与 wireframe。
- 移除持久 Parent/Worker 会话编排；Template、Content、Layout 由当前 Agent 串行执行，SVG batch 只保留一次性并发能力。
- 返修任务改用冻结的旧产物快照，消除输入/输出同路径导致的 stale 循环。
- 阶段完成绑定当前 task hash 和当前输出 hash；重复 SVG finalize 在证据仍有效时幂等返回。
- 增加 wireframe 结构执行追踪，但不新增视觉质量判断或强化视觉流程门禁。

