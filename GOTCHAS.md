# GOTCHAS —— 候选

**这里装候选**：有证据的、会稳定导致错误的具体行为。**升级**（已经改动 Skill 的那些）记在 `references/maintenance-history.md`；两个文件分开放的理由见 `references/architecture.md` 结尾。

每条只保留五件事 + 它属于哪个 module：现象／原因／行为修正／证据／状态（`候选` · `已复现` · `已升级` · `已失效`）。

按 module 聚类，方便一起改——不按发生次数堆规则。**证据不足的不要写进来**：抄不出报告条目号、票号或 `文件:行` 的，说明它还没被复现。

新增之前先看同义项，合并而不是追加。

---

## 一、动画缝（本 Skill → `video-craft`）

### G-01 交给下游的元素命名没有被任何东西核

- **module**：`scripts/validate_svg_layout.py`（规则）＋ `references/workflow/03_video_route.md`、`04_svg_stage.md`、`SKILL.md`（措辞）
- **现象**：三种形态，同一根因——
  ① 页面里**一个元素 id 都没有**，动画层只能按 DOM 序号指（实测 44 张真实页面 **0 个 id**）；
  ② 按**DOM 序号**指元素：重渲时多出一个 `<text>`，序号整体后移，指到别的东西上，**不报错**；
  ③ 每屏都叫 `caption-1`：各屏被内联进**同一个 DOM** 后，全局选择器 `#caption-1` 只命中**第一个**——想强调第 4 屏，实际打到第 1 屏（`hyperframes check` 的对比度警告把 `#caption-1` 对到了落在第 3 屏的 `t=11.556s`，就是这个碰撞的旁证）。
- **原因**：出口契约把「按 id 指名」写成了下游的责任，产出侧**没有任何东西检查 id 存不存在、唯不唯一**；文档还教「跨页重复的元素沿用同一族前缀」，等于主动制造 ③。
- **行为修正**：文案与规则都改成「把 `page_key` 放进 id、全片唯一」（`beat-04-caption-1`），保留「用 id 不用 DOM 序号」与「名字要读得出它在画面里是什么」。产出侧两条闸门：`MISSING_ELEMENT_ID`（没有可指名的元素）与 `DUPLICATE_ELEMENT_ID`（页内 id 不唯一，**含根 `<svg>` 的 id**）。跨页碰撞不在这里判（一次只读一页），由导入器在导入前报告。
- **证据**：`.scratch/matt-pocock-video/issues/19-svg-page-animation.md`（44 页 0 id；序号静默错绑的实测）；`05-VideoProject/06-测试-Vans-20260926/_测试报告.md` §11.2（4 屏 55 个 id 全按 id 指名、`hyperframes check` passed）与 §11.4（`#caption-1` 被当成全片唯一）。
- **状态**：已升级（v5.5）

---

## 二、边界适配（`scripts/init_svg_project.py`）

### G-02 「不是给屏幕看的文字」被原样搬进上屏内容

- **module**：`scripts/init_svg_project.py` 的 `adapt_visual_plan`／`_asset_reference`
- **现象**：① `sample.assets[].label` 是**审阅页的图注**（`<figcaption>`），不属于 `must_show`／`exact_labels`／`captions` 任何一类声明，却被当成上屏内容；于是一道**无文字屏**在审阅页上看起来有字，而上游、ppt-hell、`video-craft` 三处都不认为那是字（一把**没有 owner 的字**）。② `must_show` 里以「文字：」开头的条目，标记本身被连正文一起写进 `content`——一个会照抄的消费者会把「文字：」画上屏。
- **原因**：适配器按「字符串列表」处理所有字段，**没有区分这条文字的读者是谁**（上屏观众 / 审阅页的人 / 契约的阅读者）。
- **行为修正**：`label` 只进 `notes`（写成「审阅页图注：…」），绝不进 `content`；「文字：」是契约的标记，剥掉后按**正文**归类；`content` 按来源分组（`【正文】【必须出现的内容】【原样标签】【花字】`）并去掉完全重复的条目，让做画面看得出哪条来自哪一类。
- **证据**：报告 P-07（审阅页把 label 画成看得见的字）、P-11（`content` 里带「文字：」且同一信息出现两遍）。
- **状态**：已升级（v5.5）

### G-03 报错只说「你错了」，不说正确做法 → 人会走破坏性捷径

