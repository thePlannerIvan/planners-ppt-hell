# `editorial-archive` 视频画面风格规范（四域 × 独奏/群像节奏矩阵）

本规范定义 `planners-ppt-hell` 视频画面路线的旗舰视觉系统 **`editorial-archive`（瑞士编辑档案）**。它把口播视频中常见的四类信息形态——**文字凸显、模型构建、图文混排、图片为主**——统一在同一套暖纸张底色、字体阶级、工程发丝网格与预埋动效契约之下，并通过 **Solo（独奏极简）/ Multi（群像展开）** 两档密度呼吸阀控制全片节奏。

- **风格 Token 唯一真源**：`video-craft/visual/themes/editorial-archive/tokens.css`（通过 `python scripts/style/theme_tokens.py show editorial-archive` 读取）
- **预埋动效唯一契约**：`video-craft/references/svg-animation-contract.md`（与 `video-craft/visual/assets/svg-anim-engine.js` 严格配套）

---

## 0. 多模态参考图库（制作前必看）

当前主流模型均具备多模态看图能力。**在动手写本风格的 SVG 之前，用看图工具读取以下随包参考图**，对齐真实的版式呼吸感、字重反差与构件细节，不要只凭文字脑补：

| 类别 | 随包参考图路径（相对本文件 `../../assets/video_style_references/editorial-archive/`） | 观察重点 |
|---|---|---|
| **整套 7 屏实测样板（必看）** | `prototype_7_beats_contact_sheet.png` | 7 屏并排的明暗节奏（5 屏暖纸 + 1 屏深炭墨反转 + 1 屏单图独奏）、左侧 `x:0..600` 留人像、四域切换与 `Solo / Multi` 密度呼吸 |
| **域 1：文字凸显（Multi 三段式）** | `domain-1-text-focus-pin05.png` | 暖灰纸底、左侧等宽编号列、横向发丝分割线、克制的高光色块 |
| **域 1：文字凸显（Solo 巨字独奏）** | `domain-1-text-focus-solo-pin19.jpg` | 超大号衬线与粗黑无衬线混排、椭圆圈注、大面积留白呼吸 |
| **域 1：文字凸显（胶囊展开动效）** | `domain-1-slot-expand-pin26-f03.jpg` | 短语中间嵌入几何胶囊插槽（`slot-expand`），把左侧词推向右边 |
| **域 2：模型构建（正交工程节点）** | `domain-2-model-build-pin03.webp` | 双线表头工程节点卡、`1px` 正交折线、等宽角标与步骤回路 |
| **域 2：模型构建（层级分支树）** | `domain-2-model-tree-pin16.png` | 从左向右生长的 `pathLength="1"` 正交分支树与虚线聚焦框 |
| **域 3：图文混排（编辑拼贴）** | `domain-3-editorial-mix-pin12.png`、`domain-3-editorial-mix-pin32-f02.jpg` | 衬线斜体主标题、左侧编号论点卡、右侧微倾拍立得相纸与手绘朱砂红圈注箭头 |
| **域 4：图片为主（Multi 档案台）** | `domain-4-image-archive-pin15-s01.jpg`、`domain-4-z-stack-drop-pin28-f03.jpg` | 右侧阶梯文件夹标签、四角 L 型裁切线、多张拍立得 Z 轴错落叠放（`z-stack-drop`） |
| **域 4：图片为主（Solo 单图独奏）** | `domain-4-image-archive-solo-pin30.jpg` | 全台只放一张真实原件大图、顶部半透明胶带、右下角单行打字机档案签，`≥65%` 纯净留白 |

---

## 1. 全局统一脊柱（Global Spine）

无论单屏属于哪个功能域、采用独奏还是群像密度，全片所有 SVG 必须共享以下视觉脊柱：

### 1.1 画布分区与安全边界（`1920 × 1080`）

