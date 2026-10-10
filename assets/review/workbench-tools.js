/* Literal SVG-text search. Text and tspan identities survive replacement. */
let findMatches=[],findIndex=-1,replaceBusy=false,lastReplaceBatch=null,replaceConfirmation=null;
let restoredDraftMeta=null;
const thumbnailCache=new Map(),thumbnailAssets=new Map();

async function refreshThumbnail(p){
  if(!review||typeof review.read!=='function')return;
  const key=p.revision+'\u0000'+editSignature(state[p.key].svg_edits);
  let pending=thumbnailCache.get(key);
  if(!pending){
    pending=(async()=>{
      const doc=effectiveSvg(p),svg=doc.documentElement;
      for(const image of svg.querySelectorAll('image[data-project-rel]')){
        const rel=image.getAttribute('data-project-rel'),version=image.getAttribute('data-project-ver')||'';
        const assetKey=rel+'\u0000'+version;
        if(!thumbnailAssets.has(assetKey))thumbnailAssets.set(assetKey,(async()=>{
          const result=await review.read(rel);
          const mime=/\.jpe?g$/i.test(rel)?'image/jpeg':/\.webp$/i.test(rel)?'image/webp':/\.svg$/i.test(rel)?'image/svg+xml':'image/png';
          return await new Promise((resolve,reject)=>{
            const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;
            reader.readAsDataURL(new Blob([new Uint8Array(result.bytes)],{type:mime}));
          });
        })());
        const href=await thumbnailAssets.get(assetKey);
        image.setAttribute('href',href);image.removeAttributeNS('http://www.w3.org/1999/xlink','href');
      }
      const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}));
      try{
        const image=new Image();image.src=url;await image.decode();
        const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;
        canvas.getContext('2d').drawImage(image,0,0,320,180);return canvas.toDataURL('image/png');
      }finally{URL.revokeObjectURL(url)}
    })();
    thumbnailCache.set(key,pending);
    if(thumbnailCache.size>80)thumbnailCache.delete(thumbnailCache.keys().next().value);
  }
  try{
    const url=await pending;
    if(key!==p.revision+'\u0000'+editSignature(state[p.key].svg_edits))return;
    const thumbnail=railButtons.get(p.key)?.b.querySelector('img');if(thumbnail)thumbnail.src=url;
  }catch(error){thumbnailCache.delete(key)}
}

