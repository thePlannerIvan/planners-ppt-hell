# 页面制作与候选提交

读 page_content.json、共同方向、所选视觉样张与模板/主题定义，以及当前页用户修改和任务。模板是当前页的设计起点，按内容任务选用或重组；需要改分页或证据时回到内容决定，不为套原语静默删改。
画幅由 canvas_frame.py 管理；SVG 特性见 [SVG 规则](../domain/svg_rules.md)，PPT 再读 [转换规则](../domain/svg_to_ppt_rules.md)。
通用阅读层级与证据可读性见 [设计原则](../domain/style_system.md)，共享视觉数值来自主题，原语坐标是示例实现。

## Checkout → 修改 → Save

所有命令以 JSON stdin 传入：

```bash
python scripts/workbench_store.py --root <project> --command-json
```

读取页：{"op":"get","page_key":"alpha"}。状态：{"op":"state"}。
模型先 checkout，取得候选路径、基版、notes 与 protected：

```json
{"op":"checkout","operation_id":"checkout_alpha_01","page_key":"alpha"}
```

编辑返回的 candidate 文件。checkout 已把 href 定位到固定资产，保持可解析；新资产放项目内并使用相对候选可解析的路径。首次空页 base_revision 为 null，完整 SVG 写入候选。

```json
{"op":"save","operation_id":"save_alpha_01","page_key":"alpha","author":"model","candidate":"<checkout返回的绝对路径>","base_revision":"<checkout返回的revision>","notes":"<本次notes>"}
```

任务改版附 task_id。写命令有稳定 operation_id；同次重试使用同命令与 ID，新动作用新 ID。确认回执 ok、revision 与 changes：图片或文案修改应在对应元素列表里出现；no_change 提醒表示没有有效变化，不能据此声称修改完成。save 保留版本语义，技术 check 另行判断。
task_id 的改写授权绑定反馈当时的 revision；首次保存后再迭代，重新 checkout 最新页，沿用已保存结果，不重复使用过期 task_id。需要扩大人工保护的改写范围时取得新的浏览器反馈授权。最终 resolve 原任务时绑定最新结果版本。
冲突不覆盖当前页：保留候选，重新 checkout 最新版本。候选遗漏 protected 用户改字、位置或删除会被拦下。人改过字的那一处，`guard` 同时钉住它的位置（`x`/`y`/`transform`）：模型想挪动它，必须拿到页面反馈里的显式授权，否则按 `human_edits_lost` 退回。指定元素改写必须有浏览器 feedback 的显式 rewrite_elements 授权；模型不手写授权。
兼容 _internal/02_svg_source 是可重建输出，生成器不能写它。也不手写 head、revision、保护记录或任务完成戳。

## 用生成器重建整页

有时整页是由脚本生成的（数据驱动版面、批量改字号、换一套字阶），这时「在候选上改几笔」不适用：新 SVG 从零生成，用户改过的字会被静默丢掉。store 的保护机制会拦下这种提交，回执里 `code=human_edits_lost`。

**它给的是配方，不是拒绝**。回执里 `elements` 是被丢掉的元素 ID，`guards` 是每个 ID 的守卫内容（`text` 是要逐字保留的文本，`attributes` 是被固定住的属性值，`deleted` 表示用户删过它）。照这份 `guards` 重建：

1. 生成新 SVG。
2. 对 `guards` 里每一项，在**同一位置**输出同一段内容，并带上原来的 `data-workbench-id`：
   - `{"text": "…"}` → 该节点文字必须逐字等于它；
   - `{"attributes": {"font-size": "36"}}` → 该属性必须等于这个值；
   - `{"deleted": true}` → 新 SVG 里不能再出现这个节点。
3. 再 `save`。校验通过即说明用户的改动保住了。

不要把 `guards` 当成「必须原样复制整页」——它只锁定用户真正动过的那几处，其余版面照你的生成结果走。也不要用 `author=human` 或手写授权绕过：`rewrite_elements` 只能来自浏览器反馈。

```json
// 回执示例（save 被拦下时）
{"ok": false, "code": "human_edits_lost",
 "elements": ["wb_7c41d030…"],
 "guards": {"wb_7c41d030…": {"text": "小红书，放大符号传播"}}}
```

