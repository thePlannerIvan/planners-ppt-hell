"""反馈的 Skill 侧：形状校验、绑定核对、轮次留档。

**写反馈的人变了。** 以前是 `review_server.py` 在提交那一刻校验并写盘；现在是**页面自己**
经宿主（DSH 侧栏 / `serve-review.mjs`）把整份状态写进 `feedback.json` —— 宿主不解释内容。
所以校验与留档都归 Skill：

  · `consume(root)` —— 模型这一侧的**收件口**：形状校验 + 绑定核对 + 规范化写回 + 把这一轮留档（幂等）。

  旧服务器那个写入口（`save_feedback`）**已随 `review_server.py` 一起退役**：页面审阅 2026-09-26
  换宿主，模板审阅那条线同日跟上（模板侧的收件口在 `template_feedback.py`）。

绑定判据仍是 `review_id`：它由生成审阅页那一步写下（`snapshot.json`），页面把它连同每页版本
一起写进反馈。**review_id 对得上 = 这份反馈是冲着当前这一版审阅页写的**；对不上就是上一轮的
（那一轮的意见仍然要读，但不再算批准——`approvals()` 按版本比）。
"""
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from project_state import REVIEW, event, local, read, review_current, review_snapshot, sha, write

HISTORY = 'history'

def _round_paths(root):
    history=root/REVIEW/HISTORY
    rounds=[]
    if history.is_dir():
        for path in history.iterdir():
            match=re.fullmatch(r'round-(\d+)\.json',path.name)
            if match: rounds.append((int(match.group(1)),path))
    rounds.sort()
    return rounds

def _submitted_at(data):
    """这一轮的提交时刻。页面写在 `provenance.submitted_at`；兼容写在顶层的老形状。"""
    provenance=data.get('provenance') if isinstance(data.get('provenance'),dict) else {}
    return str(provenance.get('submitted_at') or data.get('submitted_at') or '')

def content_key(page, feedback='', annotations=None, assets=None):
    """一条意见的**内容身份**：哪一页 + 那句话说的是什么。

    这是"意见的生命周期"的键：`resolve` 之后它就进已关闭集合，**同一页的同一句话永远不再成为待办**。
    规范化只取会改变含义的东西（文字去掉首尾空白、框选按文本排序、图片操作按 key+operation+path 排序），
    所以"换一行排版"不会骗过它，而"换了说法"天然就是新意见。
    """
    canonical=json.dumps({
        'page':str(page),
        'feedback':str(feedback or '').strip(),
        'annotations':sorted(str(a.get('text') or '').strip() for a in (annotations or []) if isinstance(a,dict)),
        'assets':sorted((str(a.get('asset_key') or ''),str(a.get('operation') or ''),str(a.get('path') or ''))
                        for a in (assets or []) if isinstance(a,dict)),
    },ensure_ascii=False,sort_keys=True)
    return hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:16]

def closed_keys(root):
    """已经**关闭**的意见（`resolve` 过）的内容身份集合：`{(page, content_key)}`。

    2026-09-26 的规则：**意见 → 模型改 → 那条意见结束**。它不是"还挂在人名下的待办"，
    而是历史（原件仍留在 `history/round-NN.json` 里可回查）。所以同页同话再出现时**不再生成条目**。
    """
    resolutions=read(Path(root)/REVIEW/'resolutions.json',{})
    closed=set(); missing=[]
    for resolution_id,record in (resolutions.items() if isinstance(resolutions,dict) else []):
        if not isinstance(record,dict): continue
        entries=[e for e in (record.get('closed') or []) if isinstance(e,dict) and e.get('page') is not None and e.get('key')]
        if not entries: missing.append(str(resolution_id))
        for entry in entries:
            closed.add((str(entry['page']),str(entry['key'])))
    # 兼容：本规则落地之前 resolve 过的那些记录里没有 closed，从历史归档里按 id 把内容身份补出来
    # （历史归档装的就是当时提交的那份文档，含 items 的原文）。不补的话，老项目里同一句话还能再长出来。
    if missing:
        wanted=set(missing)
        for item in _items_from_history(root):
            if str(item.get('id')) not in wanted: continue
            pages=item.get('pages') if isinstance(item.get('pages'),list) else []
            if len(pages)==1:
                closed.add((str(pages[0]),content_key(pages[0],item.get('feedback'),item.get('annotations'),item.get('assets'))))
            elif pages:
                closed.add(('overall',content_key('overall',item.get('feedback'))))
    return closed

def _items_from_history(root):
    """历史归档（`history/*.json`）里出现过的条目原文。给 `closed_keys` 补老记录用。"""
    for path in sorted((Path(root)/REVIEW/HISTORY).glob('*.json')):
        try: data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError): continue
        if isinstance(data,dict) and isinstance(data.get('items'),list):
            for item in data['items']:
                if isinstance(item,dict) and item.get('id'): yield item

