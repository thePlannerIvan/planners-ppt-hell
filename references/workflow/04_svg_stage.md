# 页面制作与候选提交

读 page_content.json、共同方向、所选模板或视频主题，以及当前页用户修改和任务。
画幅由 canvas_frame.py 管理；SVG 特性见 [SVG 规则](../domain/svg_rules.md)，PPT 再读 [转换规则](../domain/svg_to_ppt_rules.md)。
通用阅读层级与证据可读性见 [设计原则](../domain/style_system.md)，具体数值来自主题。

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

任务改版附 task_id。写命令有稳定 operation_id；同次重试使用同命令与 ID，新动作用新 ID。确认回执 ok 与 revision 后才说保存成功。
冲突不覆盖当前页：保留候选，重新 checkout 最新版本。候选遗漏 protected 用户改字、位置或删除会被拦下。指定元素改写必须有浏览器 feedback 的显式 rewrite_elements 授权；模型不手写授权。
兼容 _internal/02_svg_source 是可重建输出，生成器不能写它。也不手写 head、revision、保护记录或任务完成戳。

## Check → 看图 → Inspect

```bash
python scripts/orchestrate/ppt_pipeline.py <project> check --pages alpha
python scripts/orchestrate/ppt_pipeline.py <project> inspect --page alpha --render-token <token> --note '<实际观察>' --first-glance '<第一眼焦点>' --design-check '<检查内容与发现>' --position 'x=120,y=150,w=400,h=80' --clean
```

有问题用 --must-fix，修候选后重跑。看逐页 PNG 大图，不用联系表代替。render_token 绑定当前版本与 PNG；没有实际查看就不记录 clean。
技术错误、缺图、非法 SVG 仍阻止输出；设计测量只是事实，不代替判断。此处没有用户通过门。
处理反馈后用 store resolve 绑定每个目标页的结果 revision 与具体 note，见 [工作台反馈](07_visual_review.md)。
