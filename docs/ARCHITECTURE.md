# 架构与验证

四阶段：接收 → 定方向 → 持续工作台 → 独立输出。工作台不是批准状态机。

## 所有权

workbench_store.py 唯一写 head、页面 revision、固定资产、用户保护、任务与快照；模型用 checkout → candidate save，浏览器用同一 commit 接口。
ppt_pipeline.py 负责恢复提示、技术检查、实际看图记录、工作台打开及快照输出。review_surface 与页面宿主接入另有 owner。
review_feedback.py 只对尚未接入 store 的旧项目保留原消费方式；store 存在时报告原始待恢复内容，封住树索引写回。
project_state.py 管输入、方向与派生证据；store 项目页面版本依赖保存 revision，不用 compat 修改时间判断。
模板模块按实际格式生成审阅、消费确认与发布，不与页面任务混用。

## 输出

export 先 snapshot，再校验 scenes 并转换；PPT 检查记录绑定输出指纹而非 live 状态。视频交接明确 snapshot.json 与内容差异，动效和录音处理仍归 Craft。
WORKBENCH 是持续状态，EXPORT_VERIFY 是本次输出待复核，不写永久 COMPLETE。
维护选定快照消费、并发输出或复核溯源时，读 [项目契约的选定版本输出](../references/contracts/project_contract.md#选定版本输出)。

## 候选验证

在 Skill 根用已具备 requirements.txt 的 Python 运行 scripts/test 下定向测试；完整结果以本轮报告为准，不沿用历史通过数量。
重点：store task 路由、legacy 原件恢复、候选基版与 checkout、独立导出冻结、真实技术错误、输出复核独立、当前模板包确认与旧包保留。
浏览器编辑、保护与并发由对应 store/UI 测试验证；本模块测试不替代真实用户视觉验收。
