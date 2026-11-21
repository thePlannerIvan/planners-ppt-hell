# 内容输入与核查时机

## Bypage 成品

接收 Bypage、委派资料整理或恢复这条链路时，读取 `planners-bypage` 的 `references/content-handoff.md`。复用同一 `project-memory.md` 与权威 `source-index.json`、正式稿 `.planners/by-page.md`、事实核查 `fact-audit.json` 与图片清单 `by-page.assets.json` 的原路径；不在 PPT Hell 另造第二份权威索引或把本地派生稿冒充正式稿。

按上游交付形态选择初始化入口（已有项目继续原工作台，不重新初始化覆盖用户修改）：

1. **现行 `planners-doc/2` 逐页稿（`<Project>/.planners/by-page.md`）**：
   ```bash
   python scripts/init_svg_project.py <project> --source "<Project>/.planners/by-page.md" --route slides
   ```
   按 `.planners/by-page.md` 的章节（`#`）、页（`##`）及页内 `### 正文 / 口播 / 制作` 与页末 `>` 出处，将各页整理写入 `_internal/01_content/page_content.json`（标记 `copy_confirmed: true`），将 `by-page.assets.json` 中的图片复制到项目登记资产并保留原资产 ID、来源 ID 与 `fact-audit.json` 绑定。
2. **旧版 `bypage-production/1` 生产包（`bypage-production.json`）**：
   ```bash
   python scripts/import_bypage.py <project> --production <bypage-production.json>
   ```
   程序校验原稿、审计与反馈的绑定以及页序和资产指纹，自动生成 `page_content.json` 与 `source_assets.json`。本地 `page_content` / `source_assets` 均为制作派生文件。

同时承接原项目记忆中的方法采用记录和已确认论证关系。出现新的表达组织问题时可读取并调用 `planners-method-wiki`，只发展适用的画面或论证表达；方法查询不另建来源索引、不重复事实核查，也不重新决定策略。

## 事实核查的时机

上游有效 audit 只覆盖它实际绑定的 Bypage 原稿；没有内容变化时沿用，不重复建立 source index 或伪造一份已核查 PPT。
模型或用户改数字、主体、时间、单位、来源、关键限定或证据，先对照原索引回源，用 planners-fact-check 的现有契约核查受影响内容；保留结果与核查范围。压缩措辞也检查是否改变命题。缺来源明确报告，不把“未核查”写成“通过”。
新页面版本与输出快照保留变化事实；content_delta / changed_needs_check 不自动沿用原 audit 为改版背书。必要核查在把改版内容作为事实交付前完成；技术 export 不承担事实批准。

## 直接材料与内容展开

Bypage 是已有生产包的适配入口，不是使用本 Skill 的前置条件。用户提供材料、逐页稿或需求时，可先整理成 Markdown，再用 `--source` 初始化并填写 page_content。多源研究或需要完整来源审阅时可调用 Bypage；已有完整内容无需重跑上游。
直接整理也需实际阅读材料和图片，保留来源与未解决问题。没有上游审计就报告实际核查范围，不伪造生产包或审核通过。复杂内容不足以开始设计时，先完成必要的内容整理。

## 页面身份与图片

每页有稳定 page_key、title、content、notes、source_assets，可选 mode 为“讲”或“读”（默认读）。新页使用新 ID；现有工作台页序以 store order 为准，不能只改底稿数组冒充已保存页序。
图片用途开局一次确认。源图被使用或在 unused_assets 写原因；视频包图按契约适配，未被引用的图片点名报错，不删除作者素材来过检查。

## 视频输入

--assets + --plan 初始化直接适配上游 visual-plan，screen_id 原样作为 page_key；上屏内容与不宜上屏的理解信息分别进 content / notes。没有 visual-plan 时用 `--source <上屏稿.md> --route video` 直接制作；这是独立画面输入，未绑定口播与录音，不要求先运行其他 Skill。见 [视频路线](03_video_route.md)。

## 文案对表

页面内容以当前确认稿为依据；新增表达需有内容来源或用户授权。`page_content.json` 是页面制作接口，不替代上游正式稿。`copy_audit.py` 对当前 SVG 的 `<text>` 与该页已确认内容做软核对，不拿备注、制作说明或模板示例文字当作上屏授权。

Bypage / visual-plan 适配器为页面写入 `copy_confirmed: true`，来源绑定沿用 manifest 既有 upstream / visual_plan。直接输入在完成逐页稿整理并确认后，才在对应页标记 `copy_confirmed: true`；未整理原始材料或旧项目无该字段时显示 unchecked，不阻碍工作流。直接稿沿用 `source_path`，可记录 `source_sha256` 校验引用版本；不要为了清除警告改写基准或伪造确认。

对表使用 PPT 的 title + content、视频的 content（视频 title 可能只是屏名）。工具合并 tspan、忽略换行与空格、剥离 Markdown 标记，单独列出短编号和箭头等结构文字，列出其他疑似新增字符串。授权修订先更新当前逐页内容并保留来源；来源文件哈希失配则先刷新内容适配，工具返回 unchecked。

matched 只表示没有发现额外 SVG 文字，不证明全文无遗漏、数字无误或图片内文字已核查；同样也不能证明改写与已录口播一致。疑似项由生产方判断，事实核查继续遵循上面的范围。
