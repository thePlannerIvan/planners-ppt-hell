# GOTCHAS —— 候选

**这里装候选**：尚未升级的复发隐患，或有意保留的设计取舍。已经升级进代码、测试并登记在 `references/maintenance-history.md` 的历史条目已按 Sediment 清理策略移至归档目录，不再堆在这里。

每条只保留五件事 + 它属于哪个 module：现象／原因／行为修正／证据／状态（`候选` · `已复现` · `已升级` · `已失效`）。新增之前先看同义项，合并而不是追加。

---

### G-36 模板升级不传到已有项目，也不重载已打开的页面

- **module**：`scripts/generate_review_html.py`（`make_review`／`template_fingerprint`）＋ 宿主（`dsh-review-dock`／`serve-review.mjs` 的 `watch`）
- **现象**：模板（`assets/review/review.html`）加新能力之后，已审阅项目里的 `02_visual_review.html` 还是旧的；而且侧栏里**已经打开**的那份页面照旧跑旧代码，看不出模板换过。
- **原因**：两层。① 页面按项目生成一次，重出闸门（快照 `template_sha256` vs 当前 `template_fingerprint()`）只在 `review` 被调用时才算；② 宿主 watch 的是 `snapshot.json`（数据）而不是入口 HTML。
- **行为修正**：**不改（作者 2026-10-07 决定，只记档）**。模板升级后，谁用到哪个项目就在那个项目跑一次 `review`（闸门会重出），页面若已打开则点一下「重新加载」。副作用：重出会换 `review_id`，旧提交原件仍在 `history/round-NN.json`。
- **证据**：2026-10-07 实测——跑一次 `review --surface-only` 后页面能力与快照指纹同步更新；宿主 surface 只声明 `watch: ["snapshot.json"]`。
- **状态**：候选（有意保留；别当缺陷再提）

---

### G-44 存量旧包 `dark-titanium-cockpit` 待按严格校验重发

- **module**：`assets/template_library/dark-titanium-cockpit/` ＋ `scripts/template/template_library.py`
- **现象**：`dark-titanium-cockpit` 的 `SPEC.md` 存在 4 处空单元格、`tokens.css` 有 5 处 `72px - 76px` 区间值，且 52 个 `primitives/*.svg` 未引用 tokens。
- **原因**：新包严格校验（`validate_pack_dir(..., strict=True)`）与脚手架已于 2026-11-13 上线，但既有的旧包尚未重提取或逐项重修重发。
- **行为修正**：新提取/发布的模板包强制走严格校验；`dark-titanium-cockpit` 暂维持旧包豁免，待后续专项升级并跑 `template_library.py refresh dark-titanium-cockpit` 重发。
- **证据**：2026-11-13 检查 `SPEC.md` 空表、`tokens.css` 区间值与 `primitives/*.svg` 引用情况。
- **状态**：已部分升级（新包严格校验已生效；`dark-titanium-cockpit` 仍待重发）

---

## 这个文件不收什么（附理由）

不是所有问题都该变成 gotcha。下面这些**有证据但不入库**，理由跟在各自后面；它们要么已写进别处、要么不是「会稳定复发的行为」。记下来是为了让下一个人不必重新判一遍。

| 候选 | 为什么不入库 |
|---|---|
| **视频路线必然走向导出 PPTX**（报告 P-21） | 一次性的**规格缺失**，已通过独立默认终点与 `evals` 边界解决。可迁移的教训「共用一个终态会把某条路线推向下游不要的产物」已写入工作流与 ADR。 |
| **测试隐含要求 CWD = Skill 根 + 特定解释器**（报告 P-16） | 环境与测试脚手架问题，已直接修掉；不写入规则候选。 |
| **两套审阅面不能互操作**（报告 P-14） | 作者已裁定接受的设计（项目审阅工作台 vs 模板库审阅面，各有独立目录约定），不是缺陷。 |
| **材料本身的事实错误**（报告 M-01…M-06、P-15） | 属具体输入材料问题，与本 Skill 行为无关。 |
| **上游 Skill 的问题**（报告 P-09、P-13、`video-craft` 的 P-25…P-30） | 不归本 Skill 管，应记入对应上游或下游 Skill 的候选。 |