- **module**：`scripts/init_svg_project.py`（`--assets` 与三个路径参数的报错）
- **现象**：`--assets` 指到作者的素材库时，报错是「这些图在文件夹里但没有任何一屏引用它们」。照它做的人最省事的解法是**去删源目录里的多余图片**——而那里正是作者的材料（本工作区刚丢过 6.9 GB 的那类操作）。
- **原因**：报错回答的是「检查没过」，没有回答「正确做法是什么」；`--assets`／`--plan`／`<project>` 三个路径参数也没说清**相对路径是按哪个目录解析的**，于是报错里那个拼出来的路径看起来像「作者的图片目录不存在」。
- **行为修正**：报错里写清「你给的是素材库，交付包是 `<包>/assets/`」＋「禁止为了通过这道检查去删除源素材」；全等检查本身保留（它防的是静默丢图）。路径类报错的末尾附上「相对路径按当前工作目录解析 + 当前工作目录绝对值 + 三个路径都给绝对路径最省事」。
- **证据**：报告 P-02（诱导破坏性操作）、P-03（报错指向一个不存在的路径）。
- **状态**：已升级（v5.5）

### G-04 只进不出的收集器

- **module**：`scripts/init_svg_project.py` 的 `adapt_visual_plan`
- **现象**：认不出的契约字段被 JSON 化塞进 `notes` 的「未映射字段（原样保留，待裁决）」。全项目**没有任何脚本或文档读它**（`notes` 只被写进 PPTX 的 speaker notes），契约升级时新增的字段会静默沉底。
- **原因**：写者给自己找了个「先留着」的出口，但没有指定消费者——按 `references/architecture.md` 的自查，这就是「Active 路径上没有消费者的字段」。
- **行为修正**：认不出的字段**当场点名打印**（字段名 + 值 + 怎么处理），不进 `notes`、不进 `content`；**不做成硬失败**（契约升级加字段不该把这条路打死）。契约根部的字段只报一次，不跟着每一屏重复。
- **证据**：报告 P-08。
- **状态**：已升级（v5.5）

---

## 三、检查画面（`scripts/validate_svg_layout.py`）

### G-05 同一类缺陷只在一半对象上实现了

- **module**：`scripts/validate_svg_layout.py`
- **现象**：`<rect>` 有 `ELEMENT_OUTSIDE_CANVAS`、`<image>` 有 `IMAGE_OUTSIDE_CANVAS`，而 `<text>` 只有一条 **info** 级的安全区提示。实测：72px 的中文标题挪到 `x=1700`，文字伸出画布 640px，校验器判 `pass, errors=0`；同一份真实项目里 `beat-03` 的右行文字真被切掉，`check` 也是 pass。
- **原因**：「元素不许出画布」这条规则被**逐个元素类型各写一遍**，第三类漏了；而漏掉的那一类恰好是最常见的（文字）。
- **行为修正**：三类共用同一套框计算与同一个 ±5 容差（`outside_canvas`）；`TEXT_OUTSIDE_CANVAS` 是 error。安全区（`OUTSIDE_SAFE_MARGIN`）**保持 info**——安全区是美术方向，画布不是。
- **证据**：报告 P-05。
- **状态**：已升级（v5.5）

### G-06 同一个概念，两个地方各有一套判据

- **module**：`scripts/validate_svg_layout.py` ↔ `references/domain/svg_rules.md` / `03_video_route.md`（风格 token 的落地方式）
- **现象**：文档教「把主题的 `:root` token 块内联进每页 `<style>`，元素用 `var(--…)` 取值」，而校验器只认元素自身的 `fill`／`font-family`／`font-weight` 属性。照文档做的 8 屏首跑得到 **43 error + 43 warning**，只能给每个 `<text>` 手写属性——风格库「改一处、变一套」的价值在校验器面前失效。反向的漏洞同时存在：**token 拼错**时浏览器静默取不到颜色，也没人报。
- **原因**：同一条要求（「文字要有明确的颜色与字体」）在两个 module 里各有一套判据，谁也不知道对方怎么看。
- **行为修正**：视频路线上认三种取法（元素属性、元素 `style="…"`、class 命中的**同页** `<style>` 规则，含 `.a, .b` 与 `.card .title`），三处都没有才算缺；引用了同页没定义的 token 报 `UNDEFINED_CSS_VAR`（error，**写回退值也拦**——回退值让它看起来正常，但换主题时这一处不会跟着变）。幻灯片路线不变（转换器要字面属性值）。选择器只认**由 class 组成的简单／后代选择器**，其余一律不算数（宁可要求显式属性，也不误判成「取到了」）。
- **证据**：报告 P-22；`03_video_route.md:41`（落地方式）与旧 `validate_svg_layout.py` 的 `# ── Text: explicit fill / family / weight (both routes) ──`。
- **状态**：已升级（v5.5）

