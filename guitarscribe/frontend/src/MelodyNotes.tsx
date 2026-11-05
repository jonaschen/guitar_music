import {useEffect,useState} from 'react';

type Note={job:string;api:string;text:string;saved:string;version:number;loaded:boolean;loading:boolean;saving:boolean;error:string;conflict:boolean;conflictVersion?:number;timer?:ReturnType<typeof setTimeout>;abort?:AbortController;listeners:Set<()=>void>};
class NoteMessage extends Error {}
const records=new Map<string,Note>();
const draftKey=(job:string)=>`guitarscribe.melodyNoteDraft.${job}`;
function getRecord(job:string,api:string){
  const key=`${api}:${job}`;
  if(!records.has(key)){
    let draft:{text?:unknown;baseVersion?:unknown}|null=null;
    try{draft=JSON.parse(sessionStorage.getItem(draftKey(job))??'null');}catch{/* Server remains authoritative. */}
    records.set(key,{job,api,text:typeof draft?.text==='string'?draft.text:'',saved:'',version:typeof draft?.baseVersion==='number'&&Number.isInteger(draft.baseVersion)&&draft.baseVersion>=0?draft.baseVersion:0,loaded:false,loading:false,saving:false,error:'',conflict:false,listeners:new Set()});
  }
  return records.get(key)!;
}
const notify=(r:Note)=>r.listeners.forEach(fn=>fn());
function preserve(r:Note){
  try{
    if(r.text===r.saved&&!r.conflict)sessionStorage.removeItem(draftKey(r.job));
    else sessionStorage.setItem(draftKey(r.job),JSON.stringify({text:r.text,baseVersion:r.conflict?r.conflictVersion??r.version:r.version}));
  }catch{if(r.text!==r.saved)r.error='此分頁無法保留未存草稿，請按立即保存。';}
}
function schedule(r:Note){
  clearTimeout(r.timer);
  if(r.loaded&&!r.conflict&&!r.error&&r.text!==r.saved)r.timer=setTimeout(()=>void save(r),700);
}
async function save(r:Note){
  clearTimeout(r.timer);
  if(!r.loaded||r.loading||r.saving||r.conflict||r.text===r.saved)return;
  const text=r.text,version=r.version;r.saving=true;r.error='';notify(r);
  try{
    const response=await fetch(`${r.api}/api/v1/jobs/${encodeURIComponent(r.job)}/melody-notes`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,expected_version:version})});
    if(response.status===409){r.conflict=true;r.conflictVersion=version;throw new NoteMessage('其他瀏覽器已更新；你的文字仍保留，請先複製再載入最新筆記。');}
    if(!response.ok)throw new NoteMessage('保存失敗，文字仍保留，可按重試保存。');
    const data=await response.json();
    if(data.job_id!==r.job||data.text!==text||data.version!==version+1)throw new NoteMessage('保存回應不一致，文字仍保留。');
    r.version=data.version;r.saved=text;preserve(r);
  }catch(error){r.error=error instanceof NoteMessage?error.message:'保存失敗，文字仍保留，可按重試保存。';}
  finally{r.saving=false;notify(r);schedule(r);}
}
async function load(r:Note,discard=false){
  if(r.loading||r.saving)return;
  r.loading=true;r.error='';const abort=new AbortController();r.abort=abort;notify(r);
  try{
    const response=await fetch(`${r.api}/api/v1/jobs/${encodeURIComponent(r.job)}/melody-notes`,{signal:abort.signal});
    if(!response.ok)throw new NoteMessage('筆記暫時無法載入，可重試；未存文字仍保留。');
    const data=await response.json();if(abort.signal.aborted)return;
    if(data.job_id!==r.job||typeof data.text!=='string'||!Number.isInteger(data.version)||data.version<0)throw new NoteMessage('筆記資料不完整，未覆寫文字。');
    let draft:{text:string;baseVersion:number}|null=null;
    if(!discard){try{draft=JSON.parse(sessionStorage.getItem(draftKey(r.job))??'null');}catch{/* Keep the current in-memory draft. */}}
    const memoryDirty=r.loaded&&r.text!==r.saved;
    if(!discard&&memoryDirty)draft={text:r.text,baseVersion:r.version};
    r.saved=data.text;r.version=data.version;r.loaded=true;r.conflict=false;r.conflictVersion=undefined;
    if(draft&&typeof draft.text==='string'&&draft.text!==data.text){
      r.text=draft.text;
      if(draft.baseVersion!==data.version){r.conflict=true;r.conflictVersion=draft.baseVersion;r.error='其他瀏覽器已更新；你的未存文字仍保留，請先複製再載入最新筆記。';}
    }else r.text=data.text;
    preserve(r);
  }catch(error){if(!abort.signal.aborted)r.error=error instanceof NoteMessage?error.message:'筆記暫時無法載入，可重試；未存文字仍保留。';}
  finally{if(r.abort===abort){r.loading=false;notify(r);schedule(r);}}
}

/** Per-source queue survives view changes; server notes never enter chord Undo. */
export function MelodyNotes({job,api}:{job:string;api:string}){
  const r=getRecord(job,api),[,render]=useState(0);
  useEffect(()=>{
    const refresh=()=>render(n=>n+1);r.listeners.add(refresh);
    if(r.loading&&r.abort?.signal.aborted)r.loading=false;
    if(!r.loaded||(!r.saving&&r.text===r.saved))void load(r);
    return()=>{r.listeners.delete(refresh);if(!r.listeners.size&&r.loading)r.abort?.abort();};
  },[r]);
  const dirty=r.text!==r.saved;
  const status=r.loading?'正在載入筆記…':r.saving?'正在保存…':r.error||(!r.loaded?'尚未連上伺服器，文字保留於此分頁，請重試載入。':dirty?'等待自動保存…':'已保存');
  return <details className="melody-text-notes"><summary>我的旋律筆記</summary>
    <p>記下自己抓的調性、音名或片段；文字不會自動移調或播放。此邀請空間共用。</p>
    <label>旋律筆記<textarea aria-label="旋律筆記" rows={5} maxLength={16000} disabled={r.loading} value={r.text} onChange={e=>{r.text=e.target.value;if(!r.conflict)r.error='';preserve(r);notify(r);schedule(r);}}/></label>
    <p role="status" aria-label="筆記保存狀態">{status}</p>
    <button type="button" disabled={!dirty||r.saving||r.loading||!r.loaded||r.conflict} onClick={()=>void save(r)}>{r.error?'重試保存':'立即保存'}</button>
    {(r.conflict||!r.loaded)&&!r.loading?<button type="button" onClick={()=>{if(!r.conflict||window.confirm('載入伺服器版本會取代目前未存文字，請先複製要保留的內容。'))void load(r,r.conflict);}}>載入最新筆記</button>:null}
  </details>;
}