def _item_id(scope,submitted_at):
    """反馈条目的 id：**由「哪一页 + 哪一轮」定出来**，不用随机 uuid。

    这样「同一轮被反复收件」不会每次都换一批 id（模型拿到的 feedback id 在两次 `next` 之间必须稳定，
    否则 `resolve --feedback-id` 会突然找不到人）；跨轮又必然不同（`resolved` 不会串轮）。
    """
    return hashlib.sha1((str(scope)+'|'+str(submitted_at)).encode('utf-8')).hexdigest()[:16]

def _serialize(data):
    return json.dumps(data,ensure_ascii=False,indent=2)+'\n'

def archive(root, serialized):
    """把一份反馈原文留档到 `_internal/05_review/history/round-NN.json`。

    轮次顺延；与上一份留档**内容完全相同**就不重复写（同一轮被重复消费不会长出 round-02）。
    返回留档文件，或 None。
    """
    history=root/REVIEW/HISTORY
    rounds=_round_paths(root)
    if rounds and rounds[-1][1].read_text(encoding='utf-8')==serialized: return None
    target=history/f'round-{(rounds[-1][0]+1 if rounds else 1):02d}.json'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(serialized,encoding='utf-8')
    return target

def archive_round(root):
    """旧写入口的留档：把**即将被覆盖**的 `feedback.json` 原文留档。"""
    current=root/REVIEW/'feedback.json'
    if not current.is_file(): return None
    return archive(root,current.read_text(encoding='utf-8'))

def archive_consumed(root, document):
    """收件口的留档：一轮反馈被模型**读到**时留一份。同一提交时刻只留一次。

    与 `archive_round` 的分工：那个保护"被覆盖的上一轮"，这个保证"模型读过的每一轮都可回查"
    ——宿主是把整份状态覆盖写进同一个文件的，Skill 没有别的时机留档。
    """
    rounds=_round_paths(root)
    if rounds:
        try: previous=json.loads(rounds[-1][1].read_text(encoding='utf-8'))
        except ValueError: previous=None
        if isinstance(previous,dict) and _submitted_at(previous)==_submitted_at(document): return None
    return archive(root,_serialize(document))