---

## 四、控制面、状态与审阅缝（`ppt_pipeline` ＋ `project_state` ＋ `review_surface`）

### G-07 闸门的判据可以被任意字符串满足

- **module**：`scripts/orchestrate/ppt_pipeline.py` 的 `inspect` ＋ `scripts/project_state.py` 的 `inspected`
- **现象**：`inspect`（「这一页我看过了」）只要求三个字段非空。`--note ok --first-glance ok --design-check ok` 通过，`👀 👀 👀` 也通过。更要紧的是它**分不清「看过了没问题」和「看过了有问题但我不标」**：老实写下缺陷、不带 `--must-fix`，照样 `inspected: true`。实测案例：8 屏里真正单独打开大图的只有 5 张，另外 3 张是从**联系表缩略格**上看的，记录里一样写着「看过了」。
- **原因**：判据是「写了字」而不是「写了可被证伪的内容」；没有任何东西要求记录指向**这一版**的具体一处。
- **行为修正**：`--position` 必填且必须落在画布内（「我看的是哪里」）；`--clean`／`--must-fix` 二选一必给（「看过有没有缺陷」）；报错文案写明「看的是每页 PNG 大图，不是联系表里的缩略格」。三个自由文本字段保留。
- **证据**：报告 P-06 与 P-20(a)。
- **状态**：已升级（v5.5）

### G-08 契约声明了一个 hash，而没有任何消费者核它

- **module**：`scripts/project_state.py` 的 `contract_binding` ＋ `references/contracts/project_contract.md`
- **现象**：`visual-plan.json` 里 `script_hash` 是必填，ppt-hell 只把它抄进 `notes` 的字符串，不校验。画面做完之后稿子改了，**不会有任何反应**；而作者是**对着画面录**的，等剪辑那一步才发现就只能事后返工。
- **原因**：声明与核对分在两个 Skill，谁也没把「核对」当成自己那一步的产物；而且核对结果**没有正面记录**——正常状态是一个空数组，与「这一步压根没跑」在输出上一样，所以没人敢采信。
- **行为修正**：顺着**契约文件所在目录**找 `script.md` 并核对；不符 → `error`（画面可能要重画）、契约文件变过 → `warning`、真的找不到 → `unchecked` 并带 `reason`。每核一项留一条记录（`check` ＋ `level`），视频路线上**永远至少一条**，`ok` 也显式写出来；**字段缺失才表示这一步没跑**。**核哈希不等于把口播当输入**：口播不用来判断画面内容，那份 `script.md` 只用于版本绑定。
- **证据**：报告 P-12 与 §9.1。
- **状态**：已升级（v5.5）

### G-09 用传输层探测判断应用层死活

- **module**：`scripts/orchestrate/ppt_pipeline.py` 的 `server_alive`／`start_server`（模板审阅那条线）＋ `scripts/review_surface.py` 的 `host_alive`（页面审阅，2026-09-26 换宿主后重落一次）
- **现象**：`review` 用 `subprocess.Popen(..., start_new_session=True)` 起审阅服务，服务在那次工具调用结束后**又死了**；而 `nc -z <port>` 仍报 **OPEN**（那个端口上的 socket 还接受 TCP），`curl`／`urllib` 拿到的才是真的（空响应／`RemoteDisconnected`）。作者回到对话准备写意见时，页面已经在空转。
- **原因**：用 `nc`／端口探测判断「服务活着吗」——它只回答 TCP 握手，不回答 HTTP。审阅是**跨回合**的，这个判断错了代价就是白等一轮。
- **行为修正**：判断死活一律**真的 GET 一次页面**（`/review` 返回 200 且有内容）＋ `/health` 报的 `project_dir` 与 `session_id` 对得上；对不上就当没有服务，死了就重启并返回新 URL。**端口探测不在任何判断路径里**（`review_server.find_port` 里那个 `connect_ex` 只用来挑空闲端口）。同时：进程写 pidfile、日志走文件（不挂在父进程管道上）、起来先自证、端口被占直接报错退出。
- **证据**：报告 P-20(d) 与 P-23；`curl` 与 `urllib` 在活/死两种状态下的对照实测（v5.5 维护记录）。页面审阅换宿主后（v5.5 补丁 B8.3）这条规则在 `host_alive` 上再落一次，并且**再加一条**：端口可能已经不是我们的宿主了（上个会话、别的项目），所以判据是"读回的页面逐字节等于磁盘上那一份入口（注入点还原后比对）"——只有内容能证明它端的是我们的页面。
- **状态**：已升级（v5.5）

