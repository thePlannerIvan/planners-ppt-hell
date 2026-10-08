#!/usr/bin/env python3
"""模板审阅的收件层：读页面经宿主**原样落盘**的 `template_feedback.json` → 校验 → 规范化 → 写回。

与页面审阅同一套分工（`review_feedback.py`）：**页面写原始状态，Skill 说了算**。
页面不能自证 —— `approved` / `all_approved` / `discarded_layouts` / `revision_layouts`
一律在这里按 `layouts` 重新算出来再写回；页面写的那个值只是"页面以为的"。

**对外语义一个字不改**：文件仍是 `_internal/00_project/template_feedback.json`，字段仍是
`review_id / submission_action / approved / all_approved / template_name / overall_feedback /
layouts[{approved, decision, custom_feedback}]` —— `template_library.publish()` 的
`require_approved_feedback()` 读到的还是同一件事（批准、模板名、逐版式通过、review_id 绑定）。

**一处事实只有一个来源**：这一版审阅页该有哪些 Layout，取**快照里写下的那份列表**
（生成审阅页时与页面一起写的）。以前按 `page_manifest.template_intake.mode` 推：非 fidelity
就只认 `reference_system`，而**页面是按 registry 的 layouts 渲染的** —— 两个来源，于是
"页面显示 5 个、收件只要 1 个"，一份完全正确的提交会被判成"没覆盖全部 Layout"。
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from project_state import PROJECT, TEMPLATE_REVIEW_SNAPSHOT, event, read, sha, template_version, write

sys.path.insert(0, str(Path(__file__).resolve().parent / 'template'))
from layout_canvas import registry_canvases_ready                    # noqa: E402
from template_visual_gate import review_complete as canvas_review_complete  # noqa: E402

FEEDBACK = 'template_feedback.json'
ENTRY = '00_template_review.html'
REGISTRY = 'fidelity_template/template_registry.json'
ACTIONS = {'submit_batch', 'approve_all'}
DECISIONS = {'pass', 'discard', 'revise'}
def png_hashes(root):
    """审阅对象（源模板渲染页）此刻的字节摘要 —— 批准绑上去，重渲染之后批准自动作废。"""
    base = Path(root)/PROJECT/'template_visuals'
    return {path.name: sha(path) for path in sorted(base.glob('*.png'))} if base.is_dir() else {}


def package_hashes(root):
    """模板包（registry / canvases / previews）此刻的字节摘要 —— 重建模板之后批准自动作废。"""
    pack=Path(root)/PROJECT/'template_pack'
    if pack.is_dir():
        from template_library import package_hashes as pack_hashes
        return {str((pack/rel).relative_to(Path(root))):value for rel,value in pack_hashes(pack).items()}
    base = Path(root)/PROJECT/'fidelity_template'
    files = [base/'template_registry.json',
             *sorted((base/'layout_canvases').glob('*.svg')),
             *sorted((base/'canvas_previews'/'pages').glob('*.png')),
             base/'canvas_previews'/'full_deck_contact_sheet.png']
    return {str(path.relative_to(Path(root))): sha(path) for path in files if path.is_file()}


# 这两句是**对外协议**（agent 与旧服务器都用过这两句），保持原文。
STALE_MESSAGE = 'Template review is stale; reload the review page before deciding.'
DECISIONS_MESSAGE = 'feedback must cover the exact layout set with pass/discard/revise decisions'


def feedback_path(root):
    return Path(root)/PROJECT/FEEDBACK


def template_review_snapshot(root):
    return read(Path(root)/PROJECT/TEMPLATE_REVIEW_SNAPSHOT, {})


def expected_layouts(root):
    """这一版审阅页该有哪些 Layout —— **快照说了算**（与页面同源），退一步才用 registry。"""
    snapshot = template_review_snapshot(root)
    listed = snapshot.get('layouts')
    if isinstance(listed, list) and listed:
        return [str(one) for one in listed]
    registry = read(Path(root)/PROJECT/REGISTRY, {})
    if isinstance(registry.get('layouts'), dict) and registry['layouts']:
        return [str(one) for one in registry['layouts']]
    return ['reference_system']


def stale_reason(root, data):
    """「必须看过当前版本」的保护：快照 + review_id + HTML hash + 模板版本，四条全对才算数。

    与旧服务器逐字一致（原文返回，交给调用方报给人看）。
    """
    root = Path(root)
    snapshot = template_review_snapshot(root)
    if not snapshot:
        return 'Template review page is stale; regenerate it with template-review.'
    entry = root/ENTRY
    if (str(data.get('review_id') or '') != str(snapshot.get('review_id') or '')
            or not entry.is_file()
            or snapshot.get('html_sha256') != sha(entry)
            or snapshot.get('template_version') != template_version(root)):
        return STALE_MESSAGE
    return ''


def _candidate_audit_ready(root):
    """全部通过还要求"候选审计"齐：模板里每一个抽出来的资产/原生形状都被审过。"""
    try:
        profile = read(Path(root)/PROJECT/'template_profile.json', {})
        asset_registry = read(Path(root)/PROJECT/'template_asset_registry.json', {})
        facts = profile.get('structural_extraction', {})
        candidate_ids = {
            item.get('asset_id') for item in facts.get('assets', []) if isinstance(item, dict) and item.get('asset_id')
        } | {
            item.get('candidate_id') for item in facts.get('native_shapes', []) if isinstance(item, dict) and item.get('candidate_id')
        }
        return not candidate_ids or set(asset_registry.get('reviewed_source_ids', [])) == candidate_ids
    except (OSError, ValueError, TypeError):
        return False


def _fidelity_ready(root):
    if (Path(root)/PROJECT/'template_pack').is_dir():
        from template_library import validate_pack_dir
        return validate_pack_dir(Path(root)/PROJECT/'template_pack')['valid']
    registry = read(Path(root)/PROJECT/REGISTRY, {})
    layouts = registry.get('layouts') if isinstance(registry, dict) else None
    if not isinstance(layouts, dict) or not layouts:
        return True                      # 不是 fidelity 提取（没有 registry）→ 这条门不适用
    try:
        return bool(all(layout.get('required_components') for layout in layouts.values())) and \
            registry_canvases_ready(registry, Path(root)/PROJECT/'fidelity_template') and \
            canvas_review_complete(root)
    except (OSError, ValueError, TypeError):
        return False


def validate(root, data, expected=None):
    """校验一份提交，返回 `(errors, summary)`。措辞与旧服务器一致（对外协议）。

    `expected` 只给测试用：**回放旧规则**（按 `page_manifest.template_intake.mode` 推出来的
    那份 layout 集合），好让"旧规则会把一份合法提交判死"这件事有一条可跑的红对照。
    """
    errors = []
    action = str(data.get('submission_action', '')).strip().lower()
    if action not in ACTIONS:
        errors.append('submission_action must be submit_batch or approve_all')
    expected = list(expected) if expected else expected_layouts(root)
    layouts = data.get('layouts', {})
    if not isinstance(layouts, dict) or set(layouts) != set(expected) or not all(
            isinstance(layouts.get(key), dict)
            and layouts[key].get('decision') in DECISIONS
            and isinstance(layouts[key].get('approved'), bool) for key in expected):
        errors.append(DECISIONS_MESSAGE)
        layouts = layouts if isinstance(layouts, dict) else {}
    # 派生量一律**重新算**（页面写的 approved 不算数）：
    all_pass = bool(expected) and all(layouts.get(key, {}).get('decision') == 'pass' for key in expected)
    overall = str(data.get('overall_feedback', '')).strip()
    missing = [key for key in expected
               if layouts.get(key, {}).get('decision') == 'revise'
               and not str(layouts.get(key, {}).get('custom_feedback', '')).strip() and not overall]
    if missing:
        errors.append('each revised layout requires per-layout or overall feedback')
    if action == 'approve_all' and not all_pass:
        errors.append('approve_all requires every layout to pass')
    template_name = str(data.get('template_name', '')).strip()
    if all_pass and not template_name:
        errors.append('all-pass requires a template name')
    if all_pass and not _candidate_audit_ready(root):
        errors.append('all-pass requires the candidate audit (template_asset_registry covers every extracted candidate)')
    if all_pass and not _fidelity_ready(root):
        errors.append('all-pass requires the visual gate: every layout canvas current and the canvas self-review complete')
    summary = {
        'all_pass': all_pass,
        'passed': sorted(key for key in expected if layouts.get(key, {}).get('decision') == 'pass'),
        'discarded_layouts': sorted(key for key in expected if layouts.get(key, {}).get('decision') == 'discard'),
        'revision_layouts': sorted(key for key in expected if layouts.get(key, {}).get('decision') == 'revise'),
        'template_name': template_name,
        'expected_layouts': expected,
    }
    return errors, summary


def consume(root):
    """模型这一侧的收件口：读页面写下的反馈 → 校验 → 规范化写回。幂等（同一份提交只处理一次）。

    返回 `None`（还没有提交）或
    `{'path','stale','stale_message','errors','summary','document','first_time'}`。
    `stale=True` 表示这份反馈绑的是**上一版**审阅页：它不算批准（发布闸门按 review_id 比，
    结构上就过不去），但仍然原样报出来，让人知道该重新生成一版。
    """
    root = Path(root)
    path = feedback_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('模板反馈读不出来：'+str(error))
    if not isinstance(data, dict) or not isinstance(data.get('layouts'), dict):
        raise ValueError('模板反馈的形状不对：缺少 layouts')

    reason = stale_reason(root, data)
    errors, summary = validate(root, data)
    # 这一次提交的**身份**：优先用页面自己写下的那个提交时刻（R6：取事件的身份，不取内容），
    # 没有才由收件层盖章。同一个值要同时写进顶层与 consumed —— 否则第二次收件认不出来，
    # 同一份提交会被反复处理（幂等就没了）。
    submitted_at = (data.get('submitted_at')
                    or (data.get('provenance') or {}).get('submitted_at')
                    or datetime.now(timezone.utc).isoformat())
    stamp = {
        'review_id': data.get('review_id'),
        'submitted_at': submitted_at,
    }
    already = data.get('consumed') if isinstance(data.get('consumed'), dict) else {}
    first_time = not (already.get('review_id') == stamp['review_id']
                      and already.get('submitted_at') == stamp['submitted_at'])
    document = {
        **data,
        # 派生量：Skill 重新算过的那一份（页面写的那个值不采信）
        'approved': summary['all_pass'] and not reason and not errors,
        'all_approved': summary['all_pass'] and not reason and not errors,
        'discarded_layouts': summary['discarded_layouts'],
        'revision_layouts': summary['revision_layouts'],
        'submitted_at': submitted_at,
        'consumed': {
            'at': datetime.now(timezone.utc).isoformat(),
            'stale': bool(reason),
            'errors': errors,
            'review_id': stamp['review_id'],
            'submitted_at': submitted_at,
        },
    }
    if not reason:
        # **绑定的证据由 Skill 盖章**（页面算不了、宿主不解释）：批准绑在"这一版审阅页 HTML +
        # 这一版源模板渲染页 + 这一版模板包"上。模板一重建，这些摘要就对不上，批准自动作废。
        # 陈旧的那一份**不盖章**：不给它留下任何看起来算数的证据。
        entry = root/ENTRY
        document['provenance'] = {
            **(data.get('provenance') or {'source': 'template_review_page'}),
            'html': ENTRY,
            'html_sha256': sha(entry) if entry.is_file() else None,
            'png_sha256': png_hashes(root),
            'template_package_sha256': package_hashes(root),
        }
    write(path, document)
    if first_time:
        event(root, 'template_feedback_consumed',
              review_id=data.get('review_id'), submission_action=data.get('submission_action'),
              stale=bool(reason), errors=errors, all_pass=summary['all_pass'],
              discarded_layouts=summary['discarded_layouts'], revision_layouts=summary['revision_layouts'],
              provenance=data.get('provenance', {}))
    return {'path': str(path), 'stale': bool(reason), 'stale_message': reason, 'errors': errors,
            'summary': summary, 'document': document, 'first_time': first_time}
