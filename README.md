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

## 公共模组（缺了会自动装）

本 Skill 依赖若干**公共模组**（独立发布的条目，不是本仓库的一部分）：

- [`planners-review-core`](https://github.com/thePlannerIvan/planners-review-core) —— 审阅面契约、桥与本地宿主
- [`planners-source-index`](https://github.com/thePlannerIvan/planners-source-index) —— 来源索引契约与唯一校验器
- [`planners-fact-check`](https://github.com/thePlannerIvan/planners-fact-check) —— 事实核查契约与校验器
- [`planners-report-kit`](https://github.com/thePlannerIvan/planners-report-kit) —— 报告装配与校验（仅带报告出口的 Skill 需要）

某个模组不在本地时，本 Skill 的适配器会**自动从 GitHub 装它**，不需要手动准备。适配器找的地方按顺序：

1. `$PLANNERS_MODULES_HOME/<模组名>`
2. 本 Skill 的兄弟目录 `<skills-root>/<模组名>`（发布后的主路径）
3. monorepo 里 `02-skills-library/<分类>/<模组名>`
4. **用户级安装根**：`$PLANNERS_MODULES_INSTALL_DIR` → `$PLANNERS_MODULES_HOME`（仅当它已含该模组，或那目录还不存在）→ 默认 `~/.planners-modules/<模组名>`

前三条都没有时才自动安装（顺序不变，**本地永远优先、不会无条件联网**）；装到第 4 条那个**库外**用户级目录，**绝不写进** `02-skills-library` 工作树、`~/.codex|~/.claude|~/.gemini` 的技能目录、或任何系统目录。安装过程**不静默**：会打印缺哪个、找过哪些路径、从哪个 URL 装、装到哪、用的是 `git clone --depth 1` 还是 `npx skills add`、以及装到的 **commit**。装完先在暂存目录里验证（`SKILL.md` + 该模组声明的契约/校验器锚点文件都在），再用 rename 原子就位；**任何失败都会清掉暂存、不留半成品**，并给出可复制的手动安装命令。

要它**只报不装**（CI／离线／审计）：

```bash
PLANNERS_NO_AUTO_INSTALL=1 <你的命令>
```

| 环境变量 | 作用 |
|---|---|
| `PLANNERS_MODULES_HOME` | 指定已有模组所在目录（解析第 1 条，也兼作安装根） |
| `PLANNERS_MODULES_INSTALL_DIR` | 只指定**自动安装**的落点（优先级高于上面那条） |
| `PLANNERS_MODULES_REF` | 要钉的 tag 或分支（不设 = 装默认分支 HEAD） |
| `PLANNERS_NO_AUTO_INSTALL=1` | 只报不装；缺依赖时如实失败并打印手动命令 |

装的是**默认分支 HEAD**，日志里**永远打 commit**；HEAD 恰好被某个 tag 指着时，tag 也一并打出来。想钉版本就设 `PLANNERS_MODULES_REF`：

```bash
PLANNERS_MODULES_REF=v1.0.0 <你的命令>     # 钉在 tag 上
PLANNERS_MODULES_REF=main   <你的命令>     # 钉在某个分支上
```

钉了不存在的 ref 会**如实失败**（不会悄悄退回 HEAD），错误里带正确的可复制命令。

### 两条命令别搞混：谁装 Skill，谁抓依赖

**用户装一个 Skill** —— 用 Skills CLI，它会把条目放进各 agent 的技能目录：

```bash
npx skills add https://github.com/thePlannerIvan/<Skill 名> --skill <Skill 名>
```

**Skill 自己抓一个公共模组（内部依赖）** —— 用 `git clone`，落在库外的单一安装根：

```bash
git clone --depth 1 https://github.com/thePlannerIvan/<模组名>.git \
  "$HOME/.planners-modules/<模组名>"
# 想钉版本：加 --branch v1.0.0
```

**内部依赖为什么不走 `npx skills add`**：它没有 `--dir` 之类的落点参数，只会写进 `~/.claude/skills`、`~/.codex/skills` 这类 **runtime 技能目录**（那是发布器的领地，写进去等于多一份漂移副本）；而且它下载的目录**不带 `.git`**，拿不到 commit、也就没法追溯装的是哪一版。**门面命令归用户，内部依赖归 clone** —— 上面自动安装走的就是这条。

> 自动安装器自己的不变量测试（安装根优先级、禁地断言、候选顺序、幂等、失败清理、只报不装）：
> `python3 lib/planners_modules_install_test.py`（working dir 用 `scripts/lib` 或 `helpers/lib`）



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