### G-10 文档写明的前置步骤，没有任何东西检查它发生

- **module**：`scripts/orchestrate/ppt_pipeline.py` 的 `require_direction` ＋ `references/workflow/03_video_route.md`
- **现象**：`04_svg_stage.md` 说 `design_direction.md` 是「动手前的前置」，但**没有任何闸门要求它存在**：不写也全过（8 屏照样 `check` 全过、`export` 成功）；而写它会让**全部页面版本失效**（进 `page_version`），等于让页面重做。于是「省它没有任何代价」，而视频路线最需要的四条约束（字幕安全区、人物位置、不透明与透明、强调动画余量）没有家。
- **原因**：这是典型的**隐形步骤**——流程里必经的一步既没有被任何东西检查，也没有在产品上留下痕迹。
- **行为修正**：视频路线上缺 `_internal/01_content/design_direction.md` 就 `check` 拦下、`next` 先要它（并点名四条约束与 Stage 文档）；幻灯片路线保持现状（推荐的前置，不是门）。
- **证据**：报告 P-19。
- **状态**：已升级（v5.5）

### G-12 把"宿主打印的 JSON"当逐行日志读

- **module**：`scripts/review_surface.py` 的 `_startup_report`
- **现象**：审阅宿主（公共件 `serve-review.mjs`）明明自证了，`start_host` 却报"宿主起来了但没有自证（日志里没有带 url 的启动报告）"——因为它打印的是 `JSON.stringify(report, null, 2)`，**跨多行**，而解析写成了"逐行试 `json.loads`"，每一行都不成立。
- **原因**：写的人默认"一行一条 JSON"（日志的直觉），实际是美化输出；这类失败还会把日志路径报出来，看起来像宿主的问题。
- **行为修正**：按 `{` 逐个位置试 `json.JSONDecoder().raw_decode`（跨行也能取值），不要逐行解析。报错文案保留日志路径。
- **证据**：`scripts/review_surface.py` 的实现与 `scripts/test/test_review_surface.py`（宿主自证那两条用例跑得通）；第一次实测的报错原文见 v5.5 补丁 B8.3 的维护记录。
- **状态**：已升级（v5.5 补丁 B8.3）

### G-13 桥的能力声明在无插件模式下取不到（别按它决定显示上传控件）

- **module**：`planners-review-core/assets/review-bridge.js` 的 `httpTransport`（**公共件那边的问题**；本 Skill 的修正是别依赖它）
- **现象**：宿主 `/__review/capabilities` 答的是 `{"capabilities":["asset-upload"]}`，但页面里 `review.capabilities` 实测是 `[]`：`httpTransport` 先把 `capabilities` 绑定给返回对象的属性，随后那次异步 `fetch` **重新绑定的是闭包变量**，对象属性还指着最初那个空数组。`review.upload()` 走闭包所以**能用**；页面若按 `review.capabilities` 隐藏上传控件，无插件模式下就成了"有上传能力却看不见控件"。
- **原因**：同一个值有两个持有者（对象属性 vs 闭包变量），只有一个被更新。
- **行为修正**（两步）：① 当时的规避是"不按 `review.capabilities` gate 上传 UI，控件常驻、以 `upload()` 的拒绝为准"；② **公共件已修**（`httpTransport` 改成先等 capabilities 再交出对象），所以现在**按 `review.capabilities` gate**（声明里没有 `asset-upload` 就整块隐藏上传控件），并让**浏览器冒烟断言** `review.capabilities` 含 `asset-upload` —— 这条断言就是这个缺口留给后人的回归。
- **证据**：真浏览器实测（无插件宿主、等待 600ms 之后）`review.capabilities === []`；同一次会话里 `POST /__review/upload?rel=…` 返回 200 且文件落地。修后同一条实测拿到 `['asset-upload']`（`scripts/test/test_review_browser.py` 里的断言）。
- **状态**：已修（公共件 2026-09-26；本 Skill 改为按能力 gate，并有回归断言）

### G-14 「戳」是变化驱动的：页面加载后的第一个采样周期只建立基准

