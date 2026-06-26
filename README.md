# Planner's PPT Hell

A review-gated Skill for turning dense Markdown, proposal copy, and strategy drafts into editable PowerPoint decks.

![License](https://img.shields.io/badge/license-AGPL--3.0-111111?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Agent-111111?style=flat-square)
![PPT Workflow](https://img.shields.io/badge/PPT-Review%20Gated-D46A00?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Supported-6B5B95?style=flat-square)

[中文版](#中文版) · [English](#english)

## 中文版

Planner's PPT Hell 是 **阿祖不看 TVC** 做的一个开源 Skill，用来把 Markdown、提案文案、策略稿，变成可审阅、可校验、可编辑的 PowerPoint。

它不是“一键生成精美 PPT”的工具。

它更像一个半自动、半手动的 PPT 生产线：模型负责理解文案、设计版式、生成 SVG、做预览、跑校验；人负责在关键节点停下来，看页面是否真的对，决定要不要改，最后再允许它导出 PPT。

这个 Skill 的起点很简单：大模型其实很会写 SVG，而 SVG 又可以转换成 PowerPoint 里的可编辑图形。既然如此，为什么不能让模型直接把一页提案文案写成一页 SVG，再转成 PPT？

真正难的不是做出一页好看的图。

真正难的是：让模型在做很多页的时候不要偷懒，让它逐页思考，让它保留原文的业务含义，让人可以逐页反馈，让所有页面在导出前先被检查过。

所以它叫 PPT Hell。

不是因为它轻松，而是因为它承认：认真做 PPT 本来就不轻松。模型要受苦，人也要受苦，token 也要受苦，但最后换来的是一个更可控、更能改、更接近真实交付的 PPT。

- 小红书：阿祖不看 TVC
- 网站：<https://demyth.info>
- 邮箱：<Lawyif@163.com>

### 它解决什么问题

很多 AI PPT 工具都能很快做出一个好看的东西，但常见问题也很明显：

- 它会把你的内容硬塞进模板里；
- 它会悄悄改写、压扁、丢掉文案里的业务含义；
- 它一次性做很多页时，页面会越来越敷衍；
- 它生成 HTML 很好看，但同事、领导、客户很难继续编辑；
- 它把视觉审阅放得太晚，等你发现问题时已经生成了一大堆页面；
- 它让模型自己说“我通过了”，但没有真正的人类确认。

Planner's PPT Hell 的思路相反：不要让模型一口气做完。

它强迫模型停下来。

先处理文案，再设计版式，再做 SVG，再进入视觉审阅，最后才导出 PPT。每个关键节点都有 gate，模型不能跳过，人也会被迫看到它到底做了什么。

### 工作流程

这个 Skill 会把项目推进到五个状态：

1. **CONTENT**：保留原始文案，整理成结构化页面内容。
2. **PLAN**：思考每一页的版式逻辑、线框图、文案压缩方式和素材需求。
3. **DRAFT**：按批次生成 SVG 页面和 PNG 预览。
4. **REVIEW**：通过本地 HTML 审阅页收集人的视觉反馈。
5. **EXPORT**：所有 gate 通过后，才导出可编辑 PPT。

核心规则很简单：

> 模型可以起草、修改、自检，但不能批准自己。

### 和普通 AI PPT 工具有何不同

**它是 SVG-first，不是 HTML-first。**  
目标不是做一个漂亮网页，而是生成可编辑的 PowerPoint。

**它先审版式，再画页面。**  
模型必须先解释这一页为什么这么排、文案怎么压缩、需要什么素材，再进入 SVG 生产。

**它把模型自检和人工批准分开。**  
validator 和模型自检只是内部证据，真正的通过必须来自人工审阅。

**它不是模板崇拜。**  
这个 Skill 不追求把所有内容套进固定模板，而是要求模型思考：这一页究竟要完成什么说服任务，读者应该记住什么，最简单有效的版式是什么。

**它最终导出 PPT。**  
客户、同事、领导要改的时候，可以继续在 PowerPoint 里改。

### 适合谁

它适合：

- 做提案、咨询、策略、年度规划类 PPT 的人；
- 文案内容比较详实，而且不能乱改含义的人；
- 需要一页一页审阅、反馈、修改的人；
- 最终交付必须是可编辑 PPT 的人；
- 愿意用更多流程换取更高可控性的人；
- 希望模型认真思考，而不是只负责装饰的人。

尤其适合那种“内容很重要、页面很多、结构相似、但又不能粗暴套模板”的 PPT。

### 不适合谁

它不适合：

- 只想快速做一页漂亮图的人；
- 想要完全自动一键出片的人；
- 只需要网页演示、不需要 PPT 编辑的人；
- 不想做人工审阅的人；
- 不想看任何中间过程的人；
- 不愿意为质量付出流程成本的人。

如果你只想快速得到一个看起来不错的结果，模板型 PPT 工具或 HTML 演示工具可能更合适。

### 快速安装

仓库发布后，可以作为 Skill 安装：

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell/tree/main/planners-ppt-hell --skill planners-ppt-hell
```

也可以 clone 仓库后，只复制 Skill bundle 目录到本地 skills 目录：

```bash
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git /tmp/planners-ppt-hell
cp -R /tmp/planners-ppt-hell/planners-ppt-hell ~/.claude/skills/planners-ppt-hell
```

然后对 agent 说：

```text
Use planners-ppt-hell to turn this Markdown proposal into a review-gated editable PPT.
Start from content extraction, then show me the layout review page before generating SVG pages.
```

### 典型流程

初始化项目：

```bash
python scripts/init_svg_project.py path/to/project source.md
```

查看当前状态：

```bash
python scripts/pptflow.py path/to/project status
python scripts/pptflow.py path/to/project next
```

CONTENT 和 PLAN 完成后，生成版式审阅页：

```bash
python scripts/estimate_layout_capacity.py path/to/project
python scripts/generate_layout_html.py path/to/project
python scripts/review_server.py path/to/project
```

进入视觉审阅时，只生成当前批次：

```bash
python scripts/pipeline_gate.py path/to/project batch-svg-ready --batch BATCH_ID
python scripts/render_svg_png.py path/to/project/_internal/02_svg_source --manifest path/to/project/_internal/00_project/page_manifest.json --batch BATCH_ID
python scripts/validate_svg_layout.py path/to/project/_internal/02_svg_source --manifest path/to/project/_internal/00_project/page_manifest.json --batch BATCH_ID --output path/to/project/_internal/04_validation/validation_summary.json
python scripts/generate_review_html.py path/to/project --batch BATCH_ID
python scripts/review_server.py path/to/project
```

只通过控制器导出：

```bash
python scripts/pptflow.py path/to/project export
```

正式流程里不要直接调用 `native_svg_to_ppt.py`。

### 品牌与署名

过程页、审阅页、校验页、项目文档和仓库页面可以展示：

```text
Planner's PPT Hell © 2026 阿祖不看 TVC · demyth.info
```

默认情况下，最终客户交付物不会包含这条署名。除非用户明确要求，Skill 不应该把品牌信息加到导出的 PPT 页面、最终 SVG、PNG 或客户可见内容里。

---

## English

Planner's PPT Hell is an open-source Skill created by **阿祖不看 TVC**.

It started from a simple observation: large models are surprisingly good at writing SVG. If a slide can be described as SVG, and SVG can be converted into editable PowerPoint shapes, then an agent should be able to turn real proposal copy into editable PPT pages.

The hard part is not drawing one nice page. The hard part is making the model slow down, think page by page, preserve the meaning of the copy, accept human feedback, fix real visual problems, and only export when the deck is actually usable.

That is what this Skill does.

- Xiaohongshu: 阿祖不看 TVC
- Website: <https://demyth.info>
- Email: <Lawyif@163.com>

## What This Is

Planner's PPT Hell is not a one-click template generator.

It is a semi-automatic PPT production workflow for people who care about copy fidelity, slide logic, editable output, and review control.

The agent does the exhausting work:

- turns source copy into structured page content;
- thinks through layout direction before drawing;
- generates SVG pages and PNG previews;
- validates SVG/PPT compatibility;
- shows local HTML review pages for human feedback;
- converts approved SVG pages into editable PowerPoint.

The human still makes the important calls:

- whether the page logic is right;
- whether the visual direction works;
- whether a suggested change is worth applying;
- whether the deck is ready to export.

The core rule is simple:

> The model may draft, revise, and self-check. It may not approve itself.

## Why It Exists

Most AI PPT workflows fail in predictable ways.

They can make something attractive, but they often force the content into a template. They can generate HTML decks, but HTML is hard for colleagues, managers, and clients to edit. They can produce many pages quickly, but when asked to do 20 or 30 pages at once, the model often becomes lazy: every page becomes thinner, more generic, and less thoughtful.

Planner's PPT Hell is built around the opposite idea.

It deliberately makes the process slower.

It forces the agent to stop at key moments:

1. first to understand and preserve the copy;
2. then to design the layout direction;
3. then to generate only a batch of SVG pages;
4. then to wait for human visual review;
5. finally to export editable PPT only after the gates pass.

This is why the name includes "Hell." It is not magic. It is a controlled production line. The model suffers a little, the user suffers a little, and the tokens suffer too, but the result is much closer to a deck that can survive real-world revision.

## How It Works

Planner's PPT Hell moves through five controlled states:

1. **CONTENT** - preserve the source text and create structured page content.
2. **PLAN** - decide page logic, wireframes, copy handling, and layout direction.
3. **DRAFT** - generate current-batch SVG pages and PNG previews.
4. **REVIEW** - collect real human visual feedback through a local review server.
5. **EXPORT** - export editable PPT only after every gate passes.

The workflow uses:

- a state controller;
- local HTML review pages;
- approval keys;
- SVG validation;
- PNG preview review;
- batch-by-batch human approval;
- editable SVG-to-PPT conversion.

## What Makes It Different

**It is SVG-first, not HTML-first.**  
The goal is not a pretty web presentation. The goal is editable PowerPoint.

**It reviews layout before drawing slides.**  
The agent must explain page structure, wireframes, copy compression, and asset needs before generating SVG.

**It separates model review from human approval.**  
Validator warnings and model self-review are internal evidence. Human review is the real gate.

**It avoids template worship.**  
The layout and design documents are not long rule books that force every page into the same mold. They are meant to make the model think: what is this page trying to do, what should the reader remember, and what is the simplest layout that carries that meaning?

**It keeps the output editable.**  
The final deck is a `.pptx`, not a locked image deck or a web-only artifact.

## Suitable For

Planner's PPT Hell is useful when:

- you are making proposal decks, consulting decks, strategy decks, or planning decks;
- the source copy is dense and the meaning matters;
- pages need to be reviewed and revised one by one;
- colleagues, leaders, or clients may need to edit the final PPT;
- you are willing to trade speed for control and quality;
- you want the model to think, not just decorate.

It is especially suitable for copy-heavy planning and consulting work where slides are similar enough to benefit from a process, but important enough that blind templating is not acceptable.

## Not Suitable For

This is probably not the right tool if you want:

- a quick decorative one-page slide;
- a fully automatic "make me a deck" button;
- a web presentation instead of editable PPT;
- a deck with no human review;
- a workflow that hides all intermediate decisions;
- a lightweight tool that never asks you to inspect anything.

If you only need something that looks good fast, a template-based PPT or HTML presentation tool may be better.

## 30 Second Install

After this repository is published, install it as a Skill:

```bash
npx skills add https://github.com/thePlannerIvan/planners-ppt-hell/tree/main/planners-ppt-hell --skill planners-ppt-hell
```

Or clone the repository and copy only the Skill bundle directory into your local skills directory:

```bash
git clone https://github.com/thePlannerIvan/planners-ppt-hell.git /tmp/planners-ppt-hell
cp -R /tmp/planners-ppt-hell/planners-ppt-hell ~/.claude/skills/planners-ppt-hell
```

Then ask an agent:

```text
Use planners-ppt-hell to turn this Markdown proposal into a review-gated editable PPT.
Start from content extraction, then show me the layout review page before generating SVG pages.
```

## Typical Workflow

Initialize a project:

```bash
python scripts/init_svg_project.py path/to/project source.md
```

Check the current state:

```bash
python scripts/pptflow.py path/to/project status
python scripts/pptflow.py path/to/project next
```

Generate layout review after CONTENT and PLAN are ready:

```bash
python scripts/estimate_layout_capacity.py path/to/project
python scripts/generate_layout_html.py path/to/project
python scripts/review_server.py path/to/project
```

For visual review, generate only the current batch:

```bash
python scripts/pipeline_gate.py path/to/project batch-svg-ready --batch BATCH_ID
python scripts/render_svg_png.py path/to/project/_internal/02_svg_source --manifest path/to/project/_internal/00_project/page_manifest.json --batch BATCH_ID
python scripts/validate_svg_layout.py path/to/project/_internal/02_svg_source --manifest path/to/project/_internal/00_project/page_manifest.json --batch BATCH_ID --output path/to/project/_internal/04_validation/validation_summary.json
python scripts/generate_review_html.py path/to/project --batch BATCH_ID
python scripts/review_server.py path/to/project
```

Export only through the controller:

```bash
python scripts/pptflow.py path/to/project export
```

Do not call `native_svg_to_ppt.py` directly in a formal workflow.

## Brand And Attribution

Process HTML pages, local review pages, validation dashboards, project documentation, and repository pages may display:

```text
Planner's PPT Hell © 2026 阿祖不看 TVC · demyth.info
```

Final customer deliverables do not include this credit by default. The Skill should not add branding to exported PPT pages, final SVG slides, PNG deliverables, or client-facing slide content unless the user explicitly asks for it.

## Directory Structure

```text
planners-ppt-hell/
├── README.md
├── LICENSE
├── NOTICE
├── TRADEMARK.md
├── COMMERCIAL.md
├── SECURITY.md
└── planners-ppt-hell/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    ├── references/
    │   ├── page_content_contract.md
    │   ├── layout_plan_contract.md
    │   ├── page_manifest_contract.md
    │   ├── 03_style_system.md
    │   ├── 04_svg_rules.md
    │   ├── 05_layout_taxonomy.md
    │   └── 06_quality_checklist.md
    └── scripts/
        ├── pptflow.py
        ├── pipeline_gate.py
        ├── review_server.py
        ├── generate_layout_html.py
        ├── generate_review_html.py
        ├── validate_svg_layout.py
        └── native_svg_to_ppt.py
```

## Open Source And Commercial Use

This repository is released under **GNU AGPL-3.0**.

- You may use, study, modify, and redistribute the open-source version.
- Modified versions must keep the same license obligations.
- If you deploy a modified version as a network service, users must be able to receive the corresponding source code.
- The project name, author identity, and official branding are not licensed for impersonation.

Commercial extensions, private workflow integrations, template customization, and closed-source commercial licensing are available separately. See [COMMERCIAL.md](./COMMERCIAL.md).

## Author

Created and maintained by **阿祖不看 TVC**.

- Xiaohongshu: 阿祖不看 TVC
- Website: <https://demyth.info>
- Email: <Lawyif@163.com>

## License

AGPL-3.0 © 2026 阿祖不看 TVC.
