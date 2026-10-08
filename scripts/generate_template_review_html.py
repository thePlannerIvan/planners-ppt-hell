#!/usr/bin/env python3
"""Generate the read-only, per-layout template review page.

模板审阅是一个独立主体（逐 Layout 通过／舍弃／返修 + 命名），**不是**页面审阅的
第二份画法，所以它不共用 `assets/review/review.html`：单位是 `layout_id` 不是 `page_key`，
决定词表是 `pass`/`discard`/`revise`，对照物是**源模板页**，粒度是**整批**（页面上只有一个
提交动作）。两份面的字段逐条独立判过，理由在 `scripts/review_surface.py`。

页面经公共缝说话（`review-surface/2.0.0`）：宿主把字节搬进来、把提交原样落盘、把人叫醒；
本页保留全部语义（审什么、怎么决定、反馈文件长什么样）。

三条硬要求（与页面审阅同一套，见公共件 `references/design-and-porting-rules.md`）：

  · **`{{REVIEW_BRIDGE}}` 裸标记独占一行** —— 宿主原地换成完整的一段标签，塞进 `src=""` 里会被撑破（R3）；
  · **内容不挂在握手上** —— 逐 Layout 的卡片是**服务端渲染进 HTML** 的，没有桥也看得全（R12）；
    连不上就自述「只读」，并且页面上**永久有一个 ⟳**（R11）；
  · **顶层不碰本地存储** —— 不透明源 iframe 里读它直接抛，整页脚本当场死、零报错。
"""
import argparse
import html
import json
import re
import uuid
import xml.etree.ElementTree as ET

from project_state import PROJECT, TEMPLATE_REVIEW_SNAPSHOT, sha, template_version, write
from pathlib import Path
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')

# 页面里的资产引用一律**相对 `dir`**（＝项目根），由页面经桥取 URL（R2 的第一个基准）。
# 原来写的是 `/_internal/...` 这种绝对路径：不透明帧里它指向宿主 origin，取不到。
MEDIA_PREFIX = '_internal/00_project/template_media/'
VISUALS_PREFIX = '_internal/00_project/template_visuals/'


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def esc(value):
    return html.escape(str(value or ""), quote=True)


MEDIA_HREF = re.compile(r"""(xlink:href|href)\s*=\s*(["'])(?:\.\./\.\./template_media/)([^"']+)\2""")
IMAGE_TAG = re.compile(r"<image\b[^>]*>")


def inline_canvas(path):
    """把 canvas SVG 内联进页面，并把里面的素材引用改成**相对 `dir`** 的地址。

    同时给这些 `<image>` 打上 `data-asset`：有桥时页面会把它们换成桥给的 URL（插件模式是帧内 blob），
    **但 href 保留** —— 没有桥时它是一条同源相对地址，图照样看得见（"没有桥也要能看"）。
    """
    text = MEDIA_HREF.sub(lambda m: f'{m.group(1)}={m.group(2)}{MEDIA_PREFIX}{m.group(3)}{m.group(2)}',
                          path.read_text(encoding="utf-8"))

    def tag(match):
        tag_text = match.group(0)
        already = MEDIA_HREF.search(tag_text)
        if not already or 'data-asset=' in tag_text:
            return tag_text
        return tag_text[:-1] + f' data-asset="{MEDIA_PREFIX}{already.group(3)}">'
    return IMAGE_TAG.sub(tag, text)


def inline_pack_canvas(root,path,tokens):
    tree=ET.parse(path).getroot()
    style=ET.Element('{http://www.w3.org/2000/svg}style')
    style.text=tokens
    tree.insert(0,style)
    for node in tree.iter():
        if node.tag.split('}')[-1]!='image': continue
        attr='href' if 'href' in node.attrib else '{http://www.w3.org/1999/xlink}href'
        href=node.get(attr,'')
        if href.startswith('data:'): continue
        target=(path.parent/href).resolve()
        if root not in target.parents or not target.is_file():
            raise ValueError('Template image must resolve inside project: '+href)
        rel=target.relative_to(root).as_posix()
        node.set(attr,rel);node.set('data-asset',rel)
    return ET.tostring(tree,encoding='unicode')


