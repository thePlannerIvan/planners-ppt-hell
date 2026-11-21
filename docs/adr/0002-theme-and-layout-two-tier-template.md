# 2. 模板包分为 Theme 与 Layout 两层，并与通用构图力学正交

- **Status**: accepted

我们将模板包（`Template Pack`）拆分为 **Theme**（`tokens.css` / `skyline_shell.svg` / `SPEC.md`）与 **Layouts**（`layouts.json` / `primitives/*.svg`）两层，并把版式定位为给模型的结构参考请求而非自动重绘锁层；同时将具体模板的视觉皮肤与通用构图力学（`Universal Mechanics`）解耦正交。

## Considered Options

- **旧版全页刚性母版（Fidelity Lock）**：强迫每一页套用固定坐标和组件槽位，内容一多就字体踩踏或被迫删减论据。
- **把单一高颜值模板的规则（如去框化、1.5px 细线）写死进通用设计文档**：模型会把那一套视觉风格强加到所有品牌模板上，导致与所选模板皮肤打架，也无法处理高密度咨询报告页。

## Consequences

- 选定 `Template Pack` 时，色彩、字体、容器形式与参考骨架 100% 服从模板；信息主次、单一焦点及高密/低密双密度调度服从 `Universal Mechanics`。
- 工作台内切换整套模板（`template_id`）或指定单页版式（`layout_id`）仅向 Store 提交任务，由模型按内容重排并允许在回执中说明合理偏离。