| 区域 | 坐标范围 | 规则 |
|---|---|---|
| **左侧人物留白窗**（`over-person` 模式） | `x: 0 .. 600, y: 0 .. 1080` | 保持干净底色或透明；在 `x = 620` 处画一条 `1px` 垂直工程发丝分割线（`#D6D1C7`），顶端与底端配 `8px` 十字准星 `+` |
| **右侧主视觉舞台** | `x: 620 .. 1860, y: 56 .. 940` | 所有核心图形、卡片、照片、模型落在此处（宽 `1240px`，高 `884px`） |
| **满屏替换模式**（`replace` 模式） | `x: 96 .. 1824, y: 56 .. 940` | 不留人物窗时，按 12 栏瑞士网格居中展开 |
| **顶部常驻页眉轨（Running Header）** | `y: 56 .. 92` | 左端 `[01 // DOMAIN · MODE]` 等宽胶囊，中段一句章节微注，右端 `01 / 07` 页码 + `1px` 满幅水平分割线 |
| **底部字幕安全区（`captionSafe`）** | `y: 940 .. 1080` | **严禁放任何正文、卡片或印章**；只允许极浅的页脚发丝线或十字准星 |

### 1.2 调色板与重音铁律（6 条反杂乱护栏）

| 语义角色 | Token | 色值 | 严格使用边界 |
|---|---|---|---|
| **主舞台暖纸底** | `--surface` | `#F2EFE9` | 全片 `≥ 80%` 的页面以此为底，营造温润纸质档案感 |
| **卡片凸起面 / 相纸白** | `--surface-2` | `#FAF8F4` | 拍立得边框、工程节点卡、核心定义卡底色 |
| **次级插槽灰底** | `--surface-3` | `#E6E1D6` | 标签槽、未激活模块底色 |
| **炭墨主字 / 反转深底** | `--text` | `#181715` | 主标题、反白强调块、**以及全片唯一重音反转屏（Spotlight）的主背景** |
| **次级正文墨** | `--text-2` | `#4A4742` | 副标题、卡片说明 |
| **静音档案灰** | `--text-mute` | `#6E6A63` | 编号、来源路径、SHA-256 校验码（对 `#F2EFE9` 满足 `≥ 4.5:1` WCAG AA） |
| **结构发丝线** | `--rule` | `#D6D1C7` | `1px` 网格线、分割线、十字准星 |
| **编辑朱砂砖红（唯一主色）** | `--accent` | `#C8553D` | **低饱和度印刷砖红**（绝不用刺眼的荧光红 `#E43D1E`）；只用于单处圈注、印章或核心回流线 |
| **氧化荧光黄（辅助高光）** | `--accent-yellow` | `#E9C46A` | 仅用于词语背后的荧光笔底块（`highlight-sweep`）或顶部半透明胶带 |

**6 条反杂乱与防刺眼铁律（Anti-Clutter Guardrails）：**

1. **严禁满屏高饱和红底**：哪怕是章节转折的重音反转屏（Spotlight），也**绝不允许**用红色铺满背景。反转屏一律用**深炭墨色（`#181715`）作主底**，朱砂砖红 `#C8553D` 面积不得超过舞台的 **12%**。
2. **全片必须有呼吸感（Solo 屏占比 ≥ 30%）**：一套 6~8 屏的方案里，至少要有 **2 屏**采用 `Solo（独奏极简）` 模式，给观众眼睛留白，不能屏屏都是塞满 3~4 张卡片的 `Multi` 屏。
3. **装饰件克制配额**：胶带、印章、虚线框、角标在一屏之内**最多选 2 种**；`Solo` 独奏屏里禁止堆砌无关侧边栏、多余印章或背景网格。
4. **单屏最多 1 处朱砂砖红焦点**：一屏之内只能有 **1 个**核心痛点或回流箭头用 `#C8553D`，其余律用炭墨黑 `#181715` 与纸灰 `#D6D1C7`。
5. **预埋复合子元素动效**：严禁把整屏做成一个死图层。按口播递进拆成 `#<page_key>-anchor` + 1~4 个 `data-step="N" data-anim="..."` 复合动效组，并在组内写好 `.anim-*` 子元素类名。
6. **坐标烘死、绝不在 `<g data-step>` 上挂定位 `transform`**：所有 `<g data-step>` 子元素的坐标直接写成画布绝对坐标，防止动画引擎设置 `transform` 时把元素打回 `(0,0)`。

