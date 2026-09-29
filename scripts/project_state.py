"""状态与版本：项目在磁盘上是什么、版本是多少、派生状态怎么算。

它是一件事，不拆。对外只有下面 `__all__` 这一份 interface——消费方逐个
具名导入，不再 `import *`，这样「谁依赖了什么」是可审计的。
画幅常量不在这里：画幅归做画面，见 `canvas_frame.py`。
"""
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

import canvas_frame

__all__ = [
    'PROJECT', 'CONTENT', 'REVIEW', 'VALIDATION', 'SVG', 'PNG', 'TEMPLATE_REVIEW_SNAPSHOT',
    'DIRECTION', 'ROUTES',
    'read', 'write', 'digest', 'sha', 'local', 'event',
    'manifest', 'content', 'sync', 'images', 'page_version', 'versions',
    'rendered', 'inspected', 'parse_position', 'POSITION_HELP',
    'route', 'project_root_of', 'contract_binding', 'review_recorded',
    'design_observations', 'design_observations_deck',
    'review_snapshot', 'review_current', 'approvals', 'approved',
    'template_version', 'template_review_snapshot',
]

PROJECT = '_internal/00_project'
CONTENT = '_internal/01_content/page_content.json'
REVIEW = '_internal/05_review'
VALIDATION = '_internal/04_validation'
SVG = '_internal/02_svg_source'
PNG = '_internal/03_png_preview/pages'
TEMPLATE_REVIEW_SNAPSHOT = 'template_review_snapshot.json'
# 这套页面的共同秩序。视频路线上它是动手前的前置（缺了 check 会拦）。
DIRECTION = '_internal/01_content/design_direction.md'

# 两条出口路线。录像前的静态画面（video）交 SVG；幻灯片（slides）交可编辑 PPT。
ROUTES = ('slides', 'video')
DEFAULT_ROUTE = 'slides'

# `--position` 的坐标或区域：`x=180,y=240,w=864,h=90`，也接受省略 w/h。格式宽松，几何严格。
_POSITION_NUMBER = r'[-+]?\d+(?:\.\d+)?'
POSITION_RE = re.compile(
    rf'^\s*(?:x\s*=\s*)?(?P<x>{_POSITION_NUMBER})\s*,\s*(?:y\s*=\s*)?(?P<y>{_POSITION_NUMBER})'
    rf'(?:\s*,\s*(?:w\s*=\s*)?(?P<w>{_POSITION_NUMBER})\s*,\s*(?:h\s*=\s*)?(?P<h>{_POSITION_NUMBER}))?\s*$'
)
POSITION_HELP = 'x=180,y=240,w=864,h=90'

def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def write(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def local(root, rel):
    root = Path(root).resolve(); p = (root / rel).resolve()
    if p == root or root not in p.parents: raise ValueError('path outside project: '+str(rel))
    return p

def event(root, kind, **details):
    p = root / PROJECT / 'flow_events.jsonl'
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'type':kind,'details':details},ensure_ascii=False)+'\n')

def manifest(root):
    m = read(root / PROJECT / 'page_manifest.json', {})
    if m.get('version') != '5.0':
        raise ValueError('This project uses an older workflow. Finish with the archived Skill or migrate into a new v5 project; no in-place resume.')
    return m

def route(root):
    """这条路线的出口是哪一个：`slides`（可编辑 PPT）还是 `video`（录制前的静态画面）。

    路线记在项目状态里，是「该跑哪一半检查、完成标准是什么」的唯一取值处。
    没有记录的项目按幻灯片路线处理——那之前的项目都是这一条，不猜。
    """
    value = read(Path(root) / PROJECT / 'page_manifest.json', {}).get('route')
    return value if value in ROUTES else DEFAULT_ROUTE

def project_root_of(path):
    """项目里的任意路径 → 项目根（含 `_internal/00_project/page_manifest.json` 的那一层）。

    校验器拿到的可能是一个 SVG 文件或 `_internal/02_svg_source` 目录；路线从项目状态读，
    所以这里往上找根。不是项目里的路径就返回 None。
    """
    current = Path(path).resolve()
    for base in (current, *current.parents):
        if (base / PROJECT / 'page_manifest.json').is_file():
            return base
    return None

