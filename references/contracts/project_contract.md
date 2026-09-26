# 机器接口

这些文件只服务真实消费者，不是设计思考问卷。

**页面审阅**与**模板审阅**是两个主体，各有自己的文件；下表两者都列，但不要把它们当成同一份接口的两种形状。

| 文件 | 写者 → 消费者 | 最小职责 |
|---|---|---|
| source/source_assets.json | 素材脚本 → 底稿、检查 | 资产 ID、路径、源上下文 |
| page_content.json | 模型 → 索引、制作、notes 导出 | project、pages[{page_key,mode?,title,content,source_assets?,notes?}]、unused_assets?；`content` 是上屏内容本身（按来源分组、去重），`notes` 只放理由与追溯 |
| design_direction.md | 模型 → 跨页制作、版本检查 | 这套页面共同视觉决定：网格与纵向步长、层级角色、色彩角色、跨页锚点、节奏；**视频路线上缺它 `check` 拦下** |
| page_manifest.json | Controller → Server、渲染 | v5 版本、**route（`slides`／`video`）**、**visual_plan（契约路径 + sha256 + 声明的 script_hash）**、页序与路径、每页 mode、模板模式 |
| 每页 validation JSON | check → inspect、Review | 实际输入版本、PNG hash、技术报告（含本页 `route` 与被跳过的规则及原因） |
| inspections.json | inspect → Review | render token、具体观察、**position（当前 PNG 上落在画布内的一处位置）**、**verdict（`clean`／`must_fix`）** |
| snapshot.json | 页面审阅生成器 → 页面（经宿主）、`consume` | review_id、HTML、页面及PNG版本、实际图片集合（每条素材带 `version`＝文件 sha256 前 12 位，页内素材原地替换时靠它破缓存）；页面提交前拿它比 `review_id` 判断自己是不是过期 |
| review-surface.json | 页面审阅生成器 → **宿主**（DSH 插件 / `serve-review.mjs`） | `review-surface/2.0.0` 契约：页面入口、被 serve 的 `dir`、反馈文件、唤醒文案（`wake.mode/text`）、能力（`asset-upload`）、`watch`（宿主只 stat 它们的 mtime/size，一变就戳页面；本 Skill 指 `snapshot.json`）。**不含审阅语义**（审什么、能下什么决定、怎么绑版本） |
| `template-review-surface.json` | 生成审阅页那一步写下（`_internal/00_project/`） | 模板审阅面的声明：`id` `planners-ppt-hell/template`、入口 `00_template_review.html`、`feedback` 与其同目录的 `template_feedback.json`、`watch` 盯 `template_review_snapshot.json`、**不声明上传能力** |
| template_feedback.json | **页面（经宿主原样落盘）→ `template_feedback.consume` 校验并重算 → `template_library.publish`** | 逐 Layout 决定（`pass`/`discard`/`revise` + 单独反馈）、整批动作（`submit_batch`/`approve_all`）、整体反馈与模板命名；派生量（`approved`/`discarded_layouts`/`revision_layouts`）与绑定摘要（审阅页 HTML、源模板渲染页、模板包的 sha256）**由 Skill 收件时盖章**，页面写什么都不算数 |
| feedback.json | **页面（经宿主原样落盘）→ `consume` 规范化 → 创作、导出** | 页级决定、区域、资产修改、全部反馈 items 与 provenance；每次提交**整份覆盖**，所以它始终是「当前这一轮」。写的人是页面，不是本 Skill 的服务器；`provenance.source` 为 `review_page`（`review_server` 的旧项目仍读得懂） |
| history/round-NN.json | `consume` → 创作、回查 | **每一轮被模型读到的** feedback.json 原文（轮次顺延，不覆盖历史）。提交是整份覆盖，回查上一轮提过什么只能读它 |
| review_host.json | `review_surface` → `review` 命令 | 无插件宿主的 pid/port/url/surface/log；死活判据是"读回页面且逐字节等于磁盘上那一份入口"，不是端口探测 |
| resolutions.json | resolve → Review | 反馈 ID 与实际解决说明 |
| **template_review_snapshot.json** | **模板审阅生成器 → Server、模板发布** | **review_id、生成时的 template_version、审阅页 HTML hash、被审的 layout 集合** |
| **template_feedback.json** | **Server → 模板发布（`template_library.py publish`）** | **逐 layout 决定、模板命名、整体反馈与 provenance；它是模板发布的唯一批准凭据** |
| export.json | Controller → 完成状态 | PPTX 与页面版本、实际渲染检查证据、`review_reminder`（未审过时）；**视频路线不写它——那条路不导出 PPTX** |

`review` 的输出也是接口，消费方是 Agent：默认那条报 `url`／`started`／`reused`／`host_state`（起了无插件宿主）；`--surface-only`（别名 `--no-host`）那条报 `surface`／`entry`／`feedback_path` 的**绝对路径**与 `host_started: false`，由宿主的 `review_open` 工具去挂这个面。**判据是"宿主有没有那个工具"**，不是环境探测。

`next` 与 `check` 的输出也是接口，消费方是模型：`next` 回状态、还没写哪些页、契约绑定有没有漂移，以及 **`review_intake`（这一轮绑的是不是当前这一版、留档到哪、形状对不对；`_next_action` 的 `feedback` 仍然是"待处理条目"）**；`check` 回 `route`、`contract`、每页结果，以及**被跳过的规则和它们为什么被跳过**。`contract` 里每条记录都带 `check` 与 `level`（`ok`／`warning`／`error`／`unchecked`）：视频路线上它**永远至少有一条**，`ok` 也显式写出来——只有字段缺失才表示这一步没跑。

