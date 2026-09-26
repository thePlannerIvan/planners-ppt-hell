"""One actual-page review: the surface entry page, the surface contract, and the snapshot.

这一份产物是三件东西，一起生成、一起作废：

  · `02_visual_review.html` —— 审阅页（review-surface 的入口），里面留 `{{REVIEW_BRIDGE}}` 注入点；
  · `_internal/05_review/snapshot.json` —— 生成这一刻的版本快照（review_id + 每页版本 + PNG hash）；
  · `_internal/05_review/review-surface.json` —— 交给宿主的 surface（页面、目录、反馈文件、唤醒文案）。

页面里的资产一律走**相对 `dir`（＝项目根）的路径**，由页面向桥要 URL：`await review.asset(rel, {v})`。
所以这里给的是 `rel` 与 `version`，不是拼好的 URL。
"""
import json
import uuid
from pathlib import Path

from project_state import (PNG, REVIEW, SVG, approvals, content, images, read,
                           review_snapshot, sha, versions, write)
from review_surface import write_surface

SNAPSHOT_REL = f'{REVIEW}/snapshot.json'
VERSIONS_REL = f'{REVIEW}/versions'

def asset_records(root, key):
    """这一页的素材，每条多一个能直接放进 URL 的短版本。

    `version` = 文件内容 sha256 的前 12 位。页内素材是**原地替换**的（同名覆盖），
    所以页面的资产 URL 必须带版本，才拿得到新图；页面大图用的是页版本，同一个道理。
    """
    return [{**item, 'version': str(item.get('sha256') or '')[:12]}
            for item in images(root, root/SVG/(key+'.svg'))]

def previous_page_feedback(root, current):
    """旧一轮反馈里「这一页已经按意见改过、待人复核」的那些条目。

    判定是**这一页的版本在反馈之后变过**：`feedback.json` 里那条记录的 `version`
    与当前版本不一致，就说明模型按它重出过这一页。

    为什么必须带回来：提交仍是整份覆盖（现在是页面自己整份写），所以「人写完意见 →
    模型改完一页 → 人再打开审阅页」这条路上，上一轮那些字如果只留在 `feedback.json`
    里，下一次提交就会连旧决定一起被新的整份反馈盖掉。带回来是唯一的留存方式——
    页面据此把它显示成「上一轮的意见」，复核后清空即确认。
    """
    old = read(root/REVIEW/'feedback.json', {}).get('pages', {})
    if not isinstance(old, dict):
        return {}
    carried = {}
    for key, version in current.items():
        item = old.get(key)
        if not isinstance(item, dict) or item.get('version') == version:
            continue
        carried[key] = {
            'previousDecision': item.get('decision') or 'pending',
            'previousFeedback': str(item.get('feedback') or ''),
            'previousAnnotations': item.get('annotations') or [],
            'previousAssets': item.get('assets') or [],
        }
    return carried

def generate(root):
    c=content(root);v=versions(root);old=review_snapshot(root);allowed=approvals(root)
    carried=previous_page_feedback(root,v)
    snap={'review_id':uuid.uuid4().hex,'versions':v,'order':list(v),'png_hashes':{k:sha(root/PNG/(k+'.png')) for k in v},
        'assets':{k:asset_records(root,k) for k in v}}
    data={'project':c.get('project',''),'review_id':snap['review_id'],'snapshot':SNAPSHOT_REL,'pages':[]}
    for p in c['pages']:
        k=p['page_key'];previous=root/REVIEW/'versions'/f'{k}-{old.get("versions",{}).get(k,"")}.png'
        data['pages'].append({'key':k,'title':p['title'],'png':f'{PNG}/{k}.png','version':v[k],
            'png_sha256':snap['png_hashes'][k],'assets':snap['assets'][k],
            'previous':f'{VERSIONS_REL}/{previous.name}' if previous.exists() else '',
            'decision': 'approved' if allowed.get(k,{}).get('decision')=='approved' else 'pending',
            **carried.get(k, {})})
    template=(Path(__file__).resolve().parents[1]/'assets/review/review.html').read_text()
    html=template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    (root/'02_visual_review.html').write_text(html,encoding='utf-8')
    snap['html_sha256']=sha(root/'02_visual_review.html');write(root/REVIEW/'snapshot.json',snap)
    write_surface(root)
    return snap
