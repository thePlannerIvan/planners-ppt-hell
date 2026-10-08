#!/usr/bin/env python3
"""Persistent SVG workbench: candidate commits, technical checks, snapshot exports."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import shutil
from datetime import datetime, timezone
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import review_surface
from review_feedback import (APPLIED_EDITS_FILE, ack_human_edit, consume, content_key,
                             human_edit_state, human_edits)
import template_feedback
from workbench_store import ensure, get_page, commit, snapshot, record_render, load_snapshot
from project_state import (DIRECTION, POSITION_HELP, PROJECT, PNG, REVIEW, SVG, VALIDATION, approved,
                           carry_inspection, content, contract_binding, design_observations_deck, digest,
                           event, inspected, local, manifest, page_version, parse_position, read, rendered,
                           review_current, review_recorded, review_snapshot, route, sha, sync,
                           versions, write)
SCRIPTS=Path(__file__).resolve().parents[1]
OUTPUT='_internal/06_ppt_output'

VALIDATOR_ROUTE_HELP='出口路线决定校验器跑哪一半规则；路线记在项目状态里，这里按它传下去。'
VIDEO_DELIVERABLE=f'{SVG}/<page_key>.svg（全部页面，交给动画层）'
WATCH_THE_BIG_PNG='看的是每页 PNG 大图，不是联系表里的缩略格。'
# 起过的审阅服务进程句柄。留住它们，别在进程还活着的时候被 GC 掉。

def run(*args, env=None):
    p=subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True,env=env)
    if p.returncode: raise ValueError(p.stderr.strip() or p.stdout.strip() or 'Command failed')
    return p.stdout

def validator_argv(root, m, key, mode, report=None, source=None, route_override=None):
    """检查画面的调用参数。与 check 用的是同一个校验器、同一套几何算法。

    路线一起传过去：视频出口不吃 PPTX，校验器只跑两条路都成立的那一半，
    并把跳过的规则连同原因写进报告，不静默消失。
    """
    if source:
        svg=Path(source)
    else:
        page=get_page(root,key)
        if not page['revision']: raise ValueError('Page has no saved SVG: '+key)
        svg=Path(page['svg_path'])
    argv=[sys.executable,str(SCRIPTS/'validate_svg_layout.py'),str(svg.parent),'--file',str(svg),
          '--page-mode',mode,'--route',route_override or route(root)]
    if report: argv+=['--output',str(report)]
    registry=root/PROJECT/'fidelity_template/template_registry.json'
    if (m.get('template_intake',{}).get('mode')=='fidelity' and route(root)=='slides'
            and registry.is_file() and not (root/PROJECT/'template_pack').is_dir()):
        argv+=['--fidelity-template',str(registry)]
    return argv

def direction_missing(root):
    path=root/DIRECTION
    return None if path.is_file() else path

def require_direction(root):
    """视频路线上 design_direction.md 是动手前的前置，缺了不放行。

    幻灯片路线保持现状：它是推荐的前置，不是门。
    """
    missing=direction_missing(root)
    if missing and route(root)=='video':
        raise ValueError(
            '视频路线上 design_direction.md 是动手前的前置，现在缺 '+str(missing)+
            '：先按 references/workflow/03_video_route.md 写清这套页面的共同秩序与四条视频约束'
            '（字幕安全区、人物位置、不透明与透明、强调动画余量），再画页面。')

def require_contract(root):
    """契约绑定：`level=error` 拦下（口播稿改过，画面可能要重画）。

    返回的记录每一条都带 `level`（ok／warning／error／unchecked），所以「核过没问题」
    与「压根没核」在输出里是两个样子。
    """
    records=contract_binding(root)
    errors=[item for item in records if item.get('level')=='error']
    if errors: raise ValueError('画面契约绑定对不上：'+'；'.join(i['message'] for i in errors))
    return records

def contract_result(root):
    try: return contract_binding(root)
    except (OSError,ValueError): return []

def layout_check(root, keys, export_snapshot=None):
    """检查画面，跑在导出时：转换之前逐页拦下「转成 PPT 会坏」的东西。

    它和转换 PPT 共用同一套坐标模型（validate_svg_layout 从 native_svg_to_ppt 取），
    所以两边不会再说出不同的答案。
    """
    if export_snapshot:
        # Snapshot SVG/assets are intrinsic inputs; a live template registry is not frozen evidence.
        m={};pages={p['page_key']:p.get('input',{}) for p in export_snapshot['pages']}
    else:
        m=manifest(root);pages={p['page_key']:p for p in content(root)['pages']}
    problems=[]
    frozen={p['page_key']:p for p in export_snapshot['pages']} if export_snapshot else {}
    for k in keys:
        source=Path(export_snapshot['root'])/frozen[k]['svg'] if export_snapshot else None
        result=subprocess.run(validator_argv(root,m,k,pages[k].get('mode') or '读',source=source,
                                            route_override=export_snapshot['route'] if export_snapshot else None),capture_output=True,text=True)
        try: data=json.loads(result.stdout or '{}')
        except json.JSONDecodeError: data={}
        summary=data.get('summary')
        if summary is None:
            problems.append({'page':k,'error':(result.stderr or result.stdout or 'validator produced no report').strip()[:400]})
            continue
        if result.returncode and not summary.get('errors'):
            problems.append({'page':k,'error':(result.stderr or 'validator failed without a successful report').strip()[:400]})
            continue
        if summary.get('errors'):
            issues=[i for r in data.get('reports',[]) for i in r.get('issues',[]) if i.get('severity')=='error']
            problems.append({'page':k,'errors':summary['errors'],'issues':issues})
    return problems

def human_edit_problems(root, keys):
    """人手动改过、后来又被整份重写、而没有人交代过的页。**这是「白改了」的那条路。**

    审阅页上的轻量直改（改字、移位、删除）会确定性写回 `.svg`，并记进
    `_internal/05_review/applied_svg_edits.json`。问题是同一页还有第二个写手：模型自己的
    生成脚本 —— 脚本一跑就是整份 SVG 重写，人那一笔不在脚本里，于是静默消失。

    所以这里不问「画面的风格对不对」，只问一件事实：**人改完那一版，还是现在这一版吗？**
    不是、而且没人交代过，就报出来。人在这一页上的决定只能由人撤，不能由重画顺手抹掉。

    交代走 `ack-human-edit`（要写清实际怎么处理的）。误报的代价是模型多写一句话；
    漏报的代价是人白改一场 —— 所以宁可报。
    """
    if (root/'_internal/06_workbench/head.json').is_file(): return []
    pages={p['page_key']:p for p in content(root)['pages']}
    human=human_edits(root)
    problems=[]
    for k in keys:
        page=pages.get(k)
        # 只看账本里真有人改过的页。这不只是省事：`page_version` 要读 SVG，
        # 而 CREATE 阶段页面还没写出来 —— 对全量页面无脑算版本会把 `next` 打成 errno
        # （video 路线实测：`next` 报 FileNotFoundError 而不是给出下一步动作）。
        if page is None or k not in human: continue
        if not (root/SVG/(k+'.svg')).is_file(): continue
        try:
            version=page_version(root,page)
        except OSError:
            continue
        state=human_edit_state(root,k,version)
        if not state or state['carried'] or state['acknowledged']: continue
        edits=state['edits']
        if edits:
            tags='、'.join(sorted({str(e.get('tag') or '元素') for e in edits}))
            what=f'{len(edits)} 笔：{tags}'
            where=(f'先看改了什么：账本 `{REVIEW}/{APPLIED_EDITS_FILE}` 里的 edits，'
                   f'人改完那版 SVG 快照在 {state["svg_snapshot"] or "未留档"}')
        else:
            # 扩容之前记的账只有哈希，没有逐笔内容 —— 别把「0 笔」说成"什么都没改"。
            what='内容未记账（这条记录写在账本扩容之前，只有哈希）'
            where=(f'逐笔内容要回 `{REVIEW}/history/round-NN.json` 查（那一轮的 `svg_edits` 就在里面）')
        problems.append({
            'page':k,
            'human_edit':state,
            'error':(f'{k} 在 {state["applied_at"]} 被人手动改过（{what}），'
                     f'但现在这一版已经不是人改完那一版了 —— 人那一笔很可能被整份重写覆盖掉。'
                     f'{where}，把它带进新版或恢复，'
                     f'再交代：ppt_pipeline.py <project> ack-human-edit --page {k} --note "..."'),
        })
    return problems

def check(root, keys):
    m=sync(root); require_direction(root); contract=require_contract(root)
    ensure(root)
    pages=content(root)['pages']; selected=keys or [p['page_key'] for p in pages]
    if set(selected)-{p['page_key'] for p in pages}: raise ValueError('Unknown page key')
    results=[]
    for p in pages:
        k=p['page_key']
        if k not in selected: continue
        try:
            v=page_version(root,p)
            if rendered(root,k,v):
                rec=read(root/VALIDATION/(k+'.json'),{})
                results.append({'page':k,'status':'unchanged','render_token':digest(rec),
                                'issues':rec.get('validator',{})}); continue
            page=get_page(root,k)
            svg=Path(page['svg_path'])
            # Both validator and renderer read this immutable revision, never the live view.
            from render_svg_png import PLAYWRIGHT_SNIPPET
            png=root/PNG/(k+'.png')
            old=read(root/VALIDATION/(k+'.json'),{})
            with tempfile.TemporaryDirectory(prefix='ppt-render-') as temporary:
                temp=Path(temporary);report=temp/'validator.json'
                argv=validator_argv(root,m,k,p.get('mode') or '读',report=report,source=svg)
                val=subprocess.run(argv,capture_output=True,text=True)
                data=read(report,{})
                run('-c',PLAYWRIGHT_SNIPPET,temp,svg)
                rendered_png=temp/(svg.stem+'.png')
                provenance=record_render(root,k,page['revision'],rendered_png,
                                         'render_svg_png.py:sha256:'+sha(SCRIPTS/'render_svg_png.py'))
                if page_version(root,p)!=v:
                    raise ValueError('Page changed during rendering; old render archived, rerun check')
                write(root/VALIDATION/(k+'-validator.json'),data)
            rec={'version':v,'errors':data.get('summary',{}).get('errors',1) if not val.returncode else max(1,data.get('summary',{}).get('errors',1)),
                'png_sha256':provenance['png_sha256'],'validator':data,
                'revision':page['revision'],'renderer':provenance['renderer']}
            write(root/VALIDATION/(k+'.json'),rec)
            # 版本换了但图没换（例如只改了 notes）：把上一条看图记录承接过来，不要求重看。
            carried=carry_inspection(root,k,old.get('png_sha256'),rec)
            results.append({'page':k,'status':'pass' if rec['errors']==0 else 'fix','render_token':digest(rec),'png':str(png),'issues':data,**({'inspection_carried':True} if carried else {})})
        except (ValueError,OSError,ET.ParseError) as e: results.append({'page':k,'status':'blocked','error':str(e)})
    # Read-only measurements for the model's own design self-check. Facts, never pass/fail.
    obs=design_observations_deck(root,[r['page'] for r in results if r.get('page')])
    for r in results:
        if r.get('page') in obs: r['design']=obs[r['page']]
    from render_svg_png import make_contact_sheet
    files=[root/PNG/(p['page_key']+'.png') for p in pages if (root/PNG/(p['page_key']+'.png')).exists()]
    if files: make_contact_sheet(files,root/'_internal/03_png_preview/full_deck_contact_sheet.png')
    # 人那一笔还在不在 —— 独立于画面检查的另一条事实，所以单独标上去而不是混进 validator 的 issues。
    for problem in human_edit_problems(root,[r['page'] for r in results if r.get('page')]):
        hit=next((r for r in results if r.get('page')==problem['page']),None)
        if hit is None: continue
        hit['status']='fix'
        hit['human_edit']=problem['human_edit']
        hit['human_edit_error']=problem['error']
    event(root,'check',pages=selected)
    return {'route':route(root),'contract':contract,'pages':results}

def inspect(root,k,token,note,first_glance,design_check,position,verdict):
    """记下「这一页我看过了」。

    要成立，除了三个观察字段，还要**指出当前 PNG 上的一处位置**（落在画布内），
    并**明确选一个**：`--clean`（看过，无缺陷）或 `--must-fix`（看过，有缺陷且已记录）。
    填 `ok`／`👀` 不通过——这条闸门以前是这么被绕过去的。
    """
    ps={p['page_key']:p for p in content(root)['pages']}
    if k not in ps: raise ValueError('Unknown page')
    if verdict not in ('clean','must_fix'): raise ValueError('Choose exactly one of --clean / --must-fix')
    rec=read(root/VALIDATION/(k+'.json'),{})
    if digest(rec)!=token or not rendered(root,k,page_version(root,ps[k])): raise ValueError('Stale render token: rerun check and inspect the current PNG')
    if not note.strip(): raise ValueError('Record concrete visual findings after viewing PNG')
    if not first_glance.strip(): raise ValueError('Name the one element the eye lands on first (--first-glance)')
    if not design_check.strip(): raise ValueError('State which design rules you checked against and any violation found (--design-check)')
    try: box=parse_position(position)
    except ValueError as exc: raise ValueError(str(exc)+'；'+WATCH_THE_BIG_PNG)
    records=read(root/VALIDATION/'inspections.json',{})
    records[k]={'render_token':token,'note':note,'first_glance':first_glance,
                'design_check':design_check,'position':position,'verdict':verdict,
                'must_fix':verdict=='must_fix'}
    write(root/VALIDATION/'inspections.json',records)
    return {'page':k,'inspected':verdict=='clean','verdict':verdict,'position':box}

def resolve(root,feedback_id,note,result_revision,operation_id):
    task=ensure(root)['tasks'].get(feedback_id)
    if not task or len(task['pages'])!=1:
        raise ValueError('Use store resolve with results mapping for multi-page tasks')
    key=next(iter(task['pages']))
    return commit(root,{'op':'resolve','task_id':feedback_id,'operation_id':operation_id,
                        'results':{key:result_revision},'note':note,'author':'model'})

def unresolved(root):
    return [dict(task,task_id=identity) for identity,task in ensure(root)['tasks'].items()
            if task.get('status')=='pending']

def make_review(root):
    """出审阅页。**页面模板升级也算"这一版页面该重出"** —— 理由见 `template_fingerprint`。

    `review_current` 只比"磁盘上的页面 vs 快照"，而页面与快照是一起写下的：模板换了以后
    两者照样互相印证，只看它就会把一版旧页面当成最新的（2026-10-06 真人报的右栏问题就是这样
    卡住的：模板改了，项目里的页面还是旧的）。所以再审模板与令牌表的指纹。
    """
    sync(root); ensure(root)
    from generate_review_html import generate, template_fingerprint
    if review_current(root) and review_snapshot(root).get('template_sha256')==template_fingerprint():
        return review_snapshot(root)
    return generate(root)

def template_review(root, port=0, surface_only=False):
    """模板审阅：生成审阅页与 surface，然后交给公共件的宿主（与 `review_open` 同一套两种模式）。

    这条路上不再有本 Skill 自己的 HTTP 服务器（`review_server.py` 已退役）：宿主由
    `planners-review-core` 提供（无插件时 `serve-review.mjs`），页面通过桥说话。

      · `surface_only=True`（CLI `--surface-only`）——**有 `review_open` 工具时走这条**：只生成页面、
        写 surface、校验 surface，报出 **surface 的绝对路径**给宿主去挂；不起宿主、不开浏览器。
      · 默认（`False`）——没有那个工具时走这条：起无插件宿主并**打开浏览器**。开浏览器是**一件事**，
        只有一套行为（公共件 `review-host.mjs` 的 `open`），本 Skill 里那处 `webbrowser.open` 随之删除。

    模板审阅与页面审阅是**两个主体**（单位是 `layout_id` 不是 `page_key`，决定词表是
    `pass`/`discard`/`revise`，粒度是整批）——它们的 surface 字段逐条独立判过，见
    `review_surface.TEMPLATE`。
    """
    run(SCRIPTS/'generate_template_review_html.py', root)
    face=review_surface.describe('template')
    if surface_only:
        surface=review_surface.write_surface(root,'template')
        review_surface.validate_surface(root,'template')
        return {'status':'surface_ready','face':'template','surface':str(surface.resolve()),
                'entry':str((root/face['entry']).resolve()),
                'feedback_path':str(review_surface.feedback_path(root,'template').resolve()),
                'host_started':False,
                'next_action_zh':'把 surface 的绝对路径交给宿主的 review_open 工具（有插件时）；'
                                 '没有那个工具就重跑 template-review（不带 --surface-only）起本地宿主。'}
    info=review_surface.open_review(root,port=port,name='template')
    return {'status':'awaiting_user','face':'template','url':info['url'],'pid':info['pid'],
            'started':info['started'],'reused':info['reused'],'opened':info.get('opened',False),
            'surface':info['surface'],'entry':info['entry'],'feedback_path':info['feedback_path'],
            'wake_log':info['wake_log'],'host_state':str(review_surface.host_state_path(root,'template')),
            'next_action_zh':'作者在页面上逐 Layout 决定通过／舍弃／返修（全部通过时必须填模板名）；'
                             '没有插件时 wake 落在日志里，人回对话说一声「已完成」。'}

def review_open(root, port=0, surface_only=False):
    """页面审阅：生成审阅页与 surface，然后交给公共件的宿主（有插件时是 DSH 侧栏）。

    这条路上不再有本 Skill 自己的 HTTP 服务器：宿主由 `planners-review-core` 提供
    （无插件时 `serve-review.mjs`），页面与它通过桥说话。本 Skill 只负责写 surface、
    判断宿主死活、把 URL 打开（`review_surface.py`）。

    **两种模式，按"宿主有没有 `review_open` 工具"选**（Agent 侧一眼可判，Skill 不猜环境）：

      · `surface_only=True`（CLI `--surface-only`）——**有那个工具时走这条**：只生成页面、
        写 surface、校验 surface，报出 **surface 的绝对路径**给宿主去挂；**不起宿主、不开浏览器**。
        起了就会有两套界面同时写同一个 `feedback.json`。
      · 默认（`False`）——**没有那个工具时走这条**：起无插件宿主（`serve-review.mjs`）并打开浏览器。

    `started` / `reused` 仍然报出来：作者要据此判断 URL 是不是新的。
    """
    make_review(root)
    if surface_only:
        surface=review_surface.write_surface(root)          # 幂等：与页面一起生成过
        review_surface.validate_surface(root)
        return {'status':'surface_ready','surface':str(surface.resolve()),
                'entry':str((root/review_surface.PAGE_REL).resolve()),
                'feedback_path':str((root/review_surface.FEEDBACK_REL).resolve()),
                'host_started':False,
                'next_action_zh':'把 surface 的绝对路径交给宿主的 review_open 工具（有插件时）；'
                                 '没有那个工具就重跑 review（不带 --surface-only）起本地宿主。'}
    info=review_surface.open_review(root,port=port)
    return {'url':info['url'],'status':'awaiting_user','pid':info['pid'],'started':info['started'],
            'reused':info['reused'],'surface':info['surface'],'feedback_path':info['feedback_path'],
            'wake_log':info['wake_log'],'entry':str(root/review_surface.PAGE_REL),
            'host_state':str(root/review_surface.HOST_STATE_REL),
            'next_action_zh':'作者在页面上逐页审：每页提交只重出那一页；没有插件时 wake 落在日志里，'
                             '人回对话说一声「已完成」。'}

REVIEW_REMINDER=('这套页面还没有走过整套人工审阅。导出已经完成，可以继续；'
                 '要现在跑 review 让用户逐页过一遍吗？（审阅是可选步骤，不阻塞导出）')
VIDEO_ROUTE_NO_PPTX=('视频路线的出口是 '+VIDEO_DELIVERABLE+'，不导出 PPTX：'
                     '这条路的画面后面要做动画，没有下游消费者需要 PPT。'
                     '要走幻灯片出口，就在新目录按幻灯片路线重新初始化。')

@contextmanager
def export_lock(directory):
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(lock,fcntl.LOCK_UN)


def latest_export(root,record):
    # The alias is convenient, not export evidence. Serialize alias and pointer updates.
    with export_lock(root/PROJECT):
        fd,temporary=tempfile.mkstemp(prefix='.final_deck-',suffix='.pptx',dir=root)
        os.close(fd)
        try:
            shutil.copyfile(record['output_path'],temporary)
            os.replace(temporary,root/'final_deck.pptx')
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        write(root/PROJECT/'export.json',record)


def export(root,snapshot_path=None):
    root=Path(root).resolve()
    if snapshot_path is not None:
        frozen=load_snapshot(root,snapshot_path)
    else:
        sync(root); require_direction(root); require_contract(root)
        frozen=snapshot(root,purpose=route(root))
    v={p['page_key']:p['revision'] for p in frozen['pages']}
    problems=layout_check(root,frozen['order'],export_snapshot=frozen)
    if problems: raise ValueError('检查画面在导出时拦下了这些页面，先修再导出：'+json.dumps(problems,ensure_ascii=False))
    if frozen['route']=='video':
        rec={'snapshot_id':frozen['snapshot_id'],'snapshot_path':frozen['path'],
             'snapshot_sha256':sha(frozen['path']),'versions':v,'route':'video',
             'page_count':len(v),'visual_verification':'not_requested'}
        rec['content_delta']={p['page_key']:p.get('content_delta',[]) for p in frozen['pages']}
        rec['content_binding']=frozen.get('content_binding','unchecked')
        if 'changed_needs_check' in frozen: rec['changed_needs_check']=frozen['changed_needs_check']
        write(root/PROJECT/'video_export.json',rec); event(root,'video_snapshot',**rec)
        return rec
    job=root/OUTPUT/frozen['snapshot_id']
    with export_lock(job):
        record_path=job/'export.json';target=job/'final_deck.pptx'
        rec=read(record_path,{})
        if rec:
            if (rec.get('snapshot_sha256')!=sha(frozen['path']) or not target.is_file()
                    or rec.get('pptx_sha256')!=sha(target)):
                raise ValueError('Recorded export is damaged; preserve it and export a new snapshot')
            for filename,hash_key in (('speaker_notes.json','notes_sha256'),
                                      ('conversion.json','conversion_report_sha256')):
                artifact=job/filename
                if not artifact.is_file() or rec.get(hash_key)!=sha(artifact):
                    raise ValueError('Recorded export is damaged; preserve it and export a new snapshot')
            latest_export(root,rec)
            return rec
        notes_path=job/'speaker_notes.json';report_path=job/'conversion.json'
        notes={p['page_key']+'.svg':p.get('notes','') for p in frozen['pages']}
        write(notes_path,notes)
        frozen_pages={p['page_key']:p for p in frozen['pages']}
        draft=job/'.final_deck.pptx'
        run(SCRIPTS/'native_svg_to_ppt.py',*[Path(frozen['root'])/frozen_pages[k]['svg'] for k in frozen['order']],'-o',draft,'--auto-size','--match-aspect','--strict-missing-images','--notes',notes_path,'--report',report_path)
        from pptx import Presentation
        prs=Presentation(draft)
        if len(prs.slides)!=len(v): raise ValueError('Export page count differs')
        os.replace(draft,target)
        rec={'snapshot_id':frozen['snapshot_id'],'snapshot_path':frozen['path'],
             'snapshot_sha256':sha(frozen['path']),'versions':v,'order':frozen['order'],
             'route':'slides','output_path':str(target),'pptx_sha256':sha(target),
             'notes_path':str(notes_path),'notes_sha256':sha(notes_path),
             'conversion_report':str(report_path),'conversion_report_sha256':sha(report_path),
             'converter':'native_svg_to_ppt.py:sha256:'+sha(SCRIPTS/'native_svg_to_ppt.py'),
             'page_count':len(v),'visual_verification':'pending',
             'template_verification':'intrinsic_svg_only'}
        write(record_path,rec);latest_export(root,rec);event(root,'export',**rec)
        return rec

def export_inspect(root,note,preview,snapshot_path=None):
    root=Path(root).resolve()
    if snapshot_path is not None:
        frozen=load_snapshot(root,snapshot_path)
        rec=read(root/OUTPUT/frozen['snapshot_id']/'export.json',{})
    else:
        rec=read(root/PROJECT/'export.json',{})
    if rec.get('route')=='video' or (not rec and route(root)=='video'): raise ValueError(VIDEO_ROUTE_NO_PPTX)
    frozen_path=Path(rec.get('snapshot_path',''))
    output=local(root,rec['output_path']) if rec.get('output_path') else root/'final_deck.pptx'
    if (not frozen_path.is_file() or rec.get('snapshot_sha256')!=sha(frozen_path)
            or not output.is_file() or rec.get('pptx_sha256')!=sha(output)):
        raise ValueError('Export evidence is stale')
    if not note.strip() or not preview: raise ValueError('Provide actual PPTX-rendered preview files and visual findings')
    files=[local(root,p) for p in preview]
    if len(files)!=len(rec['versions']) or len(set(files))!=len(files): raise ValueError('Provide one distinct PPTX-rendered PNG/JPEG per slide')
    from PIL import Image
    for image in files:
        if image.suffix.lower() not in {'.png','.jpg','.jpeg'}: raise ValueError('Use actual raster PPTX previews')
        with Image.open(image) as im: im.verify()
    rec.update(visual_verification='inspected',note=note,preview_hashes={str(p.relative_to(root)):sha(p) for p in files})
    job=root/OUTPUT/rec['snapshot_id']
    with export_lock(job):
        write(job/'export.json',rec)
        with export_lock(root/PROJECT):
            if read(root/PROJECT/'export.json',{}).get('snapshot_id')==rec['snapshot_id']:
                write(root/PROJECT/'export.json',rec)
    return rec

def unwritten_pages(root, pages):
    return [p['page_key'] for p in pages if not (root/SVG/(p['page_key']+'.svg')).is_file()]

def create_instruction(root, pages, detail=''):
    """给动作，不给 errno。

    `next` 是恢复提示：说清哪些页面还没写、下一步做什么。Python 异常原文
    （`[Errno 2] No such file or directory`）留在一个单独的字段里备查，不当指令。
    """
    missing=unwritten_pages(root,pages)
    if missing:
        text=(f'还没有画出这些页面：{"、".join(missing)}。读取 get_page 的 revision、用户保护与任务，逐页写候选 SVG，'
              '先用 store op=checkout 获取候选，再用 workbench_store.py --root <project> '
              '--command-json 从 JSON stdin 提交 op=save、operation_id、author=model、page_key、'
              'candidate 绝对路径、base_revision；'
              f'然后 {("check --pages "+" ".join(missing)) if len(missing)<len(pages) else "check"}，'
              f'看这一页的 PNG 大图，再用返回的 render_token 跑 inspect。')
    else:
        text=('按 check 报的问题修改候选并通过 store 提交，重跑 check 生成当前 PNG，'
              '看大图后用返回的 render_token 跑 inspect。')
    result={'state':'WORKBENCH','route':route(root),'pages':missing or [p['page_key'] for p in pages],'instruction':text,
            'stage':str(SCRIPTS.parent/'references/workflow/04_svg_stage.md')}
    if detail: result['detail']=detail
    return result

def next_action(root):
    """Read store tasks, report raw legacy recovery, and expose technical actions."""
    # Initialize before touching legacy feedback: tree indexes are not store identities.
    try:
        sync(root)
    except ValueError as error:
        return {'state':'CONTENT','instruction':str(error)}
    try:
        ensure(root)
    except ValueError as error:
        return {'state':'WORKBENCH','error':str(error),
                'instruction':'Preserve any conflicting file as a candidate; inspect store state before submitting.'}
    intake=consume(root)
    try:
        template_intake=template_feedback.consume(root)
    except ValueError as error:
        template_intake={'error':str(error)}
    result=_next_action(root)
    if isinstance(result,dict) and 'contract' not in result:
        result['contract']=contract_result(root)
    if intake: result['legacy_feedback_recovery']=intake
    _attach_template_intake(result,template_intake)
    return result

def _attach_human_edits(result,root):
    """人手动改过的页被整页重写、又没人交代过 —— 在**入口**就说出来。

    这件事不能等模型自己去翻账本才发现：人白改一场，就是这么发生的（2026-10-05）。
    人改的东西不归模型顺手抹掉；要覆盖可以，但必须先说清怎么处理的。
    """
    if not isinstance(result,dict): return
    lost=human_edit_problems(root,[p['page_key'] for p in content(root)['pages']])
    if not lost: return
    result['human_edits_lost']=[{'page':x['page'],'applied_at':x['human_edit']['applied_at'],
                                 'edits':x['human_edit']['edits'],
                                 'svg_snapshot':x['human_edit']['svg_snapshot'],
                                 'message':x['error']} for x in lost]
    result['human_edits_lost_zh']=('有人手动改过的页被整页重写了，还没人交代过怎么处理（'
        +'、'.join(x['page'] for x in lost)+'）。人在页面上的决定只能由人撤 —— '
        '先看账本里的 edits 和人改完那版 SVG 快照，把它带进新版或恢复，'
        '再跑 ack-human-edit 说明你实际怎么处理的。')

def _attach_template_intake(result,intake):
    """把模板审阅的收件结果报出来（键与页面那条**不同名**：两个主体，两份事实）。

    与页面审阅那条一样：只报事实，不替状态机做决定。`stale` 表示这份反馈绑的是上一版
    模板审阅页 —— 它**不算批准**（发布闸门按 `review_id` 比，结构上就过不去）。
    形状不对（页面写坏、人手改过）不当场抛：报出来让人决定修还是重审。
    """
    if not intake or not isinstance(result,dict): return
    if 'error' in intake:
        result['template_review_intake']={'error':intake['error']}
        result['template_review_intake_error_zh']=('模板反馈文件的形状不对：'+intake['error']
            +'。修掉或删掉 _internal/00_project/template_feedback.json 再继续（别拿它当依据）。')
        return
    summary=intake['summary']
    result['template_review_intake']={
        'path':intake['path'],'stale':intake['stale'],'all_pass':summary['all_pass'],
        'passed':summary['passed'],'discarded_layouts':summary['discarded_layouts'],
        'revision_layouts':summary['revision_layouts'],'template_name':summary['template_name'],
        'errors':intake['errors'],'first_time':intake['first_time'],
    }
    entry=result['template_review_intake']
    if intake['stale']:
        entry['message']=('这份模板反馈绑的是上一版审阅页（review_id 对不上）：它不算批准。'
                          '重新跑 template-review 生成一版再让人决定。')
    elif intake['errors']:
        entry['message']=('这份模板反馈没通过校验：'+'；'.join(intake['errors'])+'。'
                          '页面上应该已经拦过同样的规则；对不上就重新生成审阅页再提交。')
    elif summary['all_pass']:
        entry['message']=('模板 '+summary['template_name']+' 全部 Layout 通过：可以 '
                          'template_library.py publish 入库了。')
    else:
        entry['message']=('模板审阅：通过 '+str(len(summary['passed']))+' 个 / 返修 '
                          +str(len(summary['revision_layouts']))+' 个 / 舍弃 '
                          +str(len(summary['discarded_layouts']))+' 个 —— 按反馈重建模板后再审一遍。')

def _attach_intake(result,intake):
    """把收件结果报出来。

    键叫 `review_intake` 而不是 `feedback`：`_next_action` 的 CREATE 分支已经用 `feedback`
    装「还没处理完的条目」，两个都叫 `feedback` 会把那串条目盖掉（本轮踩过）。

    「这份反馈绑的是不是当前这一版审阅页」必须看得见：对不上就是上一轮的，它**不算批准**
    （`approvals()` 按版本比），页面上也已经提示过「这一页已更新，先复核」。这里只报告事实，
    不替状态机做决定——上一轮的 items 仍是模型要继续处理的东西。

    形状不对（页面/宿主写坏了、人手改过）不当场抛：报出来，让模型决定修还是重审。
    """
    if not intake or not isinstance(result,dict): return
    if 'error' in intake:
        result['review_intake']={'error':intake['error']}
        result['review_intake_error_zh']=('反馈文件的形状不对：'+intake['error']
            +'。修掉或删掉 '+REVIEW+'/feedback.json 再继续（别拿它当依据）。')
        return
    result['review_intake']={'path':intake['path'],'stale':intake['stale'],'archived':intake['archived']}
    if intake.get('suppressed'):
        # 按"意见的生命周期"收下的东西：与已落实的历史完全相同 → 不生成待办。说出来，别静默。
        result['review_intake']['suppressed']=intake['suppressed']
        result['review_intake']['suppressed_zh']=('有一页的这条意见与已经落实并关闭过的那条一模一样：'
            '按规则它不再成为待办（原件在 history/round-NN.json 里可回查）。人若确实还想改，换一种说法再提。')
    if intake.get('unrecorded'):
        # 宿主写过、却没落进 feedback.json 的提交：接回来，别让人的字只活在对话里（G-32）。
        result['review_intake']['unrecorded']=[{
            'at':row.get('at'),'submitted_at':row.get('submitted_at'),'unit':row.get('unit'),
            'pages':{k:{'decision':(v or {}).get('decision'),'feedback':(v or {}).get('feedback')}
                     for k,v in (row.get('pages') or {}).items()
                     if (v or {}).get('decision') not in (None,'pending')}} for row in intake['unrecorded']]
        result['review_intake']['unrecorded_zh']=('有提交只到了唤醒、没写进 feedback.json（宿主接入日志里还留着全文）。'
            '上面 unrecorded 就是它们——按它继续改，不要因为文件里没有就当成没提过。')
    if intake['stale']:
        result['review_intake']['message']=('这份反馈绑的是上一版审阅页（review_id 对不上）：它不算批准。'
            '页面上已提示「这一页已更新，先复核」——等作者复核后再提交，或直接按 items 继续改。')

def _next_action(root):
    manifest(root)
    route_now=route(root)
    try: m=sync(root)
    except ValueError as e: return {'state':'CONTENT','instruction':str(e),'stage':str(SCRIPTS.parent/'references/workflow/02_content_stage.md')}
    pages=content(root)['pages']
    contract=contract_result(root)
    blocked=[i for i in contract if i.get('level')=='error']
    if blocked:
        return {'state':'CONTENT','route':route_now,'contract':contract,
                'instruction':'画面契约绑定对不上，先处理再往下走：'+'；'.join(i['message'] for i in blocked),
                'stage':str(SCRIPTS.parent/'references/workflow/03_video_route.md')}
    if route_now=='video' and direction_missing(root):
        return {'state':'CONTENT','missing':[str(root/DIRECTION)],'route':route_now,'contract':contract,
                'instruction':f'视频路线的第一步是把这套画面的秩序定下来：写 {DIRECTION}——'
                              '按 references/workflow/03_video_route.md 的四条视频约束'
                              '（字幕安全区、人物位置、不透明与透明、强调动画余量）组织。'
                              '这份文件在这条路线上是必填，缺了 check 会拦。',
                'stage':str(SCRIPTS.parent/'references/workflow/03_video_route.md')}
    tasks=unresolved(root)
    if tasks:
        return {'state':'WORKBENCH','route':route_now,'feedback':tasks,'export_available':True,
                'instruction':'Read get_page for each task page (revision, SVG, notes, protected edits), '
                              'then op=checkout for a candidate with pinned assets. '
                              'Edit the candidate, submit op=save with operation_id, author=model, candidate absolute path, '
                              'page_key, base_revision and task_id through workbench_store.py '
                              '--root <project> --command-json (JSON stdin). '
                              'Resolve the task with results mapping target page keys to saved revisions and a concrete note. '
                              'On conflict re-read the page; pending tasks do not block export.'}
    try: v=versions(root)
    except (ValueError,OSError,ET.ParseError) as e:
        return create_instruction(root,pages,detail=str(e))
    pending=[k for k,x in v.items() if not inspected(root,k,x)]
    if pending: return create_instruction(root,[p for p in pages if p['page_key'] in pending])

    if route_now=='video':
        return {'state':'WORKBENCH','route':route_now,'pages':list(v),'contract':contract,
                'actions':['review','check','export'],'export_available':True,
                'instruction':'Continue editing, open review, or export an immutable video snapshot. '
                              'Pass its snapshot.json to the animation layer; no page approval required.'}

    out=read(root/PROJECT/'export.json',{})
    output=local(root,out['output_path']) if out.get('output_path') else root/'final_deck.pptx'
    if out and output.is_file() and out.get('pptx_sha256')==sha(output):
        if (out.get('visual_verification')!='inspected'
                or len(out.get('preview_hashes',{}))!=out.get('page_count')
                or any(not local(root,p).is_file() or sha(local(root,p))!=h for p,h in out.get('preview_hashes',{}).items())):
            return {'state':'EXPORT_VERIFY','route':route_now,'snapshot_id':out.get('snapshot_id'),
                    'actions':['review','check','export','export-inspect'],
                    'instruction':'Inspect PPTX-rendered pages for this export, then export-inspect. '
                                  'Report unavailable rendering explicitly. The workbench remains editable.'}
    return {'state':'WORKBENCH','route':route_now,'actions':['review','check','export'],
            'export_available':True,'last_export':out,
            'instruction':'Continue candidate edits, open review, or export the current version snapshot.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project_dir');sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('next').add_argument('--json',action='store_true')
    c=sub.add_parser('check');c.add_argument('--pages',nargs='+')
    c=sub.add_parser('inspect');c.add_argument('--page',required=True);c.add_argument('--render-token',required=True);c.add_argument('--note',required=True);c.add_argument('--first-glance',required=True);c.add_argument('--design-check',required=True)
    c.add_argument('--position',required=True,help=f'当前 PNG 上的一处坐标或区域，例如 {POSITION_HELP}；必须落在画布内')
    verdict=c.add_mutually_exclusive_group(required=True)
    verdict.add_argument('--clean',action='store_true',help='看过了，没有缺陷')
    verdict.add_argument('--must-fix',action='store_true',help='看过了，有缺陷且已记录（工作台提示继续修改）')
    c=sub.add_parser('resolve');c.add_argument('--feedback-id',required=True);c.add_argument('--note',required=True);c.add_argument('--result-revision',required=True);c.add_argument('--operation-id',required=True)
    c=sub.add_parser('ack-human-edit');c.add_argument('--page',required=True)
    c.add_argument('--note',required=True,
                   help='你实际怎么处理人那一笔的：带进新版 / 被新版替掉 / 已恢复。空话不算')
    c=sub.add_parser('review')
    c.add_argument('--surface-only','--no-host',dest='surface_only',action='store_true',
                   help='只生成页面、写 surface、校验 surface 并报出它的绝对路径；不起宿主、不开浏览器'
                        '（宿主有 review_open 工具时用这条；没有就用不带开关的那条）')
    c=sub.add_parser('export');c.add_argument('--snapshot',help='Use this exact verified workbench snapshot.json; invalid input never falls back to current pages')
    t=sub.add_parser('template-review');t.add_argument('--port',type=int,default=0)
    t.add_argument('--surface-only','--no-host',action='store_true',dest='surface_only')
    c=sub.add_parser('export-inspect');c.add_argument('--note',required=True);c.add_argument('--previews',nargs='+',required=True);c.add_argument('--snapshot',help='Inspect the output job for this exact snapshot, rather than the latest export pointer')
    c=sub.add_parser('template');c.add_argument('--mode',choices=['autonomous','reference','fidelity'],required=True);c.add_argument('--template-id');c.add_argument('--reference')
    a=p.parse_args();root=Path(a.project_dir).expanduser().resolve()
    try:
        if a.command=='next':
            result=next_action(root)
        elif a.command=='check':result=check(root,a.pages)
        elif a.command=='inspect':result=inspect(root,a.page,a.render_token,a.note,a.first_glance,a.design_check,a.position,'must_fix' if a.must_fix else 'clean')
        elif a.command=='resolve':result=resolve(root,a.feedback_id,a.note,a.result_revision,a.operation_id)
        elif a.command=='ack-human-edit':result=ack_human_edit(root,a.page,a.note)
        elif a.command=='review':result=review_open(root,surface_only=a.surface_only)
        elif a.command=='export':result=export(root,snapshot_path=a.snapshot)
        elif a.command=='export-inspect':result=export_inspect(root,a.note,a.previews,snapshot_path=a.snapshot)
        elif a.command=='template-review':result=template_review(root,port=a.port,surface_only=a.surface_only)
        elif a.command=='template':
            m=manifest(root)
            if a.template_id:
                if a.mode!='fidelity':raise ValueError('Library templates require fidelity mode')
                run(SCRIPTS/'template/template_library.py','apply',root,'--template-id',a.template_id)
            if a.mode=='reference':
                if not a.reference:raise ValueError('Reference mode needs --reference <pptx|pdf|image|dir> so the reference pages are actually rendered before design_direction.md is written')
                run(SCRIPTS/'template/prepare_visual_references.py',a.reference,'--project',root)
            m['template_intake']={'mode':a.mode,'template_id':a.template_id};write(root/PROJECT/'page_manifest.json',m);result=m['template_intake']
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if a.command=='check' and any(x['status'] in {'blocked','fix'} for x in result['pages']):raise SystemExit(1)
    except (ValueError,OSError,ET.ParseError) as e:print(json.dumps({'error':str(e)},ensure_ascii=False));raise SystemExit(1)
if __name__=='__main__':main()