page_key 为稳定的字母开头标识，后续为字母数字、短横线或下划线；顺序由 pages 数组确定。不是连续页码，也不是 batch ID。

**审阅页的每页数据**（`02_visual_review.html` 里那份 `const data={…}`，由 `generate_review_html.py` 生成）逐页给：`key`、`title`、`png`（**相对 `dir` 的路径**，页面向桥要 URL 时带上 `version`）、`version`／`png_sha256`（页面写反馈时要盖章）、`assets`（每条带 `version`）、`previous`（上一版 PNG 的相对路径，用于对照）、`decision`，以及**只在「这一页在反馈之后被重出过」时才出现的** `previousDecision`／`previousFeedback`／`previousAnnotations`／`previousAssets`——上一轮的意见原文。它必须带回来：`feedback.json` 是整份覆盖的，不带回页面就等于「人写的意见在下一轮消失」。页面把带回来的东西显示成「上一轮你说的（这一页已按它改过；只作参考，不算本轮意见）」——**只读**：不预填进 `feedback`／`annotations`／`assets`。所以这类页初始是 `pending`、一次点击即可批准，整套提交也能覆盖它；不会因此再生一条与上一轮相同的待办。**判定输入里只有"本轮的意见"这一种身份**（预填会把两种身份混在一起，2026-09-26 被真人使用打回）。版本没变的页面不带这些字段——它们的批准由 `approvals()` 原样保留。

**条目的关闭（生命周期）**：`resolutions.json` 的每条解决记录带 `closed: [{page, key}]`——`key` 是该意见的**内容身份**（哪一页 + 那句话说的是什么，见 `review_feedback.content_key()`）。`consume` 收件时跳过已经关闭的（同页同话不再生成条目），并把它们报在 `review_intake.suppressed` 里。**换了说法就是新意见**，照常生成条目。

`provenance.wake`（可选）：`{requested, verified, at}`——这次提交有没有请求唤醒、宿主的核验结果（插件宿主会去会话日志里核对并回 `{where, seq, target, requestId, equalsWakeText}`；无插件宿主不回，页面据此说"宿主未核对"）。补写这一步用**同一份 payload、同一个 `submitted_at`**，所以它不是第二轮提交、也不改变任何决定。

逐页提交的 `wake` 用**整句覆盖**：`{unit:'<page_key>', text:'<page_key> 要求修改：<要点> —— 只重出这一页，其余页不要动。'}` 或 `{unit:'<page_key>', text:'<page_key> 已通过。'}`；surface 的 `wake.text` 模板只留给不覆盖的调用方。

**页面的启动顺序是契约的一部分**：先渲染（只用自带 data）→ 再握手（`BRIDGE_TIMEOUT_MS` 上限）→ 连不上就自述"只读"。理由：不透明源 iframe 里顶层读 `localStorage` 会直接抛、整页脚本当场死且**零报错**；而把渲染挂在握手后面，握手不落地时页面同样空白。**桥是增强，不是氧气。**

**页面与宿主之间只有三种动作**（`review-surface/2.0.0`，由公共件 `planners-review-core` 提供）：`await review.asset(rel,{v})` 取资产 URL（有插件时是帧内 blob，无插件时是相对地址，两部分支都在桥里）、`await review.write(整份状态)` 落反馈文件、`await review.wake({unit: <page_key>})`（逐页：宿主用 surface 的 `wake.text` 替换 `{unit}`）或 `await review.wake({unit:'整套', text: <整句>})`（**整句覆盖**：整套提交用，surface 的模板是逐页口气，套上去会自相矛盾）唤醒模型。页面里**不放桥的副本**：入口只留一个**独立成行**的 `{{REVIEW_BRIDGE}}` 注入点，宿主 serve 时把**整段**换进去（无插件宿主给 `base` + `<script src>`，插件内联桥源码 —— 换成什么由宿主定）。注入点**不能塞进 `src="…"`**：整段替换会把标签撑破、桥 404（G-18，实测踩过）。资产路径一律相对 `dir`（本 Skill 取项目根，因为审阅页在根上而渲染图/上传件/素材分别在 `_internal` 的几处）。**上传控件按 `review.capabilities` 显示**：surface 声明了 `asset-upload` 才有「新增图片／替换图片」；没声明的宿主下整块隐藏。

**收到变化戳之后页面做什么**（`review.on('changed')`）：宿主只知道"`watch` 的文件元数据变了"，不知道变的是什么，所以页面用 `review.readText('_internal/05_review/snapshot.json')` 自己读、自己 diff —— 版本变过的页换掉 `<img>`、决定退回 `pending`、内存里的 `review_id`/`version`/`png_sha256` 跟着更新（否则下一次提交会被判上一版）。**不整页重载**：滚动、别的页的意见与框选、正在编辑的输入框都不动。面板上的「变化戳：N 次 · 最后 HH:MM:SS」就是给"模型改完了但图没变"这个问题用的：**没有戳**＝宿主没推，**有戳没换图**＝页面这一侧。

`mode` 是每页的读法声明，只接受 `讲` 或 `读`；缺失按 `读` 处理。它唯一影响的技术量是字号下限（`讲` ≥18px，`读` ≥12px），其余是设计判断的输入。它**不是**布局类型、密度或视觉风格枚举。

模型直接写底稿、方向与 SVG，其余通过命令写。Controller 计算时间和 hash。脚本能证明文件一致、缺图与技术错误，**不能**证明视觉检查真实发生、设计是否成立或商业判断是否正确——样式类启发式已从校验器移除，那部分判断归模型看图与人审。
