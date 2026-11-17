# dark-titanium-cockpit — 瑞士先锋排印与战略驾驶舱模板包（SPEC）

> **设计哲学**：源自瑞士国际主义平面排版（Swiss International Typographic Style）与前卫新野兽派（Neo-Brutalist Typographic Cockpit）。彻底摒弃泛滥而碎裂的 SaaS 灰色 Bento 胶囊框堆砌，回归**极端字阶对比（145px vs 18px）**、**50%–70% 负空间呼吸感**、**细发丝线网格（1.5px Razor Hairline）**与**单点高伏特破局色（#E2F827）**。

---

## 一、 色彩系统契约（见 tokens.css）

全套模板严格遵守「双基底 + 单一破局魂」色彩法则，严禁杂色混用：

| 角色 | CSS 变量 | 色值 | 叙事功能与使用铁律 |
| :--- | :--- | :--- | :--- |
| **曜石暗调画布（主舞台）** | `--bg-obsidian-dark` | `#0C0D11` | 承载深度思考页，沉稳深邃。四周保留 60%–70% 负空间。 |
| **冷钛灰白画布（高透舞台）** | `--bg-titanium-light` | `#ECEEF2` | 承载多维数据、网格与高可读性议程，清爽透亮，白底纯黑字。 |
| **电光酸性黄（唯一破局色）** | `--accent-electric-lime` | `#E2F827` | **全套 Deck 唯一的签名撞色**。在暗底作为高能信号灯，在亮底作为荧光记号笔。 |
| **高能全版破局底色（原爆点）** | `--bg-puncture-lime` | `#E2F827` | **仅在全案特定高能页（如交付范围与阶段交接）整版铺满**，作为视觉原爆点。 |
| **建筑发丝分割线** | `--border-hairline-dark` / `--border-hairline-light` | `#252733` (暗) / `#D1D5DB` (亮) | 统一 1.5px 极细线，严禁加粗，严禁粗重边框。 |

---

## 二、 1920×1080 空间网格与排印阶梯（见 tokens.css）

- **安全边界（Safe Margins）**：左右统一留白 100px（有效内容区 x=100..1820，宽 1720px）。
- **天际线母版（Skyline Header）**：统一位于 y=80px，包含 LOGO 与右侧等宽标签。
- **四角十字准星（Cross Markers）**：四角关键网格交界处保留 1.5px 细线坐标（如 100,80 / 1820,1000），标定仪器感。
- **排印字阶（Scale Ladder）**：
  - **巨幅陈述**：145px（Cover）、132px（Broken Syllable）、110px（Poster）
  - **纤细背景大数**：320px（16:9 / Ghost Slender Numbers，浅灰发丝）
  - **数据巨数**：130px（如 85.6M Hero KPI, +82% Multiple）
  - **大栏目/议程标**：74px（Scope of Work / Agenda / Playlist）
  - **主张断言/大字行**：48px
  - **正文大字/二级标题**：30px
  - **说明与事实段落**：20px
  - **法定易读底线**：**全页任何标注、标签、来源严禁低于 12px**。

---

## 三、 32 套精炼版式图元选型指南（7 大版式家族）

全套 32 套生产级模板划分为 7 大版式家族，杜绝形式同质化：

### 1. 封面与先锋大字宣言（p01 · p03 · p05）
- **p01_master_brutalist_cover**：曜石黑金先锋封面（145px 三层西文标题 + 右侧荧光绿方块破局）
- **p03_brutalist_parenthetical_manifesto**：打断式超粗黑体与战役信条（深黑胶囊括号横插打断大词）
- **p05_radial_sunburst_manifesto**：几何辐射能量场宣言（同心圆弧与 8 轴径向辐射能量场线）

### 2. 目录与执行时间轴（p08 · p09 · p11）
- **p08_right_aligned_index_ledger**：极右对齐精细目录账本（左叙事导言 + 右 8 行水平分割目录）
- **p09_creative_agenda_pillar**：结构化议程与垂直字柱（垂直字柱 + 细线横向结构行）
- **p11_alternating_horizontal_timeline**：交错双向水平时间轴（上下错落时间节点节奏）

