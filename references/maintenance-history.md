# 维护历史：升级记在这里

**这里装升级**：一次改动做了什么、为什么、影响了哪些 module、删了什么。给**改它的人**读——发布视角（对外逐项对账）看 `CHANGELOG.md`；同一件事两边都出现时，这里只留**维护要用的那几面**（边界怎么变、动了哪些 module、删了什么）。候选（还没升级的）在 `GOTCHAS.md`。

看每一条时问三件事：**边界怎么变了**、**哪些 module 被牵动**、**删掉了什么**。

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