- **module**：`planners-review-core/assets/review-bridge.js` 的 `httpTransport`（**公共件那边**；本 Skill 的修正在测试里）＋ `planners-ppt-hell` 的浏览器冒烟
- **现象**：无插件宿主下，页面加载后立刻改文件（模型重出一页），**永远收不到那条戳**——`review.on('changed')` 不触发，页面上的图不换，而版本令牌明明变了（实测：改前 `c5d2ceb9` → 改后 `1419cfa9`，`changed` 计数 0）。
- **原因**：桥的轮询每 2s 取一次 `/__review/version`，**第一次取只把当前令牌记成基准**（`lastToken`），不比较。基准建立之前发生的变化，之后再采样时已经和基准相同了，于是"没变过"。
- **行为修正**：**测试**在改文件之前必须先让基准落定（等一个采样周期，`scripts/test/test_review_browser.py` 里就是那个 `wait_for_timeout(2600)` 加注释）；**页面**加了「变化戳：N 次 · 最后 HH:MM:SS」状态行，把"戳没到"和"戳到了没处理"分开——真人审阅时不用猜。公共件如果愿意，可以在第一次采样后就绪时给页面一个 `ready`/`baseline` 信号，测试与真人都能少等两秒。
- **证据**：`scripts/test/test_review_browser.py` 的第 ⑤ 步（帧标记 + 换图 + 状态不丢 + 不陈旧）与 v5.5 补丁 B8.4c 的维护记录；上面那对令牌值来自该步失败时的实测输出。
- **状态**：已升级（v5.5 补丁 B8.4c；公共件未改，本 Skill 用等待 + 状态行规避）

### G-15 把「上一轮的意见」预填进参与判定的输入框

- **module**：`assets/review/review.html`（`state` 初始化）＋ `generate_review_html.previous_page_feedback()`（只读上下文的来源）
- **现象**：真人审阅里，用户点**整套提交（含"批准未处理页"）**、唤醒语是「整套已定」，但记录里那一页仍是 `revise`，框选里那句还是**上一轮的原话**，`items` 里还多出一条与上一轮完全相同的待办（已经 `resolve` 过的那句话又回来了）。三处害处：话与记录不一致、整套提交跳过该页、管线拿到一个重复条目把已经改好的页再改一遍。
- **原因**：B8.2 的设计把上一轮的 `feedback`/`annotations`/`assets` **预填进了客户端 state**，并规定"清空才算确认"。预填的字段正是**参与判定的输入**，于是同一段字同时拥有两个身份——"上一轮我要过什么"与"本轮我有什么意见"：`changed(p)` 为真 → 页面判成 `revise` → 生成新条目。
- **行为修正**：上一轮的东西**只作只读上下文**（面板上一块，显示文字/框选/图片改动），**不进任何参与判定的输入**；`state` 从空开始 → 初始 `pending` → 一次点击即可批准、整套提交能覆盖它、不再产生重复条目。人要接着上一轮的话继续提意见就自己复制过去改（那是新意见，该生成新条目）。`previous*` 仍留在页面数据里供追溯。
- **证据**：真浏览器冒烟的三条验收（`scripts/test/test_review_browser.py`：重出后初始 `pending` 且一次点击批准 / 整套提交覆盖它 / `items` 里不再有那一页）＋ 单元测试 `test_v5.test_a_resolved_round_does_not_come_back_as_a_new_todo`。
- **状态**：已升级（v5.5 补丁，2026-09-26 真人使用打回后改）

### G-16 条目"关闭"了，但同一句话还能再长出来

- **module**：`scripts/review_feedback.py`（`content_key`／`closed_keys`／建条目）＋ `scripts/orchestrate/ppt_pipeline.py`（`resolve` 写 `closed`）＋ `assets/review/review.html`（历史只读）
- **现象**：`resolve` 过的意见（同一页、同一句话）第二次又变成条目，`items` 里两条指向同一个人说的同一件事；用户"整套批准"之后状态里还挂着一条未决条目，`next` 不报可以导出。
- **原因**：`resolve` 只把条目从"未决"里摘出来，**没有关闭它的身份**；而"上一轮的意见"当时被预填回输入（G-15），于是同一句话不断以新条目回流。人被迫回头清自己的意见才算数——**等于把模型的收尾工作转嫁给人**。
- **行为修正**：`resolve` 记录该意见的内容身份（`closed: [{page,key}]`，`key=content_key(页, 文字, 框选, 图片操作)`）；收件时同页同话**不再生成条目**并报 `review_intake.suppressed`（不静默）；"有意见不许批准"只约束人刚写下的新意见；整套批准后 `items` 为空、`next` 报 `EXPORT`。
- **证据**：`test_v5.test_a_resolved_item_never_comes_back_and_a_new_wording_still_does`（同一句话不再成条目、**换说法仍是新意见**，防过度抑制）＋ `test_a_whole_deck_approval_leaves_no_items_and_next_can_export` ＋ 浏览器冒烟的四条验收。
- **状态**：已升级（v5.5 补丁，2026-09-26 用户本人打回后改）

