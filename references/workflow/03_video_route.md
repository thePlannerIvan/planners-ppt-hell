# 视频静态画面工作台

接收 video-idea-system 的既有 visual-plan.json + assets，将上屏声明制作成可按元素指名的静态 SVG。旧 Story 入口已转入 Idea；可识别的既有包按文件契约接收，不要求重跑故事流程。
普通页面没有录制前批准门。作者可以在持续工作台改字、提任务；录制或交给 Craft 时选择一次固定快照，不把整个项目封成终态。

## 接收与方向

```bash
python scripts/init_svg_project.py <project> --assets <pack>/assets --plan <pack>/visual-plan.json
```

screen ID 不重新编号；契约中的正文、原样标签和花字按适配器进 content，理由、来源与说明进 notes。未知字段报告裁决，不假装已画上屏。
确认风格与画幅，选择 Video Craft 主题或明确自主设计；editorial-archive 参考见 [主题说明](../domain/video_style_editorial_archive.md)，新主题提炼见 [提炼 SOP](08_video_style_extraction_sop.md)。
共同方向写入 _internal/01_content/design_direction.md，明确字幕区、人物位置、透明/不透明与强调余量。composition 字段按 Video Craft 的 references/composition-facts-contract.md，不在本 Skill 复制第二份字段定义。

## 制作与检查

走 [候选制作](04_svg_stage.md) 的 checkout → 编辑 → save，并看当前逐页 PNG 大图。给动画目标保留全片唯一 id（含屏号前缀），不按 DOM 序号定位。
data-step、data-anim、anchor、step 及语义子选择器按 Video Craft 的 references/svg-animation-contract.md；维持可读结构，不把它们拍平。具体动效种类与合成事实归 Craft，不在这里维护第二份词表。
check 按 video route 检查共同技术规则与元素 ID，PPT 独有的限制不混入该出口。看图记录诚实写发现与位置，技术绿色不代替内容或风格判断。
工作台 review 是可用动作，待处理意见仍可以继续保存或独立导出。

## 固定交接快照

```bash
python scripts/orchestrate/ppt_pipeline.py <project> export
```

返回 snapshot.json 绝对路径与 snapshot_id；快照固定页序、SVG、资产、notes、声明/脚本绑定和结构。兼容 02_svg_source 不是交接入口。页面 content_delta 列出变化，快照 `content_binding=changed_needs_check` 提示文本或 notes 与基线不同；不自动改 script_hash，也不能据此声称录音和新文案一致。
把确切快照交 Video Craft；该侧导入、审阅构建与合成必须读取同一入口，不能一个读快照另一个找 live 旧 SVG。资产本地化与 SVG 字节往返检查继续由现有导入器承担。
工作台继续编辑不会改已交快照。再交新快照比较受影响的页面、步骤与资产；脚本或实录变化另走声音/时间轴流程。
静态文字要改时回到本工作台提交；Craft 侧动画/时间轴修改留在 Craft，不直接改内联 SVG 并偷偷反写输入包。第一轮不提供任意双向实时同步。

宿主已给出 snapshot.path，或需要重做某次固定交接时，读 [项目契约的选定版本输出](../contracts/project_contract.md#选定版本输出)，消费该次快照。
