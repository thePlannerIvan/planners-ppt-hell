# 幻灯片视觉来源与三步式多模态模板工作流（`01_template_intake.md`）

> 这一份管的是**幻灯片出口**的视觉身份从哪来。视频画面路线不走这里（见 `03_video_route.md`）。

---

## 一、 开局一步路由：直接选模板包 vs 从参考文件提取

读完材料、明确叙事结构后，按用户意图选择视觉来源（**只确认一次，用户已点名则直接执行**）：

| 模式 | 触发场景 | 执行动作 |
| :--- | :--- | :--- |
| **模式 1：选用内置双旗舰模板包（默认推荐）** | 用户未提供外部模板，或内容属于社媒种草/品牌全案/商业战略/产品分析 | - **社媒种草 / 品牌营销 / 内容代运营提案** → 选用 `agency-social-proposal`<br>- **商业分析 / 竞品拆解 / 产品战略 / 咨询报告** → 选用 `consulting-product-strategy`<br>执行：`python scripts/template/template_library.py apply <project> --template-id <id>` |
| **模式 2：当次即用提取（轻模式）** | 用户提供了参考 `.pptx` / `.pdf` / 页面截图，要求「按这个风格做本次 PPT」 | 走下方 **Step 1 → Step 2**，在 `_internal/00_project/template_pack/` 生成四件套后直接进入 `CREATE` 画页，**零人工审批打断** |
| **模式 3：沉淀入库提取（重模式）** | 用户明确要求「把这个 PPTX/PDF 提炼成以后长期复用的模板入库」 | 走下方 **Step 1 → Step 2 → Step 3**，经 `00_template_review.html` 审阅确认并命名后，`template_library.py publish` 入库 |

---

## 二、 三步式「多模态模板提取」工作流（取代旧八步机械流）

无论用户输入的是 `.pptx`、`.pdf` 还是图片目录，统一执行以下 3 步：

### Step 1 — 脚本一步预处理（`extract_template_pack.py`）
运行：
```bash
python scripts/template/extract_template_pack.py <source_path> --project <project_dir>
```
脚本自动完成两件事：
1. **全页视觉化**：将 `.pptx` / `.pdf` / 图片集渲染为 `_internal/00_project/template_visuals/page_001.png...` 与 `contact_sheet.png`，并对实际画面像素做主色/墨色/高饱和强调色聚类采样（`visual_palette_sampling`）。
2. **PPTX 深度事实提取（若输入为 `.pptx`）**：
   - 通扫 `slide_masters` + `slide_layouts` + `slides`（含嵌套 Group），将跨页复用的真实 Logo、角标、底纹去重提取到 `_internal/00_project/template_pack/assets/`（自动剔除单页内容配图与全屏截图包装页）；
   - 统计幻灯片上**实际可见元素**的填充色、描边色、文字色频与 1080p 归一化字号阶梯（自动识别并警告未使用的 Office 默认主题色 `#4F81BD` 等），输出 `_internal/00_project/template_pack/extraction_facts.json`。

### Step 2 — 多模态看图提炼四件套 + 渲染自检
1. **多模态看图**：查看 `template_visuals/contact_sheet.png` 与 5–8 张代表性 `page_NNN.png`，对照 `extraction_facts.json` 中的真实色频与字号分布。
2. **挑锚点图**：将 4–6 张最能代表封面、非对称拆解、框架图、表格/数据页的源页面 PNG 复制到 `template_pack/anchors/`。
3. **编写四件套**：
   - `tokens.css`：锁死 75:20:5 配色变量與字号阶梯；
   - `skyline_shell.svg`：复刻源文件的页眉/页脚/标题栏与 `assets/` 品牌标志位置；
   - `primitives/*.svg`：提炼 5–6 个核心内页版式原语骨架（去框化、零 Emoji、动态胶囊宽度）；
   - `SPEC.md`：写明坐标标尺、原语选型表与防翻车禁令。
4. **渲染自检**：
   ```bash
   python scripts/render_svg_png.py <project>/_internal/00_project/template_pack/primitives <project>/_internal/00_project/template_pack/previews
   ```
   多模态查看 `previews/full_deck_contact_sheet.png`，确认无文字重叠、无切字、无溢框。

### Step 3 — 分流「当次即用」或「审阅入库」
- **当次即用（模式 2）**：直接进入 `04_svg_stage.md` 开始逐页制作，每页根据叙事角色挑选 `template_pack/primitives/*.svg` 作为起点骨架。
- **审阅入库（模式 3）**：生成并打开 `00_template_review.html`（左侧展示 `anchors/` 源参考页，右侧展示 `previews/` 提炼出的天际线与原语预览图）。作者确认通过后运行：
  ```bash
  python scripts/template/template_library.py publish <project_dir> --template-id <id> --name "<模板名称>"
  ```