function svgTextNodes(root){
  const nodes=[];let text='';
  const walk=element=>{
    for(const child of element.childNodes){
      if(child.nodeType===3){
        const previous=child.previousSibling;
        const owner=previous?.nodeType===1?previous:element;
        const element_id=owner.getAttribute('data-workbench-id');
        if(!element_id)continue;
        const value=child.nodeValue||'';
        nodes.push({element_id,slot:previous?.nodeType===1?'tail':'text',value,start:text.length});
        text+=value;
      }else if(child.nodeType===1&&child.localName==='tspan'){
        if(text&&['x','y','dy'].some(attr=>child.hasAttribute(attr)))text+='\n';
        walk(child);
      }
    }
  };
  walk(root);return {nodes,text};
}
function applyTextNodes(root,nodes){
  const lookup=new Map([root,...root.querySelectorAll('[data-workbench-id]')].map(el=>[el.getAttribute('data-workbench-id'),el]));
  for(const run of nodes){
    const owner=lookup.get(run.element_id);if(!owner)continue;
    if(run.slot==='text'){
      if(owner.firstChild?.nodeType===3)owner.firstChild.nodeValue=run.value;
      else owner.insertBefore(owner.ownerDocument.createTextNode(run.value),owner.firstChild);
    }else{
      if(owner.nextSibling?.nodeType===3)owner.nextSibling.nodeValue=run.value;
      else owner.parentNode.insertBefore(owner.ownerDocument.createTextNode(run.value),owner.nextSibling);
    }
  }
}
function effectiveSvg(p){
  const doc=new DOMParser().parseFromString(p.svgMarkup||'','image/svg+xml');
  for(const edit of state[p.key].svg_edits){
    const el=[...doc.querySelectorAll('[data-workbench-id]')].find(el=>el.getAttribute('data-workbench-id')===edit.review_id);
    if(!el)continue;
    if(edit.deleted){el.remove();continue}
    if(edit.text_nodes)applyTextNodes(el,edit.text_nodes);
    else if(edit.text!==undefined)applyTextToDom(el,edit.text,edit.lines);
  }
  return doc;
}
function toggleFind(force){
  const open=typeof force==='boolean'?force:$('#findPanel').hidden;
  $('#findPanel').hidden=!open;$('#findToggle').setAttribute('aria-expanded',String(open));
  if(open){updateFindMatches();$('#findQuery').focus()}else clearFindHighlights();
  sizePreview();
}
function clearFindHighlights(){currentSvgRoot()?.querySelectorAll('.find-match').forEach(el=>el.classList.remove('find-match'))}
function paintFindHighlights(){
  clearFindHighlights();
  for(const match of findMatches.filter(m=>m.key===page().key))findSvgEl(match.element_id)?.classList.add('find-match');
}
function updateFindMatches(){
  const current=findMatches[findIndex],query=$('#findQuery').value;
  findMatches=[];
  if(query){
    const targets=$('#findScope').value==='deck'?orderedPages():[page()];
    for(const p of targets){
      for(const el of effectiveSvg(p).querySelectorAll('text[data-workbench-id]')){
        if(el.closest('defs,clipPath,mask,pattern,symbol'))continue;
        const {text}=svgTextNodes(el);let offset=0;
        while((offset=text.indexOf(query,offset))>=0){
          findMatches.push({key:p.key,element_id:el.getAttribute('data-workbench-id'),start:offset,length:query.length});
          offset+=query.length;
        }
      }
    }
  }
  findIndex=current?findMatches.findIndex(m=>m.key===current.key&&m.element_id===current.element_id&&m.start===current.start):-1;
  if(findIndex<0&&findMatches.length)findIndex=0;
  $('#findCount').textContent=findMatches.length?`${findIndex+1} / ${findMatches.length} 处`:'0 处匹配';
  for(const id of ['findPrev','findNext','replaceOne','replaceAll'])$('#'+id).disabled=!findMatches.length||replaceBusy;
  $('#undoReplace').disabled=!lastReplaceBatch||replaceBusy;
  paintFindHighlights();return findMatches;
}
async function goFindMatch(delta){
  updateFindMatches();if(!findMatches.length)return;
  const target=findMatches[(findIndex+delta+findMatches.length)%findMatches.length];
  if(page().key!==target.key)await selectPage(pageOrder.indexOf(target.key));
  updateFindMatches();findIndex=findMatches.findIndex(m=>m.key===target.key&&m.element_id===target.element_id&&m.start===target.start);
  if(previous)await togglePrevious();
  selectedReviewId=target.element_id;updateToolbarSelection();paintFindHighlights();
  $('#findCount').textContent=`${findIndex+1} / ${findMatches.length} 处`;
}
function confirmReplaceAll(){
  updateFindMatches();if(!findMatches.length)return;
  replaceConfirmation={query:$('#findQuery').value,value:$('#replaceValue').value,scope:$('#findScope').value,
    matches:JSON.stringify(findMatches),revisions:Object.fromEntries(orderedPages().map(p=>[p.key,p.revision]))};
  $('#replaceSummary').textContent=`将在 ${new Set(findMatches.map(m=>m.key)).size} 页替换 ${findMatches.length} 处“${replaceConfirmation.query}”。`;
  $('#replaceDialog').showModal();
}
function replaceTextRuns(el,matches,value){
  const extracted=svgTextNodes(el),nodes=structuredClone(extracted.nodes);
  for(const match of [...matches].sort((a,b)=>b.start-a.start)){
    const end=match.start+match.length;
    const hits=nodes.filter(run=>run.start<end&&run.start+run.value.length>match.start);
    if(!hits.length)continue;
    hits.forEach((run,i)=>{
      const from=Math.max(0,match.start-run.start),to=Math.min(run.value.length,end-run.start);
      run.value=run.value.slice(0,from)+(i===0?value:'')+run.value.slice(to);
    });
  }
  return nodes.map(({element_id,slot,value})=>({element_id,slot,value}));
}
async function replaceMatches(all=false){
  if(replaceBusy)return false;
  endInlineTextEdit(true);updateFindMatches();
  if(!findMatches.length)return false;
  if(all&&(!replaceConfirmation||replaceConfirmation.query!==$('#findQuery').value||replaceConfirmation.value!==$('#replaceValue').value||
     replaceConfirmation.scope!==$('#findScope').value||replaceConfirmation.matches!==JSON.stringify(findMatches)||
     orderedPages().some(p=>replaceConfirmation.revisions[p.key]!==p.revision))){
    $('#replaceDialog').close();note('页面或查找条件已变化，请重新确认替换','warn');return false;
  }
  const selected=all?[...findMatches]:[findMatches[Math.max(0,findIndex)]];
  const value=$('#replaceValue').value,targets=orderedPages().filter(p=>selected.some(m=>m.key===p.key));
  replaceBusy=true;$('#replaceDialog').close();updateFindMatches();
  try{
    if(!await flushWorkbench(targets))return false;
    const batch={id:uid(),pages:{},count:selected.length};
    for(const p of targets){
      const before=structuredClone(state[p.key].svg_edits),doc=effectiveSvg(p),undoNodes=[];
      const groups=new Map();
      for(const match of selected.filter(m=>m.key===p.key)){
        if(!groups.has(match.element_id))groups.set(match.element_id,[]);
        groups.get(match.element_id).push(match);
      }
      for(const [id,matches] of groups){
        const el=[...doc.querySelectorAll('text[data-workbench-id]')].find(el=>el.getAttribute('data-workbench-id')===id);
        if(!el)throw new Error('匹配文字已变化，请刷新后重试');
        undoNodes.push({review_id:id,nodes:svgTextNodes(el).nodes.map(({element_id,slot,value})=>({element_id,slot,value}))});
        let rec=state[p.key].svg_edits.find(r=>r.review_id===id);
        if(!rec){rec={review_id:id,tag:'text',orig_text:extractTextState(el).text,dx:0,dy:0};state[p.key].svg_edits.push(rec)}
        rec.text_nodes=replaceTextRuns(el,matches,value);delete rec.text;delete rec.lines;
      }
      batch.pages[p.key]={before,after:structuredClone(state[p.key].svg_edits),undo_nodes:undoNodes,revision:p.revision};
    }
    lastReplaceBatch=batch;retainRecoveryDraft();
    if(targets.includes(page()))mountInlineSvg(page());
    const failed=[];
    for(const p of targets){
      if(!await savePage(p))failed.push(p.key);
      batch.pages[p.key].revision=p.revision;
    }
    await saveDraft();updateRail();updateFindMatches();
    if(failed.length){note(`替换未全部保存：${failed.map(key=>pageOrder.indexOf(key)+1).join('、')} 页；输入已保留`,'error');return false}
    note(`已替换 ${selected.length} 处`,'ok');return true;
  }catch(error){retainRecoveryDraft();note('替换未完成：'+error.message+'；输入已保留','error');return false}
  finally{replaceBusy=false;updateFindMatches();drawSaveStatus()}
}
async function undoReplaceBatch(){
  if(replaceBusy||!lastReplaceBatch)return false;
  endInlineTextEdit(true);
  const batch=lastReplaceBatch;
  for(const [key,item] of Object.entries(batch.pages)){
    const p=data.pages.find(p=>p.key===key);
    if(p.revision!==item.revision||pageDirty(p)||
       (state[key].svg_edits.length&&editSignature(state[key].svg_edits)!==editSignature(item.after))){
      note('替换后页面已有其他修改，不能直接撤销整批；可在版本中恢复','warn');return false;
    }
  }
  replaceBusy=true;
  try{
    const failed=[];
    for(const [key,item] of Object.entries(batch.pages)){
      const p=data.pages.find(p=>p.key===key);
      if(item.undo_nodes){
        for(const inverse of item.undo_nodes){
          let rec=state[key].svg_edits.find(r=>r.review_id===inverse.review_id);
          if(!rec){rec={review_id:inverse.review_id,tag:'text',dx:0,dy:0};state[key].svg_edits.push(rec)}
          rec.text_nodes=structuredClone(inverse.nodes);delete rec.text;delete rec.lines;
        }
      }else state[key].svg_edits=structuredClone(item.before);
      if(!await savePage(p))failed.push(key);
    }
    if(Object.hasOwn(batch.pages,page().key))mountInlineSvg(page());
    // Retry goes through ordinary autosave, not another rollback of the same batch.
    lastReplaceBatch=null;await saveDraft();updateRail();updateFindMatches();
    if(failed.length){note('撤销尚未全部保存，输入已保留，请重试保存','error');return false}
    note('已撤销上次替换','ok');return true;
  }finally{replaceBusy=false;updateFindMatches()}
}
$('#findQuery').oninput=()=>{findIndex=-1;updateFindMatches()};
$('#findScope').onchange=()=>{findIndex=-1;updateFindMatches()};
$('#findQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();void goFindMatch(e.shiftKey?-1:1)}};
window.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='f'){e.preventDefault();toggleFind(true)}
  if(e.key==='Escape'){
    if(!$('#regionDialog').hidden){cancelRegion();return}
    if(!$('#findPanel').hidden)toggleFind(false);
  }
});
