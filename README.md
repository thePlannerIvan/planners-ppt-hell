# Planner's PPT Hell v5

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-2563eb)](LICENSE)
[![Skill](https://img.shields.io/badge/Codex%20%2F%20Claude-Skill-111827)](SKILL.md)

主 Agent 把材料或上游交来的画面契约做成有证据、可读、跨页一致的 SVG 画面。**两个出口**：

- **可编辑 PPT** —— 整理轻量内容底稿、自主设计 SVG、渲染看图调整、可选整套人工审阅，导出 PPTX。
- **视频静态画面** —— 从上游的 `visual-plan.json` + `assets/` 出发，挑一个视觉风格、逐屏出**可被动画指名**的 SVG，录制前交付，**不导出 PPT**。

> 作者：阿祖不看 TVC（小红书同名） · [demyth.info](https://demyth.info) · [Lawyif@163.com](mailto:Lawyif@163.com)

入口见 [SKILL.md](SKILL.md)。依赖见 [scripts/requirements.txt](scripts/requirements.txt)；Python 还需 Playwright Chromium。

## 它解决什么

材料到画面之间最难的一段不是排版，而是**内容取舍**和**看着画面改画面**。本 Skill 让主 Agent 先把材料整理成轻量内容底稿，再自己设计 SVG、渲染出来看、看着改 —— 画面本身成为判断依据，而不是先定稿再排版。

工程上它只保证三件事：画面有证据（检查画面与导出 PPT 共用同一套坐标几何）、跨页一致（画布与视觉 token 只有一个 owner）、可复核（校验器与渲染结果留在项目里，人能回看）。

## 适合 / 不适合

适合：

- 有一批材料、或一份上游逐页内容稿，要做**可编辑**的 PPT；
- 上游 `video-idea-system` 交了 `visual-plan.json`，要在录制前把静态画面做出来；
- 要复用指定品牌模板，或从已有 PPTX 提取模板；
- 已有项目需要返修。

不适合：

- 只需要一份逐页内容稿（用 [Planners Bypage](https://github.com/thePlannerIvan/planners-bypage)）；
- 要动画或成片（那是 `video-craft` 的事）；
- 只要"一句话生成的成品 PPT"，不接受中间有一轮看图修订。

## 安装

通用 Skills CLI：

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell --skill planners-ppt-hell
```

也可直接放入 Codex 或 Claude 的 Skill 目录：

```bash
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git ~/.codex/skills/planners-ppt-hell
# 或
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git ~/.claude/skills/planners-ppt-hell
```

## 典型用法

```text
使用 $planners-ppt-hell，读这个项目文件夹的材料，做一套 12 页的可编辑 PPT。
```

```text
使用 $planners-ppt-hell，按这个品牌模板复用，先给我看封面和一页内容页。
```

```text
使用 $planners-ppt-hell，从这份 visual-plan.json 出发，做录制前的静态画面。
```

## 幻灯片路线

没有模板时自主选择视觉；严格品牌复用与模板提取按需启用。画幅默认 16:9，开局确认一次（唯一 owner：`scripts/canvas_frame.py`）；模板库在开局挑一个即可，不需要经过模板提取。

导出前会跑检查画面（与转换 PPT 共用同一套坐标几何），未审阅时提醒一次；审阅不是导出的前置门。

## 视频画面路线

```bash
python scripts/init_svg_project.py <project>/<画面目录> \
    --assets <包>/assets --plan <包>/visual-plan.json
```

视觉身份来自 `video-craft` 的**风格库**（`visual/themes/`），**不套模板库**——模板库的条目带锁层，锁层里烤着满幅不透明矩形和一条落在字幕区上的页脚线。完整任务见 [references/workflow/03_video_route.md](references/workflow/03_video_route.md)；这条路上**整套审阅是门**，出口是 `_internal/02_svg_source/<page_key>.svg` 全部页面。

v5 不使用独立 Layout 审阅、强制子 Agent 或三页批次门禁。旧项目需用已归档的旧版本完成，不能直接混用新状态机。

## 验证

**在 Skill 根目录**运行（测试里有隐含依赖当前目录的 import）：

```bash
python3 -m unittest discover -s scripts/test -p 'test_*.py'
```

解释器必须已装 `scripts/requirements.txt` 的依赖。工程验证不替代真实用户的视觉与内容验收。

## 目录结构

```text
planners-ppt-hell/
├── SKILL.md
├── agents/openai.yaml
├── assets/                  # 审阅页与模板库（planner-simple-default）
├── docs/                    # 架构说明与历史归档
├── evals/
├── examples/minimal_deck/
├── references/              # 契约、领域规则、分阶段工作流
└── scripts/                 # 画布几何、SVG 校验、渲染、模板、审阅接缝
```

## 品牌与署名边界

仓库文档、过程 HTML、审阅页面和验证页面可以显示项目来源与作者署名。Skill 默认**不得**把 Planner's PPT Hell、作者或网站标识写入客户最终 PPT、导出的 SVG 或 PNG。

开源许可证不授予冒充官方项目或作者背书的权利；修改版应明确标注 fork 或改动，详见 [TRADEMARK.md](TRADEMARK.md)。

## 开源协议与商业入口

代码以 [AGPL-3.0-only](LICENSE) 发布；请保留 [NOTICE](NOTICE) 中的项目来源与作者信息。闭源授权、私有部署、企业模板适配、工作流定制与培训见 [COMMERCIAL.md](COMMERCIAL.md)。

由阿祖不看 TVC 创建与维护 · https://demyth.info · Lawyif@163.com。