### G-17 框选的坐标是**可执行的信息**，不是"用户觉得这里有问题"

- **module**：`assets/review/review.html`（框选产生 `annotations[].{x,y,w,h}`）＋ `references/workflow/07_visual_review.md`（模型怎么用它）
- **现象**：一条只有五个字的框选（「底部没对齐」）如果只当"用户觉得这里有问题"，模型只剩猜：柱底？标签？参考线？页脚线？而同一句话**配着归一化坐标**就变成可执行信息——按坐标把那一带裁出来看，实体缺陷当场现形。
- **证据**（2026-09-26 试用 deck 的 `data` 页）：框选 `x .083, y .684, w .911, h .188` → 像素 `x 159–1908, y 739–942`，正好是页面的底部带；把这一带裁出来放大，看到的是「横轴 280–1700 而柱组 420–1500：左出头 140、右出头 200，右边那截悬空」。改成与柱组同宽（420–1500）后 `check` 0 error/0 warning，两端等宽。**如果没有坐标，这句话至少对应三种改法。**
- **行为修正**：收到框选，**先按坐标把那一带渲染出来看**（裁 `_internal/03_png_preview/pages/<page_key>.png`），再决定改什么；坐标是**归一化**的（0–1、相对页面），先换算成像素（`x*1920, y*1080, w*1920, h*1080`）。同一条规则也适用于"用户圈了整块"那种（`w>0.9`）：那是"整页重做"的信号，不是"某处小修"。
- **状态**：已升级（v5.5 补丁；`07_visual_review.md` 里写明"先按坐标裁图看"）

### G-18 把注入点塞进 `src="…"`：宿主换成"整段"之后页面就 404

- **module**：`assets/review/review.html`（注入点的写法）＋ `scripts/review_surface.py` 的 `host_alive`（判活）
- **现象**：页面突然连不上桥（`window.ReviewBridge === undefined`，console 一条 404，`#bridgeState` 显示"没有加载到审阅桥"）。**代码一行没改**——是公共件的宿主改了注入形态：它现在把 `{{REVIEW_BRIDGE}}` 换成**一整段**（`<script>window.__REVIEW_BASE__="/"</script>` ＋ `<script src="/__review/bridge.js"></script>`），而页面原来写的是 `<script src="{{REVIEW_BRIDGE}}"></script>` —— 整段塞进 `src="…"` 里，标签被撑破，浏览器去请求一个垃圾 URL。
- **原因**：契约说的是"宿主在 serve 时把注入点**换掉**，换成什么由宿主决定"（URL 或内联源码）；页面把它当成"这里只填一个 URL"就绑死了宿主的实现细节。
- **行为修正**：注入点**独立成行、只出现一次**（宿主 `replaceAll`，两个就会注入两次），外面不要再包 `<script src="…">`；校验器挡不住这一点（它只查 `includes('{{REVIEW_BRIDGE}}')`），所以**测试要钉住**：冒烟里断言注入点不在 `src=` 里、且服务出去的页面"注入点以外逐字节等于磁盘上那一份"。判活 (`host_alive`) 同样**不比注入那一小段**——比"注入点以外相同 ＋ 注入点确实被换掉了"，否则宿主改一次注入形态就会被误判成"宿主死了"、每次 `review` 都重启一个新端口。
- **证据**：`scripts/test/test_review_surface.py`（注入点唯一/不在 src 里/注入点以外逐字节相同）＋ 浏览器冒烟（`window.ReviewBridge` 必须就位）。这次的现场是 2026-09-26 公共件改注入形态时被冒烟当场抓到。
- **状态**：已升级（v5.5 补丁）

### G-19 同一次提交被重发：说"已在路上"，不说成失败、也不说成又通知了一次