## 换图与路径

先用 `python scripts/orchestrate/ppt_pipeline.py <project> frames --pages alpha` 读取当前已保存页的图片 ID、槽位、源图尺寸与 fit 测量，再 checkout。换图按稳定元素 ID 定位；无 ID 时先确认唯一目标，坐标辅助定位。源文件名会被冻结为哈希，不能依赖文件名在所有版本中保持一致。

| 路径形态 | 基准与用途 |
|---|---|
| source/extra/… 或 source/assets/… | 项目素材位置；写 href 前转换为相对 candidate 文件的路径 |
| candidate 中 ../revisions/…/assets/… | checkout 返回的固定资产引用，按 candidate 所在目录解析 |
| revision 中 assets/… | save 冻结后的版本资产，按该 revision 的 SVG 目录解析 |

`frames` 与 validator 共用 `image_diagnostics.py`。测量按 image 的本地矩形与源图比例计算，不推断人脸/产品主体，也不计入外层裁切、遮挡或非等比变换；源图或尺寸无法解析则明确 unmeasured。slice 可见面积、meet 填充率只是提醒，是否改素材/槽位由实际看图决定。

## Check → 看图 → Inspect

```bash
python scripts/orchestrate/ppt_pipeline.py <project> check --pages alpha omega --summary
python scripts/orchestrate/ppt_pipeline.py <project> inspect --page alpha --render-token <token> --note '<实际观察>' --first-glance '<第一眼焦点>' --design-check '<检查内容与发现>' --position 'x=120,y=150,w=400,h=80' --clean
```

`--pages` 用空格分隔，省略即检查全页；不支持逗号列表。`--summary` 返回页、技术状态、缓存标记、issue 码、文案核对状态、token 与 PNG；完整输出保留设计测量、疑似新增文案，validator 报告在 `_internal/04_validation/`。缓存命中仍报告原技术结果，不能把 unchanged 理解成修改已完成。
文案对表的依据和授权修订见 [内容输入](02_content_stage.md)；COPY_UNCHECKED 不是通过，COPY_NOT_IN_BASELINE 需要查看疑似文本。
有问题用 --must-fix，修候选后重跑。看逐页 PNG 大图，不用联系表代替。render_token 绑定当前版本与 PNG；没有实际查看就不记录 clean。
技术错误、缺图、非法 SVG 仍阻止输出；设计测量只是事实，不代替判断。此处没有用户通过门。
处理反馈后用 store resolve 绑定每个目标页的结果 revision 与具体 note，见 [工作台反馈](07_visual_review.md)。

## 页序与反馈收尾

模型可以通过 Workbench Store 增删页面。新增页提交 `op=add_page`、完整 candidate SVG、`page`（page_key/title/content/notes/mode/source_assets）和当前 `base_order`，可用 `before_page_key` 插入指定位置；删除页提交 `op=delete_page`、page_key、当前 base_revision 和 `base_order`。操作会保留历史 revision，更新 store order，并让下次 review / snapshot 看见新页集合；不能删除唯一页面。不要只改 page_content.json 或删除 SVG 冒充完成。

示例：

```json
{"op":"add_page","operation_id":"add_gamma_01","candidate":"<完整候选 SVG>","base_order":["alpha","omega"],"before_page_key":"omega","page":{"page_key":"gamma","title":"新增页","content":"…","notes":"…","mode":"读"}}
{"op":"delete_page","operation_id":"delete_gamma_01","page_key":"gamma","base_revision":"<当前revision>","base_order":["alpha","gamma","omega"]}
```

`order` 继续只调整现有页序，包含每一页且只出现一次，同时携带当前 `base_order`。页面拖动后，提交 `order` 的回执才算完成；`snapshot` 固定 store 的最新 order，Video Craft 必须消费该 snapshot 的 `order`，不能重新读取 visual-plan 或按文件名排序。

通过同一 JSON stdin 接口完成任务：

```json
{"op":"resolve","operation_id":"resolve_task_01","task_id":"<原任务ID>","results":{"alpha":"<结果revision>"},"note":"<实际完成的修改>"}
```

results 必须覆盖该任务所有目标页。checkout / save / resolve 各用独立 operation_id；同一操作重试才复用原 ID 与原请求。