def parse_position(value):
    """`--position`：当前 PNG 上的一处坐标或区域，必须落在画布内。

    返回 {'x','y','w','h'}；w/h 只在给了区域时非零。落在画布外、或读不出坐标，
    一律 raise——「我看了某处」要能被指出是看在哪里。
    """
    match = POSITION_RE.match(str(value or ''))
    if not match:
        raise ValueError(
            f'位置要写成画布上的一处坐标或区域，例如 {POSITION_HELP} 或 x=180,y=240；看不懂：{value!r}')
    box = {key: float(match.group(key)) for key in ('x', 'y', 'w', 'h') if match.group(key) is not None}
    box.setdefault('w', 0.0)
    box.setdefault('h', 0.0)
    if box['w'] < 0 or box['h'] < 0:
        raise ValueError(f'区域的宽高不能是负数：{value}')
    if not (0 <= box['x'] <= canvas_frame.FRAME_W and 0 <= box['y'] <= canvas_frame.FRAME_H
            and box['x'] + box['w'] <= canvas_frame.FRAME_W
            and box['y'] + box['h'] <= canvas_frame.FRAME_H):
        raise ValueError(
            f"这一处位置落在画布外：{value}（画布 {canvas_frame.FRAME_W_INT}×{canvas_frame.FRAME_H_INT}）")
    return box

def contract_binding(root):
    """画面契约的绑定核对：**每核一项都留一条记录**。

    每条记录都有 `check`（核的是哪一项）与 `level`：

      ok         核过，没问题
      warning    核过，契约文件变过（画面可能还对，但契约已经不是交进来那一版）
      error      核过，对不上（口播稿改过，画面可能要重画）
      unchecked  没核成，`reason` 说清为什么

    返回空列表只有一个意思：**这条路没有交进来的契约**（幻灯片路线就是这种）。
    视频路线上永远至少有一条——「核过没问题」必须是个正面记录，
    否则「核过了」与「压根没核」在输出上是同一个样子。
    """
    root = Path(root)
    recorded = read(root / PROJECT / 'page_manifest.json', {}).get('visual_plan')
    if not isinstance(recorded, dict) or not str(recorded.get('path') or '').strip():
        if route(root) != 'video':
            return []
        return [{'check': 'visual_plan', 'level': 'unchecked', 'path': '',
                 'reason': '项目状态里没有记录交进来的契约',
                 'message': '这条路线按契约画，但项目状态里没有契约的位置，核不了。'}]
    plan = Path(str(recorded['path']))
    declared_version = str(recorded.get('contract_version') or '')
    records = []
    if not plan.is_file():
        records.append({'check': 'visual_plan_sha256', 'level': 'unchecked', 'path': str(plan),
                        'recorded': str(recorded.get('sha256') or ''),
                        'reason': f'契约文件已不在原处：{plan}',
                        'message': f'交进来的契约已不在原处，无法核对它变没变：{plan}'})
        current_version = None
    else:
        actual = sha(plan)
        same = actual == recorded.get('sha256')
        records.append({'check': 'visual_plan_sha256', 'level': 'ok' if same else 'warning',
                        'path': str(plan), 'recorded': str(recorded.get('sha256') or ''), 'actual': actual,
                        'message': (f'契约与画面还是同一版（sha256 {actual[:12]}）' if same else
                                    f'visual-plan.json 变了（交进来时 {str(recorded.get("sha256"))[:12]}，'
                                    f'现在 {actual[:12]}）；上屏文字可能已经不是被批准的那一份。')})
        try:
            current_version = str(json.loads(plan.read_text(encoding='utf-8')).get('contract_version') or '')
        except (OSError, ValueError):
            current_version = ''
    if current_version is None:
        records.append({'check': 'contract_version', 'level': 'unchecked', 'declared': declared_version,
                        'actual': '', 'reason': '契约文件不在原处',
                        'message': '契约不在原处，它是不是适配器认的那一版也核不了。'})
    elif current_version == declared_version:
        records.append({'check': 'contract_version', 'level': 'ok', 'declared': declared_version,
                        'actual': current_version,
                        'message': f'契约版本还是适配器认的那一版（{declared_version}）'})
    else:
        records.append({'check': 'contract_version', 'level': 'warning', 'declared': declared_version,
                        'actual': current_version,
                        'message': f'契约版本从 {declared_version} 变成 {current_version}；适配器只认 5.0。'})
    # 稿子就放在契约旁边（上游交过来的包里 `visual-plan.json` 与 `script.md` 是同一个目录），
    # 所以核对顺着**契约文件所在的目录**找——不是在本项目自己的目录里找。
    # 这一侧的核对来得及：作者是对着画面录的，等剪辑那一步再发现就只能事后返工。
    declared = str(recorded.get('script_hash') or '').strip()
    script = plan.parent / 'script.md'
    if not declared:
        records.append({'check': 'script_hash', 'level': 'unchecked', 'declared': '', 'actual': '',
                        'script': str(script), 'reason': '契约没有声明 script_hash',
                        'message': '契约没有声明 script_hash，无法核对它对应哪一版口播稿。'})
    elif not script.is_file():
        records.append({'check': 'script_hash', 'level': 'unchecked', 'declared': declared, 'actual': '',
                        'script': str(script), 'reason': f'契约旁边没有 {script.name}（找的是 {script}）',
                        'message': f'契约旁边没有 {script.name}（找的是 {script}），无法核对契约声明的 '
                                   'script_hash；这不是核对通过。'})
    else:
        actual = sha(script)
        same = actual == declared
        records.append({'check': 'script_hash', 'level': 'ok' if same else 'error',
                        'declared': declared, 'actual': actual, 'script': str(script),
                        'message': (f'script.md 与契约声明的 script_hash 一致（{actual[:12]}）' if same else
                                    f'契约声明的 script_hash 与 {script} 的实际内容不符'
                                    f'（声明 {declared[:12]}，实际 {actual[:12]}）——口播稿改过，画面可能要重画。')})
    return records