- **module**：`assets/review/review.html` 的 `push()`／`wakeNote()`（提示分档）
- **现象**：人点了提交、看着没反应、**再点一次**。第二次宿主报 `duplicate`（同一次提交之前已送达），页面却说「…**并已通知模型**」——不算撒谎（通知确实在），但比实际发生的事更满。
- **原因**：提示只有"成功/失败"两档，而"这次没有新增通知（之前已送达）"是第三种事实。
- **行为修正**：`review.wake()` 的返回里 `duplicate` 为真时，直接说宿主给的那句 ——「已写入；本次没有新增通知（同一次提交之前已送达）」，**不套"并已通知模型…"那套词**。与"只说自己核过的事"是同一条规则的两面：**页面说的必须是实际发生了什么**。
- **证据**：`scripts/test/test_review_browser.py`（把 `review.wake` 换成返回 `duplicate` 的形状 → `#message` 是那句 notice、且**不含**"并已通知模型"）。
- **状态**：已升级（v5.5 补丁）

### G-20 渲染挂在握手后面 = 没桥就空白，而且零报错

- **module**：`assets/review/review.html` 的 `boot()`（启动顺序）＋ `scripts/test/test_review_surface.py`（结构断言）＋ 浏览器冒烟（行为对照）
- **现象**：插件 iframe 里握手不落地（没有 init）→ 页面只剩静态骨架，逐页卡、导航、状态**一个都不画**，console 也**没有报错**；用户看到的是"空白页"，排查时无从下手。（同形的另一种：不透明源 iframe 顶层读 `localStorage` 直接抛 → 脚本当场死，也是静态骨架 + 零报错。）
- **原因**：`boot()` 把 `render()` 排在 `await ReviewBridge.connect()` **之后**，并且在 `if(!window.ReviewBridge) return` 之后 —— 渲染被挂在了外部依赖上，**等于把"桥"当成氧气**。
- **行为修正**：先把自带 data 画完（逐页卡/导航/状态），**再**握手；握手加 `BRIDGE_TIMEOUT_MS` 上限，不落地就按"没有桥"降级继续；连不上时页面自述「本页只读 —— 内容可以看，反馈存不进去」。顶层不碰本地存储。**四条判据**：① 加载后内容真的长出来（不依赖握手）② 把 `connect()` 换成永不返回 → 仍完整画出并出现"只读"自述 ③ 结构上 `render()` 必须排在第一个 `await` 之前 ④ 不许裸用 `localStorage`／`sessionStorage`。
- **证据**：`test_the_page_paints_itself_without_a_bridge`（结构四条）＋ 浏览器冒烟的两条对照 —— 握手不落地时**新写法 rail=2 + 自述只读**，而**旧写法（渲染在 connect 之后）在同一场景 rail=0、标题空、状态空**（红）。bypage 是这条规则的样板（它先渲染再接线，且本地存储走 try/catch）。
- **状态**：已升级（v5.5 补丁，2026-09-26 由 video-idea 那一路"扫同类"报出）

### G-21 页面按 registry 渲染、收件按 manifest 推 —— 一份合法提交被判"没覆盖全部 Layout"

- **module**：`scripts/generate_template_review_html.py`（页面渲染用 `template_registry.json` 的 layouts）＋ `scripts/template_feedback.py`（`expected_layouts()`）
- **现象**：真项目（`page_manifest.template_intake.mode = autonomous`，但项目里有一份 5 个 layout 的 fidelity registry）上，审阅页显示 5 张卡、人逐张决定、提交 → 收件判 `feedback must cover the exact layout set with pass/discard/revise decisions`。**一份完全正确的提交被拒**，而且人看不出为什么。
- **原因**：收件层按 `page_manifest.template_intake.mode` 推 expected_layouts（非 `fidelity` 就只认 `reference_system`），而**页面是按 registry 渲染的** —— 同一件事有两个来源，两个来源在"这个项目算哪条路线"上不一致。**一处事实只能有一个来源**。
- **行为修正**：expected_layouts **取快照里写下的那份列表**（生成审阅页时与页面一起写的），registry 只作退一步的兜底。于是"页面显示几个 layout"与"收件要哪几个"永远是同一件事。红对照：`template_feedback.validate(..., expected=['reference_system'])` 必须判这份合法提交不合法（`test_the_old_manifest_derived_layout_rule_would_reject_a_valid_submission`）。
- **证据**：真项目副本上加盖（`test_template_review_browser.py` ⑦）；夹具那一层在 `test_template_surface.py`。
- **状态**：已升级（v5.5 补丁，2026-09-26 模板审阅面接缝化时发现）