---

## 2. 四大功能域 × `Solo / Multi` 双密度矩阵

动笔前先判断这一屏回答什么问题（选**功能域**），再看它是「只立一个核心重音/单张铁证」还是「展开多步结构」（选 **`Solo` 或 `Multi`**）：

| 功能域 | `Solo` 独奏极简模式（留白 ≥ 60%，1~2 个聚焦步） | `Multi` 群像展开模式（结构化对比/流程，3~4 个递进步） |
|---|---|---|
| **域 1：文字凸显 (`text-focus`)** | **巨字宣言 / 章节反转屏**：单句核心金句或超大斜体命令名（`110~136px`）+ 行内几何胶囊插槽展开（`slot-expand`）或单条荧光笔横扫（`highlight-sweep`）。深炭墨底 `#181715` 或纯暖纸底，零多余边框。 | **编号解剖列表（2~3 项）**：左侧 `01 / 02 / 03` 等宽编号列 + 横向发丝分割线 + 每行右侧配一个极简微图解（如进度撞墙条、发散虚线），痛点项用黑底反白块（`bar-wipe`）。 |
| **域 2：模型构建 (`model-build`)** | **核心公式 / 单公理放大**：舞台中央只放一张精雕细琢的输入→输出黑盒卡或 `A × B = C` 机制卡片，四周 `≥ 65%` 纯净留白，只走一次 `pop-card` + `draw-stroke`。 | **正交闭环 / 分支拆解树**：`40×40` 极淡工程网格之上，3~4 个双线表头工程节点卡（`pop-card`）+ 正交折线/回路箭头（`draw-stroke` + `pathLength="1"`）+ 重点叶子节点盖章（`stamp-in`）。 |
| **域 3：图文混排 (`editorial-mix`)** | **单论点 × 单图对撞**：左半单句超大号结论（配荧光笔划重点 `highlight-sweep`），右半单张微倾真实档案图（`z-stack-drop`），中间仅用一支手绘朱砂红箭头（`draw-stroke`）咬合。 | **编辑部证据墙**：顶部斜体大标题 + 左侧 2~3 张编号论点卡（`pop-card`）+ 右侧拍立得相框叠打字机 SHA-256 核验条 + 手绘红圈与箭头把文字指令与图片铁证连起来。 |
| **域 4：图片为主 (`image-archive`)** | **单张大图镇场（Hero Evidence Spotlight）**：全台只放 **1 张**高分辨率核心历史原图/关键截图（占舞台面积 `55%~65%`），配微倾拍立得白边 + 顶部一贴半透明黄胶带 + 右下角单行打字机档案编号条。**禁止加文件夹侧栏、禁止加多余印章**，留足 `≥ 60%` 纯净桌面留白。 | **多图档案台（2~4 张）**：四角 L 型取景裁切线 + 右侧阶梯式文件夹标签 + 2~4 张拍立得按口播顺序依次从上方带阴影落桌（`z-stack-drop`）+ 底部展开一条打孔档案凭条（`paper-unroll`）。 |

---

## 3. 标准 SVG 预埋动效构件模板

每页 SVG 必须按 `#<page_key>-anchor`（第 0 帧常驻层）与 `#<page_key>-step-1..K`（按口播触发的复合动效层）组织，内部挂好 `video-craft/references/svg-animation-contract.md` 规定的语义子选择器（`.anim-*`）：

### 构件 A：双层遮罩擦除块（`data-anim="bar-wipe"`，用于 `text-focus` 痛点/金句）

