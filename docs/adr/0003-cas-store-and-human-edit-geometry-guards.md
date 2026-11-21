# 3. CAS 版本库与人改元素的文字及几何双守卫

- **Status**: accepted

人机共编统一经由支持 `base_revision` 乐观锁（Compare-and-Swap）的 `Store` 提交；用户在工作台直接编辑某元素文字时，系统在 `Guard` 中同时锁定该元素的文字内容与几何坐标（`x`、`y`、`transform`），当整页重画遗漏或挪动受保护元素时返回 `human_edits_lost` 拒绝覆盖并附带保留配方。

## Considered Options

- **在 `_internal/02_svg_source/` 直接文件互写**：模型整页覆盖脚本与浏览器局部保存互相覆盖，用户修改无声丢失，或只能退回重做。
- **只锁定文字内容而不锁定几何坐标**：模型一跑全局重排就把用户在页面上精心对齐排好的文字块挪走，用户感知为“我改过的地方又乱了”。

## Consequences

- `_internal/02_svg_source/` 退化为可重建兼容视图，所有页面读写与版本冲突解决以 `workbench_store.py` 为唯一真相源。
- 脚本批量重建整页时必须消费 `human_edits_lost` 返回的 `guards` 字典（保留 `data-workbench-id`、原位文字、锁定属性或删除状态），只有浏览器反馈显式授予 `rewrite_elements` 权限时才允许改写或移动受保护元素。