### G-22 模板审阅的"批准绑定"原来只认旧服务器写下的 provenance

- **module**：`scripts/template/template_library.py`（`require_approved_feedback`）＋ `scripts/template_feedback.py`（收件盖章）
- **现象**：面接缝化之后页面成了写者，provenance 里没有 `route`、没有那三份摘要 → **发布闸门会把每一份新批准都拒掉**（"not bound to the current server review HTML"）。
- **原因**：闸门要求 `provenance.source == 'review_server' and route == '/template-feedback'`，并把"批准绑在哪些字节上"的摘要当成写者的附带产物 —— 而写者换了人，这些摘要没人算了。
- **行为修正**：① 闸门认两个写者（新页面 `template_review_page`；`review_server` 继续认，因为老项目里那份批准是人真的给过的）；② **摘要由 Skill 的收件层盖章**（`html_sha256`／`png_sha256`／`template_package_sha256`），陈旧的那一份**不盖章**（不留看起来算数的证据）。这与页面审阅"收件时由 Skill 盖版本与 PNG hash"是同一条规则。
- **状态**：已升级（v5.5 补丁，同上）

---

## 五、与相邻 Skill 协作

### G-11 拿一个库顶另一个库

- **module**：`scripts/template/`（模板库）↔ `scripts/style/theme_tokens.py`／`references/workflow/03_video_route.md`（风格库）
- **现象**：文档让「做画面开局就去读风格参考库、挑一个（`template_library.py list`）」，而库里唯一那张是 **PPT 模板**。照做会把 fidelity 锁层绑到视频画面上，第一次 `check` 就报 `FIDELITY_LAYOUT_NOT_DECLARED`／`FIDELITY_LOCKED_LAYER_MISMATCH`／`REQUIRED_FIDELITY_COMPONENT_MISSING`——因为那张 canvas 的锁层里烤着**两个满幅不透明矩形**和一条 **y=1010 的页脚线**：视频画面要么满屏替换、要么透明叠加，前者两个都做不了，后者正压在字幕安全区上。
- **原因**：两个库服务两个出口（模板库给幻灯片、风格库给视频），而入口的默认动作把其中一个顶到了另一个的位置上；文档里「没有贴合的就别硬套」是对的，是被入口的默认动作顶掉了。
- **行为修正**：`SKILL.md` 的两条路线对照表 + 「模板库≠风格库」写清分工；`ppt_pipeline` 只在 `route=='slides'` 时才挂 `--fidelity-template`；视频路线的视觉身份只从风格库（或自主设计，在 `design_direction.md` 里说明）来。**做画面永不经过模板提取。**
- **证据**：报告 P-01（含锁层里那两个矩形的实测 XML）。
- **状态**：已升级（v5.5）

---

## 这个文件不收什么（附理由）

不是所有问题都该变成 gotcha。下面这些**有证据但不入库**，理由跟在各自后面；它们要么已写进别处、要么不是「会稳定复发的行为」。记下来是为了让下一个人不必重新判一遍。

| 候选 | 为什么不入库 |
|---|---|
| **视频路线必然走向导出 PPTX**（报告 P-21） | 一次性的**规格缺失**（当时只有 `final_deck.pptx` 一个终态定义），不是会复发的行为。可迁移的教训「共用一个终态会把某条路线推向下游不要的产物」已写进 `references/architecture.md` 的「终态／路线判定」一行 |
| **测试隐含要求 CWD = Skill 根 + 特定解释器**（报告 P-16） | 环境与测试脚手架问题，已直接修掉（`test_source_assets.py` 自己把 Skill 根放进 `sys.path`）；它不会影响做画面的行为，写进候选只会挤掉真问题。解释器约定已在 `references/architecture.md` 的「环境缝」写明 |
| **两套审阅面不能互操作**（报告 P-14） | 作者已裁定接受的设计（两个主体、各有自己的目录约定），不是缺陷。`architecture.md` 的「两个真相源」第 2 条已写清为什么分开 |
| **材料本身的事实错误**（报告 M-01…M-06、P-15） | 是那一包材料的问题，与本 Skill 的行为无关；报告已经记了，重复记等于把项目反馈抄进 Skill |
| **上游 Skill 的问题**（报告 P-09 指纹按字节数、P-13 地图 Notes 过期、P-17 测试怎么跑、`video-craft` 的 P-25…P-30） | 不归本 Skill 管；按 `architecture.md` 的相邻关系，应该记到对应 Skill 的候选里 |
