# Planner's PPT Hell

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-2563eb)](LICENSE)
[![Skill](https://img.shields.io/badge/Codex%20%2F%20Claude-Skill-111827)](SKILL.md)

**先把每一页做成人眼看得见、能按图挑刺的清晰 SVG，再一键变成真正可编辑的 PowerPoint（`.pptx`），或者直接输出给短视频使用的静态关键帧画面。**

> 作者：阿祖不看 TVC（小红书同名）· [demyth.info](https://demyth.info) · [Lawyif@163.com](mailto:Lawyif@163.com)

---

## 一句话看懂：它的两个出口与生态卡位

很多 AI 生成的 PPT 之所以“不能交稿”，是因为字体叠车、盒子只是死截图、改一个字得全套重生成。**Planner's PPT Hell** 反过来：所有页面先以高可控 SVG 写成，渲染出图自检后再交给你在**可视化审阅台逐页看图返修**，最后通过坐标几何转换出原生可编辑元素：

```text
输入（任选其一）：
  ├─ 路线 A（做幻灯片）：planners-bypage 逐页包 / 直接资料 / 已有 PPTX 模板
  │     → 挑模板或现场扒模板 → AI 设计每页 SVG → 看图自查 → 打开审阅台改图
  │     → 出口 ①：原生可编辑 PowerPoint（final_deck.pptx + 演讲者备注）
  │
  └─ 路线 B（做视频静态画面）：video-idea-system 的 visual-plan.json（或已定稿上屏稿）
        → 对照风格参考（私有风格库或通用洁净风格）绘制 9:16 / 16:9 静态 SVG
        → 出口 ②：直接交付已保存 SVG 与素材目录 → 交给 video-craft 做动效合成
```

*(注：若你的新视频还没有 `visual-plan.json` 与口播定稿，请先从 [`video-idea-system`](https://github.com/thePlannerIvan/video-idea-system) 开始；只需要写逐页文案先不急着排版，请用 [`planners-bypage`](https://github.com/thePlannerIvan/planners-bypage)。)*

---

## 开箱自带：4 套旗舰模板库 + “直接从现有 PPT 扒模板”

你既不用从零凑样式，也不必被死板的几套默认模板绑死：

### 1. 内置 4 套开箱视觉模板

| 模板包名称 | 视觉风格与适合场景 |
| --- | --- |
| `agency-social-proposal` | **整合营销与社媒种草提案**：高对比杂志编辑感 + 实战种草卡片与排期表 |
| `consulting-product-strategy` | **商业分析与产品战略报告**：深空蓝黑冷峻数据秩序 + KPI 仪表带、2×2 象限与四阶传导 |
| `dark-titanium-cockpit` | **瑞士先锋排印与暗钛金驾驶舱**：强字阶对比、极细发丝网格与单点高对比破局色 |
| `planner-simple-default` | **通用简洁商业模板**：克制高对比浅色系，开箱通用不抢戏 |

### 2. 从任意旧 PPTX / PDF “扒”出一套品牌模板

手上有客户 VI 手册或去年的优秀提案 `.pptx` / `.pdf`？可以直接让它提取配色、字体规范、底壳与可复用版式家族——在网页界面里勾选你想要的那几类版式骨架，一键生成专属模板包并在后续整套复用。

### 3. 看图无限返修的工作台

在工作台里你可以随时：
- 给某一页划框提意见（“字太挤 / 换个对比卡片布局 / 重写这页论据”）；
- 整套切换模板，或针对单页请求改换版式骨架；
- 点击确认导出固定快照的版本，保证“网页里点选的最终版本”就是导出的 `.pptx`。

*(如果改了某页的核心事实或数据结论，Skill 会按需请 [`planners-fact-check`](https://github.com/thePlannerIvan/planners-fact-check) 复查那一页；仅调整排版时直接快速重渲染。)*

---

## 什么时候选我 vs 选别的 Skill

| 你现在手里有什么 | 用哪个 Skill | 原因 |
| --- | --- | --- |
| 文档零散、还没定好每页该写什么故事和数字依据 | 先用 [`planners-bypage`](https://github.com/thePlannerIvan/planners-bypage) | 先写出经得起审计的逐页文案与配图，再来做版面 |
| 内容或结构已有思路，现在要做 SVG 页面、套/提模板、导出可编辑 `.pptx` | **本 Skill (`planners-ppt-hell`)** | 负责视觉呈现、审阅返修、PPTX 导出与视频静态画面 |
| 静态画面做完了（或手头是实拍视频片段），要剪口播、加动效、出词级字幕、合成最终视频 | 交给 [`video-craft`](https://github.com/thePlannerIvan/video-craft) | 我不制作视频时间轴动画或音频剪辑 |

---

## 快速开始与安装

### 1. DSH 用户（推荐）

通过 [Planners Form](https://github.com/thePlannerIvan/planners-form) 在 DSH 设置里勾选 `planners-ppt-hell` 一键安装。

### 2. Codex / Claude Code 用户

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell --skill planners-ppt-hell
```

或克隆到本地 Skill 目录：

```bash
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git ~/.codex/skills/planners-ppt-hell
# 或
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git ~/.claude/skills/planners-ppt-hell
```

### 3. 安装 Python 渲染依赖

```bash
pip install -r scripts/requirements.txt   # python-pptx / lxml / Pillow / playwright
playwright install chromium             # 用于把 SVG 渲染成真实 PNG 预览与目检
```

### 4. 直接这样调用

**做 PPT：**

```text
使用 $planners-ppt-hell 读取这个逐页内容包（或这批项目资料），先用 consulting-product-strategy 模板做出前两页让我看效果。
```

**扒旧 PPT 模板：**

```text
使用 $planners-ppt-hell 从这份客户参考.pptx 里提取一套可复用模板包，打开网页让我勾选需要的版式。
```

**做视频静态关键帧：**

```text
使用 $planners-ppt-hell 根据上游的 visual-plan.json 和 assets 生成视频录制前的静态 SVG 画面。
```

### 真实运行时依赖

- **核心环境**：Python 3（见 `scripts/requirements.txt` + Playwright Chromium）与 Node.js 20+（审阅宿主）。
- **代码级自动加载底座**（缺了会自动拉取至 `~/.planners-modules/`）：[`planners-review-core`](https://github.com/thePlannerIvan/planners-review-core)（看图审阅台）、按需校验使用的 [`planners-source-index`](https://github.com/thePlannerIvan/planners-source-index) 与 [`planners-fact-check`](https://github.com/thePlannerIvan/planners-fact-check)。（**不依赖 `planners-report-kit`**。）
- **按需协同的同行 Skill**（环境中存在时自动参考）：[`slide-copy`](https://github.com/thePlannerIvan/slide-copy)（微调页面文案）、[`planners-method-wiki`](https://github.com/thePlannerIvan/planners-method-wiki)（补充论证关系）。
- **视频风格库优雅降级**：若本机配置了私有风格库 `~/.config/planners/video-vault` 会自动挂载；开源无该目录时会自动降级为内置通用洁净风格 `default-clean`。

---

<details>
<summary>开发者说明：环境变量、输出目录规范、模板校验闸门与单测（普通用户可忽略）</summary>

### 公共模组解析与离线开关

适配器（`scripts/lib/planners_modules.py`）按顺序查找本地公共模组：
`$PLANNERS_MODULES_HOME` → `<skills-root>` → `02-skills-library/<分类>` → 用户级目录（`$PLANNERS_MODULES_INSTALL_DIR` → `$PLANNERS_MODULES_HOME` → `~/.planners-modules/`）。设 `PLANNERS_NO_AUTO_INSTALL=1` 可在 CI/离线环境禁用自动克隆。

### 导出目录与版本存储

- 工作台采用 `store checkout → 编辑 candidate → save` 与版本冲突保护；`_internal/02_svg_source` 仅为可重建兼容视图。
- 固定版本导出产物位于 `_internal/06_ppt_output/<snapshot_id>/`，根目录 `final_deck.pptx` 为最近成功输出的兼容副本；PPT 导出支持 `--previews` 与 `export-inspect` 实图核验。

### 验证与模板库完整性闸门

**在 Skill 根目录运行**（修改过 `assets/template_library/` 后发布前必跑 `verify`）：

```bash
python3 scripts/template/template_library.py verify
python3 -m unittest discover -s scripts/test -p 'test_*.py'
```

### 目录结构

```text
planners-ppt-hell/
├── SKILL.md
├── agents/openai.yaml
├── assets/                  # 4 套内置模板包（template_library/）与审阅页
├── docs/                    # 架构与历史文档
├── evals/
├── examples/minimal_deck/
├── references/              # 契约、领域排版规则与 00-08 工作流文档
└── scripts/                 # 画布几何、SVG→PPTX 转换、模板提取与工作台服务
```

</details>

---

## 品牌边界、开源协议与商业合作

- **许可协议**：以 [AGPL-3.0-only](LICENSE) 发布，可商业使用，修改版或通过网络提供的服务须公开源码。
- **署名边界**：源码与审阅工作台保留作者标识；默认**不得**把 Planner's PPT Hell、作者或站点信息写入客户最终 `.pptx`、导出 SVG 或 PNG。修改或衍生规范见 [TRADEMARK.md](TRADEMARK.md)，归属声明见 [NOTICE](NOTICE)。
- **商业支持**：企业定制品牌模板包、私有部署、工作流定制或闭源授权，请联系 `Lawyif@163.com` 或访问 [demyth.info](https://demyth.info)，详见 [COMMERCIAL.md](COMMERCIAL.md)。

## 相关项目

- [Planners Bypage](https://github.com/thePlannerIvan/planners-bypage) —— 上游多源资料整理、逐页文案与配图包
- [Video Idea System](https://github.com/thePlannerIvan/video-idea-system) —— 短视频选题、口播稿与 `visual-plan.json` 入口
- [Video Craft](https://github.com/thePlannerIvan/video-craft) —— 接收静态画面或素材剪辑合成最终成片