def generate_pack_review(root):
    from template.template_library import validate_pack_dir
    pack=root/PROJECT/'template_pack'
    validation=validate_pack_dir(pack)
    if not validation['valid']: raise ValueError('Incomplete template pack: '+str(validation['issues']))
    tokens=(pack/'tokens.css').read_text(encoding='utf-8')
    paths=[pack/'skyline_shell.svg',*sorted((pack/'primitives').glob('*.svg'))]
    layouts=[path.relative_to(pack).as_posix() for path in paths]
    cards=[]
    for index,(path,identity) in enumerate(zip(paths,layouts),1):
        cards.append(f'''<article class="card"><header><h2>{esc(identity)}</h2></header>
<div class="compare"><section class="canvas">{inline_pack_canvas(root,path,tokens)}</section></div>
<div class="decision"><fieldset data-decision="{esc(identity)}"><legend>此原语如何处理？</legend>
<label class="choice pass"><input type="radio" name="decision-{index}" value="pass"><span>通过</span></label>
<label class="choice discard"><input type="radio" name="decision-{index}" value="discard"><span>舍弃</span></label>
<label class="choice revise"><input type="radio" name="decision-{index}" value="revise"><span>返修</span></label></fieldset>
<textarea data-feedback="{esc(identity)}" placeholder="单独反馈"></textarea></div></article>''')
    anchors=''.join(f'<figure><img src="{esc(path.relative_to(root).as_posix())}" '
                    f'data-asset="{esc(path.relative_to(root).as_posix())}" alt="{esc(path.name)}"></figure>'
                    for path in sorted((pack/'anchors').glob('*.png')))
    contact=f'<pre>{esc(tokens)}</pre><pre>{esc((pack/"SPEC.md").read_text(encoding="utf-8"))}</pre><div class="thumbs">{anchors}</div>'
    version=template_version(root);review_id=uuid.uuid4().hex
    page=(PAGE.replace('__CARDS__',''.join(cards)).replace('__CONTACT__',contact)
          .replace('__LAYOUTS__',json.dumps(layouts,ensure_ascii=False))
          .replace('__REVIEW_ID__',review_id).replace('__VERSION__',version[:12]))
    out=root/'00_template_review.html';out.write_text(page,encoding='utf-8')
    write(root/PROJECT/TEMPLATE_REVIEW_SNAPSHOT,
          {'review_id':review_id,'template_version':version,'html_sha256':sha(out),
           'layouts':layouts,'package_format':'four_piece'})
    return out


