"""审阅面：**这两份 surface 的内容**（业务），宿主生命周期全部归公共件。

本 Skill 有**两个**审阅面，它们是两个主体、不是一份画法的两处皮肤：

  · `visual`   —— 逐页看渲染图、逐页提交，模型只重出提交的那一页（`02_visual_review.html`）；
  · `template` —— 逐 Layout 看生产 canvas 与源模板证据，决定通过／舍弃／返修（`00_template_review.html`）。

**每一条面字段都是各自独立判的**（R10：审阅的粒度由产出方决定）—— 下面 `VISUAL` / `TEMPLATE`
两处都逐条写了理由，**不许把一面的结论抄给另一面**。它们唯一的共同点是"用同一个契约描述自己"：
面只声明契约那几个字段，宿主永不解释（R1）。

本文件只做四件事，别的都在 `planners-review-core`（契约校验器 / 宿主 / 桥）：

  1. `surface_document(root, name)` —— 写出这一份面的内容（页面在哪、被 serve 的是哪棵树、
     反馈写进哪个文件、盯哪些文件、唤醒说什么）。**这是业务，只有这里知道**；
  2. 建文档 → 交给模组落盘并校验；
  3. 起/复用/停宿主 —— 直接调模组，本文件**不再实现**（曾经和 video-craft 各一份，已经漂移过：
     僵尸判据、SIGKILL 升级；现在唯一实现在 `review-host.mjs`，Python 侧只是传输层）；
  4. `open_review` 里那点**业务前置**：缺件检查与 `--surface-only` 开关（在 `ppt_pipeline`）。

`dir` 为什么是项目根：两个审阅页都生成在项目根（`02_visual_review.html` / `00_template_review.html`），
而 visual 面要加载的渲染图在 `_internal/03_png_preview/`、上传件在 `_internal/05_review/uploads/`、
页内素材在 `_internal/02_svg_source/` 与 `_internal/00_project/source/assets/`；template 面的 canvas
在 `_internal/00_project/fidelity_template/`、源模板证据在 `_internal/00_project/template_visuals/`。
这几处的最近公共祖先是项目根，所以 `dir` 只能取项目根——把审阅页搬进子目录会改动项目契约里的
产物位置，不在这一轮里做。宿主仍然会做包含性校验（serve 的每个路径都必须落在 `dir` 的 realpath 子树里）。
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.planners_modules import resolve_module                    # noqa: E402

# 公共模组里唯一那份宿主生命周期。**模块解析走本 Skill 的适配器**（发布后按名字找兄弟目录），
# 再把它 scripts/lib 放上 sys.path —— 模组自己不需要知道谁在调它。
sys.path.insert(0, str(resolve_module('planners-review-core')/'scripts'/'lib'))
import review_host                                                 # noqa: E402

REVIEW = '_internal/05_review'
PROJECT_DIR = '_internal/00_project'

# ── 面一：页面审阅（逐页决定 + 逐页版本）────────────────────────────────────────
VISUAL = {
    'name': 'visual',
    'surface_rel': f'{REVIEW}/review-surface.json',
    'entry': '02_visual_review.html',
    # `feedback` / `watch` 相对 **surface 文件**（R2 的第二个基准）：同在 `_internal/05_review/`。
    'feedback_rel': 'feedback.json',
    # 草稿：和 `feedback` 分开的两个文件、两件事。`feedback` 是**决定**（人点了提交，
    # 模型按轮次收件）；`draft` 是**还没提交的草稿**（页面拿它做「刷新不丢」，模型不当它是收件）。
    # 曾经只有 feedback：于是「我改了东西」和「告诉模型可以动手」被绑成一个动作 ——
    # 不提交就只活在内存里，刷新即丢（真人反馈 2026-10-05）。
    'draft_rel': 'draft.json',
    'watch': ['snapshot.json'],
    'id': 'planners-ppt-hell/visual',
    'title': '整套页面审阅',
    'description': '逐页看实际渲染图，框选或写意见；每页可单独提交，模型只重出提交的那一页。',
    # 逐页审阅要人补图（换一张渲染图、贴一张截图）→ 声明上传能力。
    'capabilities': ['asset-upload', 'draft'],
    # 逐页：单位是 page_key，所以唤醒语带 `{unit}`；页面会用整句覆盖（自带决定）。
    'wake_text': '{unit} 已定；只重出这一页，其余页不要动。',
}

# ── 面二：模板审阅（整批决定 + 模板整体版本）────────────────────────────────────
# **与上面那条逐条不同，而且理由是各自判的**：
#   · 单位是 `layout_id` 不是 `page_key`；决定词表是 `pass`/`discard`/`revise` 不是 `approved`/`revise`；
#     对照物是**源模板页**，不是"这一页的上一版"；
#   · 返修一个 Layout ≠ 换一张图：要**重建模板**（canvas / registry 变）→ 旧审阅页整体作废，
#     所以这里**没有"原地换图"这件事**，也就没有逐单位唤醒；
#   · 页面上只有一个提交动作（`submit_batch` / `approve_all`），粒度天然是**整批**。
TEMPLATE = {
    'name': 'template',
    # 与它描述的两份产物（`template_feedback.json` / `template_review_snapshot.json`）同目录，
    # 于是下面两个相对名就是同目录文件名。
    'surface_rel': f'{PROJECT_DIR}/template-review-surface.json',
    'entry': '00_template_review.html',
    'feedback_rel': 'template_feedback.json',
    # 盯快照：重建模板会重写它（新 review_id）→ 开着的那一页**立刻自证过期**，
    # 而不是等人填完一整页决定、提交时才发现这一版已经不作数。
    'watch': ['template_review_snapshot.json'],
    'id': 'planners-ppt-hell/template',
    'title': '模板审阅',
    'description': '逐 Layout 看生产 canvas 与源模板证据，决定通过／舍弃／返修；整体一句反馈与模板命名。',
    # 模板审阅是只读对照 + 决定 + 命名，没有上传需求：声明 `asset-upload` 会广告一个不存在的入口。
    'capabilities': [],
    # 整批：单位是"这一批 Layout"，页面自己会整句覆盖成带决定的那句（见页面 `submitFeedback`）。
    'wake_text': '模板审阅已提交；按反馈重建模板，其余不要动。',
}

FACES = {face['name']: face for face in (VISUAL, TEMPLATE)}

# 向后兼容：visual 面那组名字继续存在（`ppt_pipeline` 与测试按它们取路径）。
SURFACE_REL = VISUAL['surface_rel']
HOST_STATE_REL = f"{REVIEW}/{review_host.HOST_STATE_NAME}"
PAGE_REL = VISUAL['entry']
FEEDBACK_REL = f"{REVIEW}/{VISUAL['feedback_rel']}"
DRAFT_REL = f"{REVIEW}/{VISUAL['draft_rel']}"
WAKE_LOG_REL = f"{REVIEW}/{review_host.WAKE_LOG_NAME}"
ID = VISUAL['id']
WAKE_TEXT = VISUAL['wake_text']


def describe(name='visual'):
    """取一份面的描述；名字不认识时把认识的名字都报出来，别让人猜。"""
    key = str(name or 'visual')
    if key not in FACES:
        raise ValueError(f'不认识的审阅面：{key}（只有 {", ".join(FACES)}）')
    return FACES[key]


def surface_path(root, name='visual'):
    """这份 surface 文件在哪（本 Skill 的目录约定，模组不需要知道）。"""
    return Path(root)/describe(name)['surface_rel']


def feedback_path(root, name='visual'):
    """反馈落盘在哪 —— **相对 surface 文件**（R2），所以基准是 surface 的父目录。"""
    return surface_path(root, name).parent/describe(name)['feedback_rel']


def surface_document(root, name='visual'):
    """这一份 surface 的内容。`project_root` / `dir` 都**相对 surface 文件**。"""
    face = describe(name)
    base = surface_path(root, name).parent.resolve()
    # 相对 surface 文件自己（R2）——`os.path.relpath` 对"面在子目录里"也成立，不会抛。
    up = os.path.relpath(Path(root).resolve(), base)
    return {
        'contract_version': review_host.CONTRACT_VERSION,
        'id': face['id'],
        'title': face['title'],
        'description': face['description'],
        # 两个基准分开写（R2）：`dir` / `entry` 是"被 serve 的那棵树"上的地址，
        # `feedback` / `watch` 相对**这份 surface 文件**自己。
        'project_root': up,
        'dir': up,
        'entry': face['entry'],
        'feedback': face['feedback_rel'],
        # 省略 = 这个面不做草稿（模板审阅面就没有）。宿主按声明决定收不收 `draft` 调用。
        **({'draft': face['draft_rel']} if face.get('draft_rel') else {}),
        # 唤醒一律**插话**（`steer` → `next-step`），不进持久队列。
        # 声明 `queue` 会让提交排到当前回合之后（DSH 的 `agent.followup` → `next-turn`）：
        # 模型正忙时它就躺在队列里等，界面上同时出现「已送达」和「排队中」两份。
        # 人点「本页要求修改」的语义是"现在就按这个改"，所以走步骤边界。
        'wake': {'mode': 'steer', 'text': face['wake_text']},
        'capabilities': list(face['capabilities']),
        'watch': list(face['watch']),
    }


def write_surface(root, name='visual'):
    """建文档 → 交给模组落盘（幂等）。页面与它是同一对产物，所以由生成审阅页那一步一起写。"""
    path = surface_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    return review_host.write_surface(path, surface_document(root, name))


def host_state_path(root, name='visual'):
    """这个面的宿主状态文件在哪（名字归公共件，位置归本 Skill 的目录约定）。"""
    return surface_path(root, name).parent/review_host.HOST_STATE_NAME


def validate_surface(root, name='visual'):
    """薄壳：模组收 surface 路径，本 Skill 的调用方习惯给项目根。"""
    return review_host.validate_surface(surface_path(root, name))


def open_review(root, port=0, open_browser=True, name='visual'):
    """让作者在页面上审阅：**写 surface + 校验**（业务），然后交给模组起/复用宿主。

    「有插件时只报 surface 路径、不起宿主」那条分支在 `ppt_pipeline`（`--surface-only`）：
    它要的 `entry` / `feedback_path` 是本 Skill 的产物位置，属于业务，所以留在那边。
    """
    root = Path(root)
    face = describe(name)
    surface = write_surface(root, name)              # 幂等：与页面一起生成过
    validate_surface(root, name)
    info = review_host.open_review(surface, port=port, open_browser=open_browser)
    info['face'] = face['name']
    info['entry'] = str((root/face['entry']).resolve())
    info['feedback_path'] = str(feedback_path(root, name).resolve())
    return info


def main(argv=None):
    parser = argparse.ArgumentParser(description='审阅面：写 surface，交给公共缝的宿主')
    parser.add_argument('project', help='项目目录')
    parser.add_argument('--face', choices=sorted(FACES), default='visual', help='哪个审阅面（默认页面审阅）')
    parser.add_argument('--port', type=int, default=0, help='无插件宿主的端口（默认 0＝自动选）')
    parser.add_argument('--no-open', action='store_true', help='不自动打开浏览器')
    args = parser.parse_args(argv)
    try:
        result = open_review(Path(args.project).expanduser().resolve(), port=args.port,
                             open_browser=not args.no_open, name=args.face)
    except ValueError as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False, indent=1))
        return 2
    print(json.dumps({'ok': True, **result}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
