# 持续工作台、任务与输出复核

review 随时打开工作台；已有待办不阻止打开，普通页不要求逐页或整套批准。

```bash
python scripts/orchestrate/ppt_pipeline.py <project> review
python scripts/orchestrate/ppt_pipeline.py <project> review --surface-only
```

## 选择宿主

DSH 侧栏可用时，用 surface-only，把返回的绝对 surface 路径交 review_open。侧栏支持逐页反馈，原有整套反馈也保留：逐页提交只针对本页，整套提交针对这次选定的任务范围，不把旧整套页面状态覆盖其他页。
没有侧栏时，运行默认 review 打开本地整套工作台。两路都通过同一个 store 保存页面与任务；改字、调位置和 notes 的保存独立于发送反馈，不依赖模型唤醒。SVG 已保存不等于 PNG 已更新，旧 PNG 不能冒充当前画面。
宿主必须支持 surface 声明的 command backend。若没有 command 能力、接口不可用或后端拒绝，明确说明未持久保存，保留未提交草稿；使用页面给出的本地启动命令或重新运行默认 review，转到同一项目的本地宿主。不能退回 legacy feedback.json 树索引写回，也不能把 write 或 wake 成功当作页面保存成功。

刷新按钮是“保存并同步最新页面”：先等页面编辑、反馈草稿和页序收到持久回执，再读 store 的最新 SVG、任务和缩略图。它不做浏览器重载、不提交反馈、不唤醒模型、不触发导出；保存或版本冲突失败时保留输入并停止同步。

## 处理任务

next 从 store head tasks 报 pending。读取目标页及 protected，走 [候选制作](04_svg_stage.md) 的 checkout → 修改 → save，命令附 task_id。
每页单独处理，不携带旧整套状态覆盖其他页。相同文字的新提交仍是新任务；ID 代表动作，不是文字永久去重。
resolve 通过 store 绑定结果，不表示用户批准。当前命令用目标页到 revision 的 results 映射：

```json
{"op":"resolve","operation_id":"resolve_task_01","task_id":"<task_id>","results":{"alpha":"<保存回执revision>"},"note":"<实际处理及保留差异>"}
```

旧 _internal/05_review/feedback.json 与宿主日志的遗漏原文只做恢复报告。它们没有 stable store 元素和基版，不自动应用 svg_edits，也不伪造浏览器改写授权。

浏览器提交后清空本轮新意见；已提交任务和 resolved 任务只显示在待处理／历史区。后续任务不得把历史反馈拼回指令，只有用户主动重新开启历史反馈时才生成新的当前意见。

## 输出与复核

网页输出按钮提交快照后，或恢复一次输出/复核时，读 [项目契约的选定版本输出](../contracts/project_contract.md#选定版本输出)，使用该次确切路径；反馈不是输出批准。
PPT 复核查看实际渲染的逐页图，记录换行、层级、图片裁切与接受差异。缺少实际渲染就说明未复核，不伪造预览或宣称跨渲染器完全一致。完成本次输出后工作台继续可编辑。
