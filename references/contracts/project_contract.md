# 项目与版本契约

_internal/00_project/page_manifest.json 保留 version 5.0 与 route（slides / video）。底稿在 _internal/01_content/page_content.json，共同方向在同目录 design_direction.md。page_key 稳定，不随页序变化。

## 存储

store 位于 _internal/06_workbench；原 _internal/06_ppt_output 不受影响。
ensure(root) 首次导入兼容 SVG，之后核对外部改写；state(root) 返回 order、pages[key].revision、tasks[id]；get_page(root,key) 返回 revision、svg、notes、protected。`add_page` / `delete_page` 是页面集合的唯一写入口；add 以 candidate 创建首个 revision，delete 从当前 order 移除但保留 revision 历史。
模型命令通过 workbench_store.py --root <project> --command-json 的 JSON stdin 提交。checkout 返回固定资产引用的 candidate，save 带 author=model、candidate、base_revision。操作 ID 控制重试，基版与用户保护控制覆盖。
模型 save 可带 `layout_id`（这页的参考版式），存进页面记录并随 get/state 返回；人工保存不能写它。反馈任务可带 `template_id` 与每页 `layout_id`；只换整套模板的任务可以没有页面，resolve 用空 results。
save 回执增加 changes（元素增删改 ID/数量、图片和文本变化 ID、notes/protected 变化、序列化字节差、no_change）。比较归 store，图片按冻结内容哈希识别；路径改写不算换图，字节差也不等同视觉变化。no_change 仅提醒，保存与幂等语义不变。
版本 SVG 与资产保存后不可重写。兼容 _internal/02_svg_source 可重建，直接修改会被检测，不静默当作模型新版本。
用户保护与任务在同一 head 持久化。浏览器反馈才可声明元素改写范围。resolve 绑定真实结果版本，不建立页面批准。
模型收件只读取 pending task；resolved task 仍留在历史但不会重新进入新任务。浏览器提交成功后把本轮意见从新草稿移入任务记录，下一轮只提交新增意见。
工作台刷新先取得页面编辑与草稿的持久回执，再读取 store 最新页面和任务；刷新不重载页面、不唤醒模型、不导出，也不覆盖未保存输入。版本菜单只读预览历史，恢复版本才创建新的人工作业版本。
查找与替换只遍历当前 SVG 的 `text` / `tspan` 文本节点，保持稳定元素 ID 与格式边界；整批替换以一次可撤销批次保存，不唤醒模型。元素批注在画布旁输入，允许模型改写只加入当前批注对应任务的 rewrite scope。

## 派生证据

PNG、validator 与 inspect 绑定版本；旧证据不能代表新页。渲染失败不取消保存的 SVG，也不把旧预览盖为当前。
legacy feedback 保持原始值供恢复；旧树索引不是 stable element ID，不盲目回放。

视频默认按 store order 交付 get_page 返回的当前版本 SVG 与关联素材，不要求 export。需要冻结整套版本或消费既有快照时使用以下接口。

## 输出快照

snapshot(root,purpose='slides') 返回 snapshot_id、绝对 root / path、order 与 pages。pages[].svg 是 scenes/key.svg 等快照内相对路径；SVG 与资产冻结，不依赖 live 目录。
快照记录 route、notes、声明与脚本绑定；视频 content_delta / changed_needs_check 报告变化，不自动改稿、script_hash 或录音。
PPT 导出只读快照 scenes；复核绑定 snapshot 与 PPTX 指纹，不比较 live 页以否定旧输出。未处理反馈不阻塞输出，真实技术错误仍阻塞。
工作台长期可编辑；完成输出记录，不写永久 COMPLETE。

## 模板

模板与页面是不同主体。入库批准绑定当前 HTML、review_id、包与预览；重新提炼旧批准失效。四件套与 legacy 模板按实际格式审阅发布，见 [模板包契约](template_package.md)。

## 选定版本输出

网页先保存末次输入，再提交 snapshot；宿主唤醒携带确切 snapshot.path。用 `python scripts/orchestrate/ppt_pipeline.py <project> export --snapshot <snapshot.json绝对路径>` 消费它，不能丢掉路径重取 live 页面。未指定路径时才固定当前快照；指定无效路径直接报错。
slides 的实际输出、notes 和转换报告在 `_internal/06_ppt_output/<snapshot_id>/`，export 记录的 output_path 是证据；根 final_deck.pptx 只是兼容副本。同快照加锁并复用已验证文件。
复核 `export-inspect --snapshot <同一snapshot.json> --previews <实际PPTX渲染PNG...> --note "<工具与发现>"`，绑定该 job 输出，不受后续 live 编辑或最新兼容副本替换影响。
快照导出检查冻结 SVG/资产及冻结页级 mode；目前模板 registry / direction 并未随快照冻结，不用后来变化的 live registry 为旧快照背书，记录 template_verification=intrinsic_svg_only。严格品牌语义的额外复核需明确报告范围。


## 项目画幅与独立输入

机器画幅由 `page_manifest.json.canvas` 保存（width、height，正整数 SVG 像素）；初始化用 `--width` / `--height`，旧项目缺省沿用默认画幅。解析归 `canvas_frame.py`。快照冻结 canvas，选定快照的检查不读取后来变化的项目画幅；已有 SVG 要改画幅需提交新版本。
`--source ... --route video` 的新项目记录 `input_kind=standalone`，未绑定脚本的快照记录 `content_binding=unbound`。它可用于画面制作与审阅，不等于已完成 Craft 的脚本/录音交接。已有 visual-plan 输入继续严格校验声明与脚本；绑定丢失不自动降级。