def validate_document(root,data,strict=True,suppressed=None):
    """校验一份反馈，返回规范化后的文档（不改盘）。

    `strict=True`（这份反馈的 review_id 就是当前这一版审阅页）：页面集必须与当前页集一致、
    整份审阅必须仍然成立（`review_current`），并且**每页的版本与 PNG hash 由当前快照重新盖章**
    ——「看过的是现在这一版」这条保护落在这一步，页面自己写什么都不算数。
    `strict=False`（上一轮的反馈）：只做形状校验，缺的页不追究——它已经不再算批准了，
    但模型还要靠它的 items 知道上一轮提过什么。
    """
    root=Path(root)
    snapshot=review_snapshot(root)
    if not isinstance(data,dict): raise ValueError('反馈不是一个对象')
    supplied=data.get('pages')
    if not isinstance(supplied,dict) or not supplied: raise ValueError('反馈里没有 pages')
    if strict:
        expected=snapshot.get('versions') or {}
        if str(data.get('review_id') or '')!=str(snapshot.get('review_id') or ''):
            raise ValueError('Review is stale. Reload the current review; decisions were not saved.')
        if set(supplied)!=set(expected): raise ValueError('Feedback must cover the exact page set')
    result={}; items=[]
    submitted_at=_submitted_at(data)
    closed=closed_keys(root)
    overall=str(data.get('overall_feedback','')).strip()
    # 条目 id 优先沿用页面写下的（页面自己给 uuid）——规范化**不能换 id**：模型可能已经拿着
    # 这个 id 跑过 `resolve`，换一次 id 那条解决记录就变成孤儿、item 会"复活"。
    # 只有页面没给 items（手写文件、旧形状）时才由「哪一页 + 哪一轮」推出来。
    incoming=data.get('items') if isinstance(data.get('items'),list) else []
    given={}; given_overall=None
    for item in incoming:
        if not isinstance(item,dict) or not str(item.get('id') or ''): continue
        pages=item.get('pages') if isinstance(item.get('pages'),list) else []
        if len(pages)==1: given.setdefault(str(pages[0]),str(item['id']))
        elif given_overall is None: given_overall=str(item['id'])
    for key,entry in supplied.items():
        if not isinstance(entry,dict): raise ValueError('Invalid page feedback')
        decision=entry.get('decision')
        if decision not in {'pending','approved','revise'}: raise ValueError('Invalid decision')
        note=str(entry.get('feedback','')).strip()
        annotations=entry.get('annotations',[]);assets=entry.get('assets',[])
        if not isinstance(annotations,list) or not isinstance(assets,list): raise ValueError('Invalid annotations/assets')
        for region in annotations:
            if not isinstance(region,dict): raise ValueError('Invalid region')
            numbers=[region.get(n) for n in ('x','y','w','h')]
            if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in numbers): raise ValueError('Invalid region coordinates')
            x,y,w,h=numbers
            if min(x,y)<0 or min(w,h)<=0 or x+w>1.00001 or y+h>1.00001 or not str(region.get('text','')).strip():
                raise ValueError('Region must be inside page and have feedback')
        declared={a['asset_key'] for a in (snapshot.get('assets',{}).get(key) or [])}
        permitted={a['path'] for a in (snapshot.get('assets',{}).get(key) or [])}
        upload_base=root/REVIEW/'uploads'/key
        used=set()
        for asset in assets:
            asset_key=asset.get('asset_key','');operation=asset.get('operation')
            if not asset_key or asset_key in used or operation not in {'add','replace','crop'}:
                raise ValueError('Unique asset keys and valid operations required')
            used.add(asset_key)
            if declared and (operation=='add' and asset_key in declared or operation!='add' and asset_key not in declared):
                raise ValueError('Asset operation does not match displayed image')
            path=local(root,asset.get('path',''))
            if permitted and str(path.relative_to(root)) not in permitted and upload_base not in path.parents:
                raise ValueError('Asset must be displayed or uploaded for this page')
            if not path.is_file() or asset.get('fit') not in {'contain','cover'}: raise ValueError('Missing image or invalid fit')
            if upload_base in path.parents and not _is_image(path): raise ValueError('Invalid image bytes: '+str(path))
            if not re.fullmatch(r'(original|[1-9]\d*:[1-9]\d*)',str(asset.get('ratio',''))): raise ValueError('Use original or W:H ratio')
            if asset.get('anchor') not in {'center','top','bottom','left','right'}: raise ValueError('Invalid anchor')
            asset['sha256']=sha(path)
        if note or annotations or assets: decision='revise'
        if decision=='revise' and not (note or annotations or assets or overall): raise ValueError('Describe the requested change')
        if strict:
            result[key]={'decision':decision,'feedback':note,'annotations':annotations,'assets':assets,
                         'version':(snapshot.get('versions') or {})[key],'png_sha256':(snapshot.get('png_hashes') or {})[key]}
        else:
            result[key]={**entry,'decision':decision,'feedback':note,'annotations':annotations,'assets':assets}
        if decision=='revise':
            fingerprint=content_key(key,note,annotations,assets)
            if (str(key),fingerprint) in closed:
                # 这句话已经落实并关闭过：它是历史，不是待办（原件在 history/round-NN.json 里可回查）
                if suppressed is not None: suppressed.append({'page':key,'content_key':fingerprint,'reason':'already_resolved'})
                result[key]['already_resolved']=True
            else:
                items.append({'id':given.get(str(key)) or _item_id(key,submitted_at),'pages':[key],
                              'feedback':note,'annotations':annotations,'assets':assets})
    if overall and ('overall',content_key('overall',overall)) not in closed:
        items.append({'id':given_overall or _item_id('overall',submitted_at),'pages':list(result),'feedback':overall})
    normalized={**data,'pages':result,'overall_feedback':overall,'items':items}
    return normalized

def _is_image(path):
    """落地的上传件必须真的是图片（以前是服务器在写盘前 verify，现在写盘的是宿主）。"""
    try:
        from PIL import Image
        with Image.open(path) as image: image.verify()
        return True
    except Exception:
        return False

def consume(root):
    """模型这一侧的收件口：读页面写下的反馈 → 校验 → 这一轮留档。幂等。

    返回 `{'document','stale','archived','path'}`；没有反馈文件时返回 None。
    `stale=True` 表示这份反馈绑的是**上一版**审阅页（review_id 对不上当前快照）——
    它仍然可读（items 是模型要继续处理的东西），但不算批准，也不按当前页集追究。
    """
    root=Path(root)
    path=root/REVIEW/'feedback.json'
    data=read(path,None)
    if not isinstance(data,dict) or not data: return None
    try: current=review_current(root)
    except (OSError,ValueError): current=False
    snapshot=review_snapshot(root)
    stale=(str(data.get('review_id') or '')!=str(snapshot.get('review_id') or '')) or not current
    suppressed=[]
    document=validate_document(root,data,strict=not stale,suppressed=suppressed)
    # 收件即规范化：宿主原样落盘，所以「items / 决定词汇 / 盖上的版本」这些 canonical 形状由 Skill
    # 在这一步补齐并写回。幂等——规范化过的文件再收一次内容不变，就不重复写。
    if document!=data: write(path,document)
    archived=archive_consumed(root,document)
    return {'document':document,'stale':stale,'path':str(path),'suppressed':suppressed,
            'archived':str(archived.relative_to(root)) if archived else ''}
