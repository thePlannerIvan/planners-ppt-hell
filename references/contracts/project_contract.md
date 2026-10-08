# 项目与版本契约

_internal/00_project/page_manifest.json 保留 version 5.0 与 route（slides / video）。底稿在 _internal/01_content/page_content.json，共同方向在同目录 design_direction.md。page_key 稳定，不随页序变化。

## 存储

store 位于 _internal/06_workbench；原 _internal/06_ppt_output 不受影响。
ensure(root) 首次导入兼容 SVG，之后核对外部改写；state(root) 返回 order、pages[key].revision、tasks[id]；get_page(root,key) 返回 revision、svg、notes、protected。
模型命令通过 workbench_store.py --root <project> --command-json 的 JSON stdin 提交。checkout 返回固定资产引用的 candidate，save 带 author=model、candidate、base_revision。操作 ID 控制重试，基版与用户保护控制覆盖。
版本 SVG 与资产保存后不可重写。兼容 _internal/02_svg_source 可重建，直接修改会被检测，不静默当作模型新版本。
用户保护与任务在同一 head 持久化。浏览器反馈才可声明元素改写范围。resolve 绑定真实结果版本，不建立页面批准。

## 派生证据

PNG、validator 与 inspect 绑定版本；旧证据不能代表新页。渲染失败不取消保存的 SVG，也不把旧预览盖为当前。
legacy feedback 保持原始值供恢复；旧树索引不是 stable element ID，不盲目回放。

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