### 3. 多列立柱与模块化卡片（p12 · p13 · p14 · p15 · p17 · p18）
- **p12_monumental_4column_slender**：顶天立地纤细巨数四栏（4 根发丝线通顶，320px 纤细高数）
- **p13_threepillar_mechanism_void**：三柱虚空留白机制矩阵（三根贯通立柱，微型卡片锚定逻辑）
- **p14_escalating_stat_grid_pillars**：三阶递增阶梯式网格立柱（三根渐进高度框架柱，第三柱穿透）
- **p15_circular_step_columns**：四阶圆形步骤胶囊悬浮立柱（四列流程推演柱）
- **p17_editorial_quote_2x2_wireframe**：大号名言 + 2x2 极简线框矩阵（理念引述 + 四维视窗）
- **p18_dual_tier_mega_numeral**：双阶巨型章节号阶跃排版（双层巨号阶跃）

### 4. 数据账本与高密财务台账（p20 · p21 · p23）
- **p20_high_density_financial_ledger**：高密运营数据账本与战略叙事（高密度多列财务审计矩阵）
- **p21_digits_data_grid**：数据金融建筑网格与亮黄方块（严谨金融网格 + 亮黄大数字实心块）
- **p23_diptych_polar_split**：双联版面黑白双子极性对撞（左右整版黑白极性对撞）

### 5. 仪表盘、图表与进度刻度（p25 · p26 · p27 · p28 · p31 · p32 · p33）
- **p25_precision_metric_gauge_spectrum**：高精度百分比刻度进度条仪表（多段刻度滑条）
- **p26_barcode_pill_metric_array**：20 段条码刻度指标阵列（硬核工业条码刻度药丸）
- **p27_horizontal_gradient_fade_ledger**：水平渐变羽化柱状图（渐变羽化进度条 + 百分比清单）
- **p28_horizon_rounded_ascending_bars**：地平线圆角递增柱状图（水平阶梯柱条）
- **p31_organic_spline_wave_matrix**：正弦波峰山脉趋势图（正弦山脉波形趋势）
- **p32_human_pictogram_penetration_matrix**：人形象形图渗透率矩阵（人群渗透象形矩阵）
- **p33_geometric_dot_matrix_grid**：几何波点阵列与单点高亮决策（矩阵波点 + 荧光点决断）

### 6. 摄影展台、标本矩阵与多图拼贴（p35 · p38 · p39）
- **p35_editorial_multigrid_moodboard**：杂志编辑感多格情绪板（多格画报式拼贴网格）
- **p38_horizontal_triptych_gallery_strip**：水平三联画展台长廊（3 联宽幅横屏照片 + 下白卡说明）
- **p39_monolith_pedestal_showcase_strip**：横向 4 联单品展台条（4 根垂直立柱展台 + 上图下参数）

### 7. 沉浸式图文驾驶舱与遥测系统（p40 · p41 · p43 · p44 · p48 · p49 · p52）
- **p40_monolithic_numeral_accordion_photo**：巨数字立柱建筑背衬屏（4 手风琴列 + 1 列巨石建筑背衬）
- **p41_cybernetic_portrait_split_cockpit**：赛博侧脸肖像分屏驾驶舱（左侧大图视窗带 HUD 准星 + 右双层仪表卡）
- **p43_horizon_panoramic_strip_sunken_ledger**：宽幅地平线全景与下沉文本舱（顶部 1720×390 全景带 + 下 4 列账本）
- **p44_edge_infiltrated_hardware_hero**：右缘穿入式硬件产品大屏（左规格阶梯 + 右破界侵入大图带标尺）
- **p48_scope_big_arrow_break**：新野兽派高能交付看板与巨型箭头（全屏高饱和荧光绿看板）
- **p49_fluorescent_lime_blast_screen**：高饱和赤红原爆点数据屏（全屏高能赤红）
- **p52_aura_horizon_milestone**：柔和光晕与弧线抛物线里程碑（抛物线光晕地平线）
