# 开始与恢复

目标：把机械准备交给工具，让模型获得可继续制作的材料与当前状态。

**在 Skill 根目录运行，三个路径参数都给绝对路径**（`<project>`、`--source`／`--assets`、`--plan`）。相对路径会按当前工作目录解析，不对时得到的报错会指向一个看起来不存在的路径——它会让你以为材料丢了，其实是路径基准不对。用已具备 `requirements.txt` 依赖的 Python。

## 两条路线各一条命令

幻灯片路线先按 `02_content_stage.md` 判断内容入口。原始资料尚需理解、组织或展开时，先调用 `planners-bypage`，接收 `deliverable/by-page.md` 与资产后再初始化；不要把 PDF、表格或资料目录直接传给只接受 Markdown/Word 的 `--source`。已有制作项目则恢复原项目，不重新初始化。

```bash
# 幻灯片：有源文档
python scripts/init_svg_project.py <project> --source <source.md|source.doc|source.docx>

# 视频画面：上游交了画面契约
python scripts/init_svg_project.py <project> --assets <包>/assets --plan <包>/visual-plan.json

# 任何路线，恢复与推进
python scripts/orchestrate/ppt_pipeline.py <project> next --json
```

两条路线互斥，同时给 `--source` 和 `--assets` 直接报错。已有项目只运行 `next`；旧版项目不能在原地混用新控制器，继续使用归档旧 Skill 完成，或在新目录从材料重新开始并人工核对旧反馈。

### 幻灯片路线：`--source`

初始化原子复制源文，登记本地图片，内容底稿由你接着整理（`02_content_stage.md`）。

### 视频画面路线：`--assets` + `--plan`

图片是一平铺文件夹里的散图，画面契约由上游直接交进来（`deliverable/visual-plan.json`，contract 5.0）。初始化在边界上把它适配成 `page_content.json`：

- `screens[].screen_id` **原样成为 `page_key`**——不改名、不重新编号；
- 上屏内容进 `content`，按来源分组（正文／必须出现的内容／原样标签／花字），认不出的字段当场点名报出来由你裁决；
- 理由与来源（`question`／`must_express`／`evidence`／`beat_id`／样张说明）进 `notes`——**它们只用来理解画面，不上屏**。

不写 `source.md`，也不重推底稿。这条路线的完整任务在 `03_video_route.md`。

**`<包>/assets` 是交付包，不是作者的素材库。** 它恰好等于契约引用的那几张图；文件夹里每张图都必须被某一屏引用，否则初始化报错并点名——这条规则防的是静默丢图。撞上它时，**正确的解法是指向交付包**。作者的素材库不是交付包，**不要为了过闸去删源素材**。

## 开局一次问清，别的都别问

**幻灯片路线** —— 读完材料、写完内容底稿后，一次性把这三件问清：

1. **视觉来源** — 自主设计／用模板库里的模板／给一份视觉参考／新建严格品牌模板。四条路线的命令、产物与完成标准见 `01_template_intake.md`。
   **不要静默默认自主设计。** 库里有一个内置模板，用户可能手上有参考成品或自己的品牌 PPTX——这三件事都会显著改变成品，而它们都不会自己冒出来。
   **「用参考」和「建参考」分开问**：只是想借一个方向就用库里的模板或渲染过的参考件；要从用户自己的 PPTX 里提出可复用模板，那是另一件重活，单独确认。
2. **画幅** — 默认 16:9，确认一次即可（`04_svg_stage.md`）。
3. **图片** — 这套需不需要配图、要什么类型、大概哪几页、是否已有现成资产。见 `02_content_stage.md`。

**视频画面路线** —— 接手时一次性问清两件：

1. **风格** — 报 2–3 个候选给作者挑（风格库里的主题 + 色与字型预览），见 `03_video_route.md`。**不要静默默认。**
2. **画幅** — 同上，默认 16:9。

用户已经明确说了的就直接执行，不重复问。除此之外只在导入异常、源资料缺失或影响商业结论的歧义上询问。

## next 给出什么

它给出 `CONTENT`、`CREATE`、`VISUAL_REVIEW`、`EXPORT`、`EXPORT_VERIFY` 或 `COMPLETE`，是**恢复提示**，不把模型拆成只能读白名单的小执行器：可以回看原文、图片、相邻页面和整套方向。

**两条路线的终态不同：**

| | 幻灯片路线 | 视频画面路线 |
|---|---|---|
| 中间状态 | CONTENT → CREATE ↔ VISUAL_REVIEW → EXPORT → EXPORT_VERIFY | CONTENT → CREATE ↔ VISUAL_REVIEW → COMPLETE |
| COMPLETE 的判据 | `final_deck.pptx` 存在且 hash 对得上，且导出后复核过 | 全部页面 `check` 无 error，**且整套审阅有作者提交的记录** |
| 交付物 | `final_deck.pptx` | `_internal/02_svg_source/<page_key>.svg` 全部页面（**不导出 PPT**） |

视频画面路线上**没有导出这一步**，所以 `EXPORT` / `EXPORT_VERIFY` 不会出现，`COMPLETE` 也不要求任何 PPTX。

## 完成标准

源文可读；或者（视频画面路线）交进来的契约与交付包已登记、每张图都有归属、**契约文件的 sha256 已记入项目状态**。图片路径有效。**路线与画幅已确认**；幻灯片路线另确认视觉来源，视频画面路线另确认风格。内容任务或恢复动作明确。

**`script_hash` 在这里核。** `script.md` 与 `visual-plan.json` 同在 `deliverable/` 里，顺着契约文件所在目录就找得到。不符报 **error 拦下**——工序是「做好画面 → 录人声 → 剪」，作者**对着画面录**，这里的核对是**唯一还来得及**的那一次；等到剪辑接手才发现，人已经录完了。契约文件本身被换过另报警告。真的找不到 `script.md` 时报「无法核对」，不报成功。

素材存在和 Schema 合法**不能**证明内容已被理解。