PAGE = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>模板人工审阅</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#eef3f8;color:#182433;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.top{position:sticky;top:0;z-index:4;background:#06131b;color:#fff;padding:16px 30px;display:flex;gap:18px;align-items:center}
.top b{font-size:17px}
.top .meta{color:#9fb4c6;font-size:13px;margin-right:auto}
.top button{background:#1d3346;color:#fff;border:1px solid #2f4b63}
.stale{background:#7a2f0d;color:#fff;padding:12px 30px;font-weight:700}
main{max-width:1680px;margin:auto;padding:24px}
.summary,.card,.global{background:#fff;border:1px solid #dce4ec;border-radius:12px;margin-bottom:22px;overflow:hidden}
.summary,.global{padding:20px}
.card{scroll-margin-top:96px}
.card header{padding:15px 22px;border-bottom:1px solid #e5eaf0;display:flex;justify-content:space-between}
.compare{display:grid;grid-template-columns:1.25fr .75fr;gap:22px;padding:22px}
.canvas svg,.thumbs img{display:block;width:100%;height:auto;border:1px solid #d7dee7}
.thumbs{display:grid;grid-template-columns:1fr 1fr;gap:9px}
figure{margin:0}
figcaption,.muted{color:#697582;font-size:13px}
.decision{padding:0 22px 22px;display:grid;grid-template-columns:360px 1fr;gap:15px}
fieldset{border:1px solid #cfd8e2;border-radius:9px;padding:12px;display:flex;gap:8px;align-items:center}
legend{font-weight:700}
textarea,input,button{font:inherit}
textarea{width:100%;min-height:88px;padding:10px}
.choice input{position:absolute;opacity:0;pointer-events:none}
.choice span{display:inline-block;padding:10px 18px;border:1px solid #bcc7d3;border-radius:8px;background:#fff;font-weight:800;cursor:pointer}
.choice.pass input:checked+span{background:#087a51;color:#fff;border-color:#087a51}
.choice.discard input:checked+span{background:#3e4854;color:#fff;border-color:#3e4854}
.choice.revise input:checked+span{background:#a44a12;color:#fff;border-color:#a44a12}
.global input{width:100%;padding:10px;margin-bottom:10px}
.actions{position:sticky;bottom:0;z-index:5;background:#eef3f8ee;padding:15px;text-align:center;border-top:1px solid #d4dde6}
button{padding:12px 22px;border:0;border-radius:8px;color:#fff;background:#27506f;font-weight:800;cursor:pointer}
button.approve{background:#087a51}
#status{font-weight:700}
#status.warn{color:#a44a12}
#status.ok{color:#087a51}
#status.error{color:#a41a12}
@media(max-width:1000px){.compare,.decision{grid-template-columns:1fr}}
</style></head><body>
<div class="top"><b>模板提取人工审阅</b><span class="meta">每个 Layout 分别决定通过 / 舍弃 / 返修 · 模板版本 __VERSION__ · <span id="bridgeState">正在连审阅宿主…</span></span><button id="reload" title="拿到最新的一版页面">⟳ 重新加载</button></div>
<div class="stale" id="staleBar" hidden>这一版模板已经重建，你现在看到的 canvas 与决定都过期了 —— 点右上角 ⟳ 重新加载，再决定。</div>
<main><section class="summary"><h1>先看生产 canvas，再对照源模板</h1><p>通过会保留该 Layout；舍弃会在返修阶段删除该 Layout；返修必须留下具体意见。“全部通过”会自动把每个 Layout 设为通过并提交。</p>__CONTACT__</section>
__CARDS__
<section class="global"><h2>整体反馈与模板命名</h2><input id="templateName" placeholder="模板名称（全部 Layout 通过时必填）"><textarea id="overall" placeholder="整体反馈（可选）"></textarea></section></main>
<div class="actions"><button onclick="submitFeedback('submit_batch')">提交批次反馈</button> <button class="approve" onclick="approveAll()">全部通过</button><p id="status"></p></div>
{{REVIEW_BRIDGE}}
<script>
const layoutIds=__LAYOUTS__, REVIEW_ID="__REVIEW_ID__";
const SNAPSHOT_REL="_internal/00_project/template_review_snapshot.json";
let review=null, stale=false;
const $=(sel)=>document.querySelector(sel);
function status(text,kind){const el=$('#status');el.textContent=text||'';el.className=kind||''}
$('#reload').addEventListener('click',()=>location.reload());
// 资产：有桥就走桥（插件模式是帧内 blob、无插件是相对地址），没桥退化成同源相对地址。
// 这里不写任何宿主知识（base / 端口 / 绝对路径）。
async function assetFor(rel){
  if(review){try{return await review.asset(rel)}catch(error){return '/'+rel}}
  return '/'+rel;
}
async function hydrateAssets(){
  for(const el of document.querySelectorAll('[data-asset]')){
    const url=await assetFor(el.getAttribute('data-asset'));
    if(el.tagName==='IMG')el.setAttribute('src',url);
    else{el.setAttribute('href',url);el.setAttributeNS('http://www.w3.org/1999/xlink','xlink:href',url)}
  }
}
// R5：状态行只说自己核过的事 —— 宿主"接受"≠"通知到"；同一次提交重发也不许说成失败。
function wakeNote(verified){
  return verified?'宿主已在会话日志里核对进入队列':'宿主未核对 —— 若模型迟迟没反应，请回对话说一声';
}
async function readSnapshot(){
  if(!review)return null;
  try{return JSON.parse(await review.readText(SNAPSHOT_REL))}catch(error){return null}
}
async function refreshStale(){
  const snap=await readSnapshot();
  if(!snap)return;                                  // 读不到（例如插件还没支持 read）→ 不据此拦截，Skill 收件时仍会判
  if(String(snap.review_id||'')!==REVIEW_ID){stale=true;$('#staleBar').hidden=false}
}
async function push(payload){
  if(!review){status('本页只读：没有连上审阅宿主，反馈存不进去（请让宿主打开这一页）','warn');return {ok:false}}
  if(stale){status('这一版模板已经重建，先点 ⟳ 重新加载再决定。','error');return {ok:false}}
  const document_=collect(payload);
  try{
    await review.write(document_);
    const sent=payload.wake?await review.wake(payload.wake):null;
    if(!sent)return {ok:true,verified:null};
    if(sent.duplicate){
      return {ok:true,duplicate:true,notice:sent.notice||'已写入；本次没有新增通知（同一次提交之前已送达）'};
    }
    const verified=(sent&&sent.verified)||null;
    try{
      await review.write({...document_, provenance:{...document_.provenance,
        wake:{requested:true,verified,at:new Date().toISOString()}}});
    }catch(error){/* 记不上不影响这次提交已经成立 */}
    return {ok:true,verified};
  }catch(error){status('保存失败：'+error.message,'error');return {ok:false}}
}
function decisions(){
  const layouts={};let allPass=true,missing=false,revisionWithoutFeedback=false;
  for(const id of layoutIds){
    const box=document.querySelector('[data-decision="'+id+'"]');
    const choice=box.querySelector('input:checked')?.value||'';
    const feedback=document.querySelector('[data-feedback="'+id+'"]').value.trim();
    if(!choice)missing=true;
    if(choice!=='pass')allPass=false;
    if(choice==='revise'&&!feedback)revisionWithoutFeedback=true;
    layouts[id]={approved:choice==='pass',decision:choice,custom_feedback:feedback};
  }
  return {layouts,allPass,missing,revisionWithoutFeedback};
}
function collect(request){
  return {review_id:REVIEW_ID, submission_action:request.action,
          approved:request.allPass, all_approved:request.allPass,
          template_name:request.templateName, overall_feedback:request.overall, layouts:request.layouts,
          provenance:{source:'template_review_page',transport:(review&&review.transport)||'none',
                      surface:'planners-ppt-hell/template', submitted_at:new Date().toISOString()}};
}
async function submitFeedback(action, preset){
  const templateName=$('#templateName').value.trim(), overall=$('#overall').value.trim();
  const {layouts,allPass,missing,revisionWithoutFeedback}=decisions();
  if(missing){status('请先为每个 Layout 选择通过、舍弃或返修。','error');return}
  if(revisionWithoutFeedback&&!overall){status('选择返修的 Layout 需要填写单独或整体反馈。','error');return}
  if(allPass&&!templateName){status('全部 Layout 通过时必须填写模板名称。','error');return}
  const passed=layoutIds.filter(id=>layouts[id].decision==='pass').length;
  const revised=layoutIds.filter(id=>layouts[id].decision==='revise');
  const dropped=layoutIds.filter(id=>layouts[id].decision==='discard');
  // 唤醒语自带决定（整句覆盖）：粒度是整批，但要说清"哪些 Layout 怎么了"。
  const parts=[passed+' 通过'];
  if(revised.length)parts.push(revised.length+' 返修（'+revised.join('、')+'）');
  if(dropped.length)parts.push(dropped.length+' 舍弃（'+dropped.join('、')+'）');
  const wake={unit:'整批', text: allPass
    ? '模板审阅：'+layoutIds.length+' 个 Layout 全部通过（模板名「'+templateName+'」）—— 可以发布模板库了。'
    : '模板审阅：'+parts.join(' / ')+' —— 按反馈重建模板，其余不要动。'};
  const sent=await push({action:action==='approve_all'?'approve_all':'submit_batch', layouts, allPass,
                         templateName, overall, wake});
  if(!sent.ok)return;
  if(sent.duplicate){status(sent.notice,'ok');return}
  status('反馈已写入，并已通知模型（'+wakeNote(sent.verified)+'）。没有插件时模型不在这一侧，回对话说一声「已完成」。', sent.verified?'ok':'warn');
}
function approveAll(){
  for(const id of layoutIds){document.querySelector('[data-decision="'+id+'"] input[value="pass"]').checked=true;}
  submitFeedback('approve_all');
}
const BRIDGE_TIMEOUT_MS=2500;   // 握手要有上限：不落地就按"没有桥"降级继续
function connectWithTimeout(ms){
  return new Promise(resolve=>{
    let done=false;const finish=value=>{if(!done){done=true;resolve(value)}};
    setTimeout(()=>finish(null),ms);
    try{ ReviewBridge.connect().then(finish,()=>finish(null)); }catch(error){finish(null)}
  });
}
// 桥是**增强**，不是氧气：卡片与 canvas 是服务端渲染进 HTML 的，先把它画出来（浏览器解析时就有了），
// 再去握手；连不上就说"只读"，而不是留一个空壳。
(async function boot(){
  await hydrateAssets();                            // 没有桥时这里退化成同源相对地址
  try{ if(window.ReviewBridge)review=await connectWithTimeout(BRIDGE_TIMEOUT_MS); }catch(error){review=null}
  if(!review){
    $('#bridgeState').textContent=window.ReviewBridge?'连不上审阅宿主（握手未落地）· 只读':'没有加载到审阅桥 · 只读';
    status(window.ReviewBridge? '只读：内容可以看，决定存不进去（连不上审阅宿主）。'
                              : '只读：内容可以看，决定存不进去（请让宿主打开这一页）。','warn');
    return;
  }
  $('#bridgeState').textContent='已连接审阅宿主（'+review.transport+'）';
  await hydrateAssets();                            // 再水合一次：插件模式下资产要走桥（帧内 blob）
  review.on('changed',()=>refreshStale());
  refreshStale();
})();
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    project = root / "_internal" / "00_project"
    if (project/'template_pack').is_dir():
        print(generate_pack_review(root));return
    registry = load(project / "fidelity_template" / "template_registry.json")
    profile = load(project / "template_profile.json")
    assets = load(project / "template_asset_registry.json")
    reviews = load(project / "template_canvas_self_review.json")
    visual_manifest = load(project / "template_visuals" / "visual_manifest.json")
    if not profile or not assets or not registry.get("layouts"):
        raise SystemExit("template review requires profile, asset registry, and fidelity registry")
    version = template_version(root)
    review_id = uuid.uuid4().hex

    component_map = {x.get("component_id"): x for x in registry.get("components", []) if isinstance(x, dict)}
    page_images = {int(x["page"]): x.get("image", f"page_{int(x['page']):03d}.png")
                   for x in visual_manifest.get("pages", []) if isinstance(x, dict) and x.get("page")}
    cards = []
    layout_ids = list(registry["layouts"])
    for index, layout_id in enumerate(layout_ids, 1):
        layout = registry["layouts"][layout_id]
        canvas = project / "fidelity_template" / str(layout.get("canvas_file", ""))
        if not canvas.is_file():
            raise SystemExit(f"missing Builder canvas: {canvas}")
        ids = list(dict.fromkeys(layout.get("required_components", []) + layout.get("optional_components", [])))
        source_pages = {p for cid in ids for p in (
            component_map.get(cid, {}).get("source_pages") or [component_map.get(cid, {}).get("source_page")]
        ) if p}
        review = reviews.get("layouts", {}).get(layout_id, {})
        for ref in review.get("compared_source_pages", []):
            digits = "".join(ch for ch in str(ref) if ch.isdigit())
            if digits:
                source_pages.add(int(digits))
        # 源模板证据：**只列真的存在的那几张**（引用一个不存在的文件＝页面上一个坏图 +
        # 一次注定失败的取资产；库里来的模板本来就没有源模板页）。
        evidence = "".join(
            '<figure><img src="{rel}" data-asset="{rel}" alt="源模板 P{page}"><figcaption>源模板 P{page}</figcaption></figure>'.format(
                rel=esc(VISUALS_PREFIX + page_images.get(p, f"page_{p:03d}.png")), page=p)
            for p in sorted(source_pages)[:6]
            if (project / "template_visuals" / page_images.get(p, f"page_{p:03d}.png")).is_file()
        ) or '<p class="muted">无源页映射；请对照 contact sheet。</p>'
        usage = "默认开放内容页" if layout_id == "content_base" else (
            "仅在内容关系精确匹配时使用" if layout_id.startswith(("content_", "data_", "two_column_", "process_", "funnel_", "compare_"))
            else "核心功能页")
        cards.append(f'''<article class="card"><header><h2>{index}. {esc(layout_id)}</h2><span>{usage}</span></header>
<div class="compare"><section class="canvas">{inline_canvas(canvas)}</section><section><h3>源模板证据</h3><div class="thumbs">{evidence}</div>
<p><b>Required:</b> {esc(", ".join(layout.get("required_components", [])))}</p><p><b>Optional:</b> {esc(", ".join(layout.get("optional_components", [])))}</p></section></div>
<div class="decision"><fieldset data-decision="{esc(layout_id)}"><legend>此 Layout 如何处理？</legend>
<label class="choice pass"><input type="radio" name="decision-{index}" value="pass"><span>通过</span></label>
<label class="choice discard"><input type="radio" name="decision-{index}" value="discard"><span>舍弃</span></label>
<label class="choice revise"><input type="radio" name="decision-{index}" value="revise"><span>返修</span></label></fieldset>
<textarea data-feedback="{esc(layout_id)}" placeholder="此 Layout 的单独反馈；选择返修时请说明要改什么"></textarea></div></article>''')

    contact_sheet = project / "template_visuals" / "contact_sheet.png"
    contact = (f'<img style="max-width:100%" src="{esc(VISUALS_PREFIX + "contact_sheet.png")}" data-asset="{esc(VISUALS_PREFIX + "contact_sheet.png")}" alt="源模板 contact sheet">'
               if contact_sheet.is_file() else
               '<p class="muted">这一版模板没有源模板 contact sheet（库模板路径）；生产 canvas 就是对照物。</p>')
    page = (PAGE.replace('__CARDS__', ''.join(cards))
                .replace('__CONTACT__', contact)
                .replace('__LAYOUTS__', json.dumps(layout_ids, ensure_ascii=False))
                .replace('__REVIEW_ID__', review_id)
                .replace('__VERSION__', esc(str(version)[:12])))
    out = root / "00_template_review.html"
    out.write_text(page, encoding="utf-8")
    # 与页面审阅同一套「必须看过当前版本」握手：快照 + 一次性 review_id + HTML hash。
    # 快照写在 project/ 下的 JSON，不进入 template_version 覆盖的文件集合，
    # 所以写快照不会让刚生成的审阅页作废。
    write(project / TEMPLATE_REVIEW_SNAPSHOT,
          {"review_id": review_id, "template_version": version, "html_sha256": sha(out),
           "layouts": layout_ids})
    print(out)


if __name__ == "__main__":
    main()
