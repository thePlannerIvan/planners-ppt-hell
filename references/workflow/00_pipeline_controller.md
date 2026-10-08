# 接收与恢复

在 Skill 根运行，路径用绝对路径，Python 已安装 scripts/requirements.txt 依赖。

```bash
python scripts/init_svg_project.py <project> --source <source.md|source.doc|source.docx>
python scripts/init_svg_project.py <project> --assets <pack>/assets --plan <pack>/visual-plan.json
python scripts/orchestrate/ppt_pipeline.py <project> next --json
```

初始化两条路线互斥。已有项目恢复原目录，不重新初始化。仍识别 5.0 manifest；更早流程另建目录并核对旧反馈，不混用旧状态机。
幻灯片先按 [内容输入](02_content_stage.md) 判断内容入口。复杂材料交 Bypage 得到逐页稿，再程序导入。视频保留 screen ID；包内图片必须被契约引用。素材库不等于交付包，不能删原素材来消除未引用错误。

## 定方向

幻灯片一次确认视觉来源、画幅、图片需求；视频确认风格与画幅。已指明的直接执行。
幻灯片来源分自主设计、库模板、当次参考、模板提炼入库，见 [模板入口](01_template_intake.md)。视频见 [视频路线](03_video_route.md)。
共同秩序写入 design_direction.md；视频在 check/export 前必须有该文件。

## 状态与动作

正常编辑状态是 WORKBENCH，未复核的 PPT 输出是 EXPORT_VERIFY；内容或契约错误仍报告 CONTENT。没有永久完成状态。
review 是可用动作，不是 compulsory state。export 独立于待办反馈与页面批准，仍运行真实技术校验。模板另走 template-review。
首次接入 store 导入现有兼容 SVG。之后所有修改走 store；直接覆盖兼容目录会报冲突，保留异常文件为候选后处理。
旧 feedback.json 与宿主遗漏提交只报告为恢复材料，不自动应用旧树索引。工作台任务只从 store tasks 读取。
候选命令与资产定位见 [页面制作](04_svg_stage.md)；打开工作台与任务恢复见 [工作台](07_visual_review.md)。
