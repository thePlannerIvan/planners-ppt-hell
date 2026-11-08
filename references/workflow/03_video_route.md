# 视频静态画面工作台

可适配 video-idea-system 的 visual-plan.json + assets，也可直接接收上屏稿或材料，将内容制作成静态 SVG。元素级可指名性是可选增强，不是这条路线的前置条件。旧 Story 入口已转入 Idea；可识别的既有包按文件契约接收，不要求重跑故事流程。
普通页面没有录制前批准门。作者可以在持续工作台改字、提任务；录制或交给 Craft 时交付已保存的 SVG 与关联素材，需要固定整套版本时可使用快照，不把整个项目封成终态。

## 接收与方向

```bash
python scripts/init_svg_project.py <project> --assets <pack>/assets --plan <pack>/visual-plan.json
```

无生产包时用 `python scripts/init_svg_project.py <project> --source <上屏稿.md> --route video`，整理 page_content 后使用同一工作台。独立输入输出快照标明未绑定脚本，后续合成需由 Craft 建立脚本与时间绑定；不声称它已满足生产包交接。

已有包的 screen ID 不重新编号；契约中的正文、原样标签和花字按适配器进 content，理由、来源与说明进 notes。未知字段报告裁决，不假装已画上屏。
确认风格与画幅：视频路线仅服务 `production_mode="keyframe-svg"` 的关键帧示意风格（如 `line-art`、`collage`、`business-report`、`concept-film`；若上游契约标为 `footage-montage` 如哈雷/Vans 混剪风，则直接跳过本 Skill 交 `video-craft`）。开工前运行 `python3 scripts/resolve_video_vault.py --style <style_id>` 从私有风格库 `~/.config/planners/video-vault/styles/<style_id>/` 读取 `page.md`、画框预设 `frames/*.json` 与 `anchors/` 多模态参考图（未挂载私有库的开源环境自动降级为 `default-clean` 通用规范）；新视频风格进化与沉淀见 [提炼 SOP](08_video_style_extraction_sop.md)。
共同方向写入 _internal/01_content/design_direction.md，写清风格、机器画幅引用和本次实际选择。字幕区、人物位置、透明/不透明、强调余量都只是**可选提示**：项目需要就写，不需要就不写，不拦页面制作与快照。只有明确要用 Video Craft 的 composition 事实时才读它的 references/composition-facts-contract.md；本 Skill 不复制第二份字段定义。

## 制作与检查

走 [候选制作](04_svg_stage.md) 的 checkout → 编辑 → save，并看当前逐页 PNG 大图。

`id`、`data-step`、`data-anim`、`anchor`、`step` 都是**可选**的：只有当你明确要 Video Craft 做元素级动效时才需要，默认不要求。没有这些，Craft 会把整页当作一张画面使用，或自行重排；不要为了“给视频用”而给每个元素补钩子。若确实要做元素级动效，再读 Video Craft 的 references/svg-animation-contract.md 并保持结构可读；具体动效种类与合成事实仍归 Craft，不在本 Skill 维护第二份词表。

`check` 只跑两条出口共同的技术规则。**没有元素 id 只报 info**，不拦保存、不拦快照；**页内重复 id 仍是 error**——那是 SVG 自身的唯一性问题，不是视频要求。PPT 独有的检查不混入 video 出口。看图记录诚实写发现与位置，技术绿色不代替内容或风格判断。
工作台 review 是可用动作，待处理意见仍可以继续保存或独立导出。

## 交付 SVG

完成保存、技术检查与实际看图后，按 store 的 order 读取各页 get_page 返回的 revision 与 svg_path，交付这些已保存的 SVG、关联素材与 notes。保持 SVG 相对素材路径可解析；移交文件时携带对应资产，不只复制裸 SVG。普通视频交付到此即可，无需运行 export，也无需生成 PPTX。兼容 02_svg_source 可用于查看，交付版本以 store 保存回执为准。

没有脚本或录音绑定时如实说明；文案修改后的事实核查仍按内容输入流程处理，不把 SVG 已保存当成与录音语义一致。

## 按需固定交接版本

需要冻结整套页序与资产、重现某次交接，或下游明确消费 snapshot.json 时，才使用以下快照能力：

```bash
python scripts/orchestrate/ppt_pipeline.py <project> export
```

返回 snapshot.json 绝对路径与 snapshot_id；快照固定页序、SVG、资产、notes 与结构。声明/脚本绑定只在项目本来就有 visual-plan 或实录时记录，不要求、不补造。兼容 02_svg_source 不是交接入口。页面 content_delta 列出变化，快照 `content_binding=changed_needs_check` 提示文本或 notes 与基线不同；不自动改 script_hash，也不能据此声称录音和新文案一致。
把确切快照交 Video Craft；该侧导入、审阅构建与合成必须读取同一入口，不能一个读快照另一个找 live 旧 SVG。资产本地化与 SVG 字节往返检查继续由现有导入器承担。
工作台继续编辑不会改已交快照。再交新快照比较受影响的页面、步骤与资产；脚本或实录变化另走声音/时间轴流程。
静态文字要改时回到本工作台提交；Craft 侧动画/时间轴修改留在 Craft，不直接改内联 SVG 并偷偷反写输入包。第一轮不提供任意双向实时同步。

宿主已给出 snapshot.path，或需要重做某次固定交接时，读 [项目契约的选定版本输出](../contracts/project_contract.md#选定版本输出)，消费该次快照。