```xml
<g id="beat-01-step-3" data-step="3" data-anim="bar-wipe">
  <!-- 阶段 1：朱砂砖红先导色块与黑底反白块先后擦入 -->
  <rect class="anim-bar" x="660" y="640" width="12" height="130" fill="#C8553D"/>
  <rect class="anim-mask" x="672" y="640" width="1148" height="130" fill="#181715"/>
  <!-- 阶段 2：主副文案错位滑入 -->
  <text class="anim-title" x="704" y="702" fill="#FAF8F4" font-family="Noto Sans SC" font-size="38" font-weight="700">03  只给浓缩摘要，不敢确定真假</text>
  <text class="anim-sub" x="704" y="744" fill="#D6D1C7" font-family="JetBrains Mono" font-size="18">[ ? UNVERIFIED SUMMARY BLACKBOX ]</text>
</g>
```

### 构件 B：拍立得物理落桌卡（`data-anim="z-stack-drop"`，用于 `image-archive` / `editorial-mix`）

> **注意**：`<g data-step>` 自身不写 `transform`；拍立得的微倾角度写在内部 `<g class="card-tilt" transform="rotate(-1.5 1240 500)">` 上！

```xml
<g id="beat-05b-step-1" data-step="1" data-anim="z-stack-drop">
  <g class="card-tilt" transform="rotate(-1.5 1240 500)">
    <!-- 阶段 1：偏移阴影在落桌瞬间收紧 -->
    <rect class="anim-shadow" x="870" y="214" width="760" height="580" fill="rgba(24,23,21,0.12)"/>
    <!-- 阶段 2：拍立得白边相纸落桌 -->
    <rect class="anim-frame" x="860" y="200" width="760" height="580" fill="#FAF8F4" stroke="#181715" stroke-width="1.5"/>
    <!-- 阶段 3：真实照片轻微缩放显影 -->
    <image class="anim-photo" href="../00_project/assets/HD-002_early-years-shed_1903_image.jpg" x="884" y="224" width="712" height="460" preserveAspectRatio="xMidYMid slice"/>
    <!-- 阶段 4：顶部半透明胶带贴合 + 底部打字机图注浮现 -->
    <rect class="anim-tape" x="1170" y="184" width="140" height="32" fill="rgba(233,196,106,0.78)" stroke="#181715" stroke-width="1"/>
    <text class="anim-caption" x="888" y="726" fill="#181715" font-family="Noto Sans SC" font-size="24" font-weight="700">1903 密尔沃基起家木屋原件</text>
    <text class="anim-caption" x="888" y="756" fill="#6E6A63" font-family="JetBrains Mono" font-size="15">ARCHIVE // HD-002 · 1000×750 RAW</text>
  </g>
</g>
```

### 构件 C：双线工程节点卡 + 路径自绘（`data-anim="pop-card"` + `draw-stroke`，用于 `model-build`）

```xml
<g id="beat-04-step-1" data-step="1" data-anim="pop-card">
  <rect class="anim-bg" x="680" y="250" width="520" height="170" fill="#FAF8F4"/>
  <rect class="anim-border" x="680" y="250" width="520" height="170" fill="none" stroke="#181715" stroke-width="1.5" pathLength="1"/>
  <rect class="anim-header" x="680" y="250" width="520" height="36" fill="#181715"/>
  <text class="anim-badge" x="696" y="274" fill="#FAF8F4" font-family="JetBrains Mono" font-size="15" font-weight="700">[STEP // 001]  /research</text>
  <text class="anim-title" x="704" y="334" fill="#181715" font-family="Noto Sans SC" font-size="28" font-weight="700">模糊主题先搜集一手源</text>
  <text class="anim-body" x="704" y="376" fill="#4A4742" font-family="Noto Sans SC" font-size="20">原始网页、图片、PDF 落盘并记下哈希</text>
</g>
```

完整的 8 种 `data-anim` 子元素选择器清单、缓动曲线与时间轴绑定规则，统一见 `video-craft/references/svg-animation-contract.md`。