def review_recorded(root):
    """作者提交过整套审阅吗：有反馈记录，且覆盖当前全部页面、页面版本也对得上。

    版本对得上是「看过的是现在这一版」；页面改过之后旧记录不再算数，
    与页面审阅「改了就不再批准」同一条规则。
    """
    pages = read(Path(root) / REVIEW / 'feedback.json', {}).get('pages')
    if not isinstance(pages, dict) or not pages:
        return False
    try:
        current = versions(root)
    except (OSError, ValueError, ET.ParseError):
        return False
    if set(pages) != set(current):
        return False
    return all(isinstance(pages[key], dict) and pages[key].get('version') == current[key]
               for key in current)

def content(root):
    data = read(root / CONTENT, {})
    pages = data.get('pages', [])
    if not isinstance(pages, list) or not pages: raise ValueError('Write the lightweight page_content.json first.')
    seen = set(); used = set()
    source = read(root / PROJECT / 'source/source_assets.json', {})
    available = {a['asset_id'] for a in source.get('assets', [])}
    for p in pages:
        k = p.get('page_key', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', k) or k in seen: raise ValueError('Each page needs a unique stable page_key: '+k)
        seen.add(k)
        # title 是这张页的名字，必须写；`content` 允许为空——一屏可以只有画面，没有上屏文字。
        # 这是内容层的规则，只拦「任何风格下都是缺陷」的事；真正空白的页面由检查画面的空页
        # 判据兜底（既无文字也无图）。
        if not str(p.get('title','')).strip(): raise ValueError(k+': title required')
        mode = p.get('mode')
        if mode is not None and mode not in ('讲','读'): raise ValueError(k+': mode must be 讲 or 读')
        refs = p.get('source_assets', [])
        if not isinstance(refs,list) or any(not isinstance(x,str) for x in refs): raise ValueError(k+': source_assets must contain asset IDs')
        used.update(refs)
    excluded = data.get('unused_assets', {})
    if not isinstance(excluded,dict) or any(not str(v).strip() for v in excluded.values()): raise ValueError('unused_assets maps asset ID to a reason')
    if used - available or set(excluded)-available: raise ValueError('unknown source asset IDs')
    if available - used - set(excluded): raise ValueError('Source assets not accounted for: '+', '.join(sorted(available-used-set(excluded))))
    return data

def sync(root):
    m = manifest(root); c = content(root)
    m['project'] = c.get('project','')
    m['pages'] = [{'page_key':p['page_key'],'title':p['title'],'mode':p.get('mode') or '读','svg_path':f'{SVG}/{p["page_key"]}.svg','png_path':f'{PNG}/{p["page_key"]}.png'} for p in c['pages']]
    write(root / PROJECT / 'page_manifest.json',m)
    return m

def images(root, svg):
    root=Path(root).resolve()
    result=[]
    for i,node in enumerate(ET.parse(svg).getroot().iter()):
        if node.tag.split('}')[-1] != 'image': continue
        href = node.get('href',node.get('{http://www.w3.org/1999/xlink}href',''))
        if not href or href.startswith(('data:','http:','https:','#')): raise ValueError('Use local project image files: '+href[:60])
        p = local(root, str((Path(svg).parent / href).resolve()))
        if not p.is_file(): raise ValueError('Missing image: '+str(p))
        if node.get('preserveAspectRatio') == 'none': raise ValueError('Image stretching is prohibited')
        key = node.get('data-asset-key') or node.get('id') or f'image_{i}'
        result.append({'asset_key':key,'path':p.relative_to(root).as_posix(),'sha256':sha(p),'width':float(node.get('width',1)),'height':float(node.get('height',1)), 'fit':'cover' if 'slice' in node.get('preserveAspectRatio','') else 'contain'})
    if len({x['asset_key'] for x in result}) != len(result): raise ValueError('Duplicate image asset key')
    return result

def page_version(root, p):
    svg = root / SVG / (p['page_key']+'.svg')
    m = manifest(root)
    source = read(root / PROJECT / 'source/source_assets.json', {})
    assets = {a['asset_id']:a for a in source.get('assets',[])}
    dependencies = {aid:sha(local(root,assets[aid]['normalized_path'])) for aid in p.get('source_assets',[])}
    direction = root / DIRECTION
    # 没有源文档的路线（init 的 `--assets`）不写 source.md：底稿本身就是材料，它的内容已在
    # 'page' 里，实际用到的图在 'source_assets' 里。缺源文时给固定空值；有源文时仍是同一个
    # hash，所以既有页面的 digest 不变。
    document = root / PROJECT / 'source/source.md'
    template = root / PROJECT / 'fidelity_template'
    return digest({'page':p,'svg':sha(svg),'images':images(root,svg),'source_assets':dependencies,
        'source':sha(document) if document.exists() else '','direction':sha(direction) if direction.exists() else '',
        'mode':m.get('template_intake'), 'template':{str(f.relative_to(template)):sha(f) for f in sorted(template.rglob('*')) if f.is_file()} if m.get('template_intake',{}).get('mode')=='fidelity' else {}})

def versions(root):
    return {p['page_key']:page_version(root,p) for p in content(root)['pages']}

def rendered(root, k, version):
    rec = read(root / VALIDATION / (k+'.json'), {})
    png = root / PNG / (k+'.png')
    return bool(rec.get('version')==version and rec.get('errors')==0 and png.is_file() and rec.get('png_sha256')==sha(png))

def inspected(root,k,version):
    """这条看图记录成立吗。

    成立要同时满足：渲染是最新的；`note`／`first-glance`／`design-check` 都写了；
    **指出了当前 PNG 上的一处位置且落在画布内**；**明确选了「看过无缺陷」或「看过有缺陷」**。
    自由文本填满不算数——那是这条闸门以前被跳过的方式。
    """
    rec=read(root / VALIDATION / (k+'.json'),{})
    ins=read(root / VALIDATION / 'inspections.json',{}).get(k,{})
    if not (rendered(root,k,version) and ins.get('render_token')==digest(rec)):
        return False
    if not all(str(ins.get(f,'')).strip() for f in ('note','first_glance','design_check')):
        return False
    if ins.get('verdict') not in ('clean','must_fix'):
        return False
    try:
        parse_position(ins.get('position'))
    except ValueError:
        return False
    return ins.get('verdict')=='clean'


def design_observations(root, page_key):
    """Read-only measurements for the model's own design self-check.

    Facts about the page, not judgements: no pass/fail, no thresholds. They exist so
    the self-check in style_system.md can be done against numbers instead of memory.
    v6.0: Honors <g>/leaf transform, inline <style>/:root vars, and measures
    lowest_content_bottom across <text>, <rect>, <image>, <circle>, <ellipse>, <line>, <path>.
    """
    svg = root / SVG / (page_key + '.svg')
    if not svg.is_file():
        return {}
    raw_text = svg.read_text(encoding='utf-8-sig')
    root_el = ET.fromstring(raw_text)

    try:
        from native_svg_to_ppt import (
            _parse_path_to_points,
            compose_axis_aligned,
            inline_svg_styles_and_vars,
            parse_axis_aligned_transform,
        )
        inline_svg_styles_and_vars(root_el, raw_text)
    except Exception:
        def parse_axis_aligned_transform(_t):
            return (0.0, 0.0, 1.0, 1.0)
        def compose_axis_aligned(p, l):
            return (p[0] + p[2] * l[0], p[1] + p[3] * l[1], p[2] * l[2], p[3] * l[3])
        def _parse_path_to_points(*_a, **_kw):
            return []

    parent_map = {child: parent for parent in root_el.iter() for child in parent}

    def tag(n):
        return n.tag.split('}')[-1]

    def num(n, attr, default=0.0):
        val = n.get(attr)
        if val is None:
            return default
        m = re.search(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?", str(val))
        return float(m.group(0)) if m else default

    def acc_tf(n):
        chain = []
        cur = n
        while cur is not None:
            chain.append(cur)
            cur = parent_map.get(cur)
        chain.reverse()
        acc = (0.0, 0.0, 1.0, 1.0)
        for item in chain:
            acc = compose_axis_aligned(acc, parse_axis_aligned_transform(item.get('transform', '')))
        return acc

    def eff_font_size(n, sx, sy):
        fs = num(n, 'font-size', 0.0)
        if fs <= 0:
            cur = parent_map.get(n)
            while cur is not None:
                fs = num(cur, 'font-size', 0.0)
                if fs > 0:
                    break
                cur = parent_map.get(cur)
        return fs * min(sx, sy)

    texts = [n for n in root_el.iter() if tag(n) == 'text']
    rects = [n for n in root_el.iter() if tag(n) == 'rect']
    images_el = [n for n in root_el.iter() if tag(n) == 'image']
    circles = [n for n in root_el.iter() if tag(n) in ('circle', 'ellipse')]
    lines_el = [n for n in root_el.iter() if tag(n) == 'line']
    paths_el = [n for n in root_el.iter() if tag(n) == 'path']

    sizes = set()
    for n in texts:
        _, _, sx, sy = acc_tf(n)
        fs = eff_font_size(n, sx, sy)
        if fs > 0:
            sizes.add(round(fs))
        for child in n:
            if tag(child) == 'tspan':
                cfs = num(child, 'font-size', 0.0) * min(sx, sy)
                if cfs > 0:
                    sizes.add(round(cfs))
    sizes = sorted(sizes)
    scale_ratio = round(sizes[-1] / sizes[0], 2) if len(sizes) > 1 else None

    groups = {}
    for n in rects:
        _, _, sx, sy = acc_tf(n)
        w, h = num(n, 'width') * sx, num(n, 'height') * sy
        if (w >= canvas_frame.CONTAINER_MIN_W and h >= canvas_frame.CONTAINER_MIN_H
                and not (w >= canvas_frame.FULL_BLEED_W and h >= canvas_frame.FULL_BLEED_H)):
            groups[(round(w), round(h))] = groups.get((round(w), round(h)), 0) + 1
    equal_containers = [f'{w}x{h}×{c}' for (w, h), c in sorted(groups.items()) if c >= 2]

    bottom_candidates = []
    for n in texts:
        dx, dy, sx, sy = acc_tf(n)
        ey = dy + num(n, 'y') * sy
        efs = eff_font_size(n, sx, sy)
        if ey < canvas_frame.BODY_TEXT_MAX_Y:
            bottom_candidates.append(ey + efs * 0.2)

    for n in rects + images_el:
        dx, dy, sx, sy = acc_tf(n)
        ey = dy + num(n, 'y') * sy
        ew = num(n, 'width') * sx
        eh = num(n, 'height') * sy
        if ew <= 0 or eh <= 0:
            continue
        if ew >= canvas_frame.FULL_BLEED_W and eh >= canvas_frame.FULL_BLEED_H:
            continue
        # Ignore full-height vertical grid rules
        if ew <= 4 and eh >= canvas_frame.FRAME_H * 0.75:
            continue
        if ey < canvas_frame.BODY_TEXT_MAX_Y and (ey + eh) <= canvas_frame.FOOTER_RULE_Y + 10:
            bottom_candidates.append(ey + eh)

    for n in circles:
        dx, dy, sx, sy = acc_tf(n)
        cy = dy + num(n, 'cy') * sy
        ry = (num(n, 'ry') or num(n, 'r')) * sy
        if ry > 0 and cy < canvas_frame.BODY_TEXT_MAX_Y and (cy + ry) <= canvas_frame.FOOTER_RULE_Y + 10:
            bottom_candidates.append(cy + ry)

    for n in lines_el:
        dx, dy, sx, sy = acc_tf(n)
        y1 = dy + num(n, 'y1') * sy
        y2 = dy + num(n, 'y2') * sy
        max_y = max(y1, y2)
        if max_y < canvas_frame.BODY_TEXT_MAX_Y:
            bottom_candidates.append(max_y)

    for n in paths_el:
        d = n.get('d', '')
        if not d:
            continue
        dx, dy, sx, sy = acc_tf(n)
        subpaths = _parse_path_to_points(d, dx, dy, sx, sy)
        pts = [pt for sp in subpaths for pt in sp]
        if pts:
            max_y = max(py for _, py in pts)
            min_y = min(py for _, py in pts)
            if min_y < canvas_frame.BODY_TEXT_MAX_Y and max_y <= canvas_frame.FOOTER_RULE_Y + 10:
                bottom_candidates.append(max_y)

    lowest = round(max(bottom_candidates), 1) if bottom_candidates else None
    void = round(canvas_frame.FOOTER_RULE_Y - lowest, 1) if lowest is not None else None

    # Include footer text too: the footer/folio baselines are themselves cross-page anchors.
    small = []
    for n in texts:
        dx, dy, sx, sy = acc_tf(n)
        ey = dy + num(n, 'y') * sy
        efs = eff_font_size(n, sx, sy)
        if 0 < efs <= canvas_frame.SMALL_TEXT_MAX_PX:
            small.append(round(ey))
    small = sorted(set(small))

    return {
        'type_tiers': sizes,
        'scale_ratio': scale_ratio,
        'equal_containers': equal_containers,
        'lowest_content_bottom': lowest,
        'gap_to_footer_rule': void,
        'small_text_baselines': small,
    }


def design_observations_deck(root, page_keys):
    """Per-page observations plus which small-text baselines are shared across pages."""
    obs = {k: design_observations(root, k) for k in page_keys}
    seen = {}
    for o in obs.values():
        for y in o.get('small_text_baselines', []):
            seen[y] = seen.get(y, 0) + 1
    for o in obs.values():
        o['shared_small_baselines'] = sorted(y for y in o.get('small_text_baselines', []) if seen.get(y, 0) > 1)
    return obs


def review_snapshot(root):
    return read(root / REVIEW / 'snapshot.json',{})

def review_current(root):
    try:
        snap=review_snapshot(root); v=versions(root)
        return bool(snap and snap.get('versions')==v and snap.get('order')==list(v) and
            all(inspected(root,k,x) for k,x in v.items()) and
            snap.get('png_hashes')=={k:sha(root/PNG/(k+'.png')) for k in v} and
            snap.get('html_sha256')==sha(root/'02_visual_review.html'))
    except (OSError,ValueError,ET.ParseError): return False

def approvals(root):
    """Per-page approval survives only while its exact content and rendered image remain unchanged.

    `provenance.source` 认两个值：`review_page`（页面经宿主自己写反馈，现在这条路）与
    `review_server`（旧服务器写反馈的项目，仍然读得懂）。别的东西写进这个文件不算人工批准。
    """
    f=read(root/REVIEW/'feedback.json',{})
    if f.get('provenance',{}).get('source') not in ('review_page','review_server'): return {}
    result={}
    for p in content(root)['pages']:
        k=p['page_key']; item=f.get('pages',{}).get(k,{})
        try: v=page_version(root,p)
        except (OSError,ValueError): continue
        if item.get('version')==v and (root/PNG/(k+'.png')).is_file() and item.get('png_sha256')==sha(root/PNG/(k+'.png')) and inspected(root,k,v): result[k]=item
    return result

def approved(root):
    if not review_current(root): return False
    s=review_snapshot(root); f=read(root/REVIEW/'feedback.json',{})
    return f.get('review_id')==s.get('review_id') and not f.get('overall_feedback','').strip() and all(x.get('decision')=='approved' for x in approvals(root).values()) and len(approvals(root))==len(s['versions'])


def template_version(root):
    base=root/PROJECT
    paths=[base/'fidelity_template',base/'template_visuals',base/'template_media']
    files=[f for p in paths for f in p.rglob('*') if f.is_file()]
    files += [base/n for n in ('template_profile.json','template_asset_registry.json','template_canvas_self_review.json','template_worker_result.json') if (base/n).is_file()]
    return digest({str(f.relative_to(root)):sha(f) for f in files})


def template_review_snapshot(root):
    """模板审阅的握手快照：生成审阅页时写下，提交与发布时对照。

    页面审阅有 `snapshot.json` + `review_id`，模板审阅此前只有一个写在 HTML 里的
    内容摘要，因此旧标签页能批准新版本。这份快照把两者拉平。
    """
    return read(root / PROJECT / TEMPLATE_REVIEW_SNAPSHOT, {})
