# 5. `ppt_pipeline.py` 定位为无状态工具 CLI，废弃步步打卡状态机

- **Status**: accepted

我们将 `ppt_pipeline.py` 重新定位为封装高频重活的无状态深模块 CLI（只负责 `check` 渲染与布局校验、`review` 打开审阅宿主、`export` 冻结快照转 PPTX、`frames` 测图、以及 `template-select` / `template-review`），不再在主工作流中强迫模型运行 `next`、`inspect` 命令行填空打卡或 `export-inspect` 形式主义手续。

## Considered Options

- **继续强制运行 `next → check → inspect (填 render-token/position) → export-inspect`**：该状态机原本用于约束早期指令遵循能力较弱的模型，但不仅迫使现代长程多模态模型每页重复提交八股文命令行参数，且 `next` 的 `export_available: true` 返回还会不断诱导模型自动导出 PPTX。
- **彻底删除 `ppt_pipeline.py`**：这会打碎 `check`（Playwright 渲染 + 几何校验 + 文案对表合一）、`review`（宿主生命周期管理）与 `export`（带锁冻结快照转 PPTX）这些有真实价值的深模块，同时破坏既有的 400+ 条回归测试。

## Consequences

- 模型的日常制作循环简化为：`workbench_store.py` 存页 → `ppt_pipeline.py check --summary` 出图查错 → 模型直接多模态查看 PNG 大图 → `ppt_pipeline.py review` 打开工作台即完成本轮交付。
- `inspect`、`export-inspect`、`ack-human-edit` 与 `next` 仍保留在 `ppt_pipeline.py` 代码中以维持存量单元测试向后兼容，但已从活跃文档工作流中退役，且 `next` 的指引文本已改为默认交回 `review` 而非 `export`。
