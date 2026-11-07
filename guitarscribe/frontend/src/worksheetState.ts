import {useEffect,useState} from 'react';
import {emptyWorksheet,encodeDocument,type WorksheetDocument} from './worksheetDocument';

type Note={job:string;api:string;text:string;saved:string;version:number;loaded:boolean;loading:boolean;saving:boolean;error:string;conflict:boolean;draftSchema:1|undefined;invalidDraft:boolean;rawBackup?:string;conflictVersion?:number;timer?:ReturnType<typeof setTimeout>;abort?:AbortController;listeners:Set<()=>void>};
class NoteMessage extends Error {}
const records=new Map<string,Note>();
const draftKey=(job:string)=>`guitarscribe.lyricWorksheetDraft.${job}`;
function getRecord(job:string,api:string){
  const key=`${api}:${job}`;
  if(!records.has(key)){
    let draft:{text?:unknown;baseVersion?:unknown;anchor_schema?:unknown}|null=null;
    let raw:string|null=null,invalidDraft=false;
    try{raw=sessionStorage.getItem(draftKey(job));draft=JSON.parse(raw??'null');if(raw&&(!draft||typeof draft.text!=='string'||!Number.isInteger(draft.baseVersion)||Number(draft.baseVersion)<0))throw Error();if(draft)encodeDocument(JSON.parse(String(draft.text)));}catch{invalidDraft=true;draft=null;}
    records.set(key,{job,api,text:typeof draft?.text==='string'?draft.text:encodeDocument(emptyWorksheet),saved:encodeDocument(emptyWorksheet),version:typeof draft?.baseVersion==='number'&&Number.isInteger(draft.baseVersion)&&draft.baseVersion>=0?draft.baseVersion:0,loaded:false,loading:false,saving:false,error:'',conflict:false,draftSchema:draft?(draft.anchor_schema===1?1:undefined):1,invalidDraft,rawBackup:invalidDraft?raw??undefined:undefined,listeners:new Set()});
  }
  return records.get(key)!;
}
const notify=(r:Note)=>r.listeners.forEach(fn=>fn());
function preserve(r:Note){
  if(r.invalidDraft)return;
  try{
    if(r.text===r.saved&&!r.conflict)sessionStorage.removeItem(draftKey(r.job));
    else sessionStorage.setItem(draftKey(r.job),JSON.stringify({anchor_schema:r.draftSchema,text:r.text,baseVersion:r.conflict?r.conflictVersion??r.version:r.version}));
  }catch{if(r.text!==r.saved)r.error='此分頁無法保留未存草稿，請按立即保存。';}
}
function schedule(r:Note){
  clearTimeout(r.timer);
  if(r.loaded&&!r.conflict&&!r.invalidDraft&&!r.error&&r.text!==r.saved)r.timer=setTimeout(()=>void save(r),700);
}
async function save(r:Note){
  clearTimeout(r.timer);
  if(!r.loaded||r.loading||r.saving||r.conflict||r.invalidDraft||r.text===r.saved)return;
  const text=r.text,version=r.version;r.saving=true;r.error='';notify(r);
  try{
    const response=await fetch(`${r.api}/api/v1/jobs/${encodeURIComponent(r.job)}/lyric-worksheet`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({document:JSON.parse(text),expected_version:version,anchor_schema:1})});
    if(response.status===409){r.conflict=true;r.conflictVersion=version;throw new NoteMessage('其他瀏覽器已更新；你的文字仍保留，請先複製再載入最新歌詞工作頁。');}
    if(!response.ok)throw new NoteMessage('保存失敗，文字仍保留，可按重試保存。');
    const data=await response.json();
    if(data.job_id!==r.job||encodeDocument(data.document)!==text||data.version!==version+1)throw new NoteMessage('保存回應不一致，文字仍保留。');
    r.version=data.version;r.saved=text;preserve(r);
  }catch(error){r.error=error instanceof NoteMessage?error.message:'保存失敗，文字仍保留，可按重試保存。';}
  finally{r.saving=false;notify(r);schedule(r);}
}
async function load(r:Note,discard=false){
  if(r.loading||r.saving)return;
  r.loading=true;r.error='';const abort=new AbortController();r.abort=abort;notify(r);
  try{
    const response=await fetch(`${r.api}/api/v1/jobs/${encodeURIComponent(r.job)}/lyric-worksheet`,{signal:abort.signal});
    if(!response.ok)throw new NoteMessage('歌詞工作頁暫時無法載入，可重試；未存文字仍保留。');
    const data=await response.json();if(abort.signal.aborted)return;
    if(data.job_id!==r.job||!Number.isInteger(data.version)||data.version<0)throw new NoteMessage('歌詞工作頁資料不完整，未覆寫文字。');
    let draft:{text:string;baseVersion:number;anchor_schema?:1}|null=null;
    const serverText=encodeDocument(data.document);
    if(!discard&&!r.invalidDraft){
      try{
        draft=JSON.parse(sessionStorage.getItem(draftKey(r.job))??'null');
        if(draft){if(typeof draft.text!=='string'||!Number.isInteger(draft.baseVersion)||draft.baseVersion<0)throw Error();draft.text=encodeDocument(JSON.parse(draft.text));}
      }catch{r.invalidDraft=true;try{r.rawBackup=sessionStorage.getItem(draftKey(r.job))??r.text;}catch{r.rawBackup=r.text;}}
    }
    if(!discard&&r.loaded&&r.text!==r.saved&&!r.invalidDraft)draft={text:r.text,baseVersion:r.version,anchor_schema:r.draftSchema};
    if(r.invalidDraft&&!discard){r.error='工作頁草稿格式無法讀取，請先下載備份，再確認載入最新版本。';return;}
    r.saved=serverText;r.version=data.version;r.loaded=true;r.conflict=false;r.draftSchema=1;r.invalidDraft=false;r.rawBackup=undefined;r.conflictVersion=undefined;
    const legacyAnchorRisk=!!draft&&draft.anchor_schema!==1&&data.document.lines.some((row:{anchor?:unknown})=>row.anchor!=null);
    if(draft&&(draft.text!==serverText||legacyAnchorRisk)){
      r.text=draft.text;r.draftSchema=legacyAnchorRisk?undefined:1;
      if(legacyAnchorRisk){r.conflict=true;r.conflictVersion=draft.baseVersion;r.error='舊版草稿未包含定位資訊，未覆寫已保存位置。請先下載草稿備份，再載入最新工作頁並合併文字。';}else
      if(draft.baseVersion!==data.version){r.conflict=true;r.conflictVersion=draft.baseVersion;r.error='其他瀏覽器已更新；你的未存文字仍保留，請先複製再載入最新歌詞工作頁。';}
    }else r.text=serverText;
    preserve(r);
  }catch(error){if(!abort.signal.aborted)r.error=error instanceof NoteMessage?error.message:'歌詞工作頁暫時無法載入，可重試；未存文字仍保留。';}
  finally{if(r.abort===abort){r.loading=false;notify(r);schedule(r);}}
}


/** Per-source queue stays outside chord Undo and outside existing melody notes. */
export function useWorksheet(job:string,api:string){
  const r=getRecord(job,api),[,render]=useState(0);
  useEffect(()=>{
    const refresh=()=>render(n=>n+1);r.listeners.add(refresh);
    if(r.loading&&r.abort?.signal.aborted)r.loading=false;
    if(!r.loaded||(!r.saving&&r.text===r.saved))void load(r);
    return()=>{r.listeners.delete(refresh);if(!r.listeners.size&&r.loading)r.abort?.abort();};
  },[r]);
  let document:WorksheetDocument=emptyWorksheet;
  try{document=JSON.parse(encodeDocument(JSON.parse(r.text)));}catch{/* Corrupt storage is retained separately for explicit recovery. */}
  const dirty=r.text!==r.saved;
  return {document,dirty,loaded:r.loaded,loading:r.loading,saving:r.saving,conflict:r.conflict,invalidDraft:r.invalidDraft,
    status:r.loading?'正在載入工作頁…':r.saving?'正在保存…':r.error||(!r.loaded?'尚未連線；草稿保留於此分頁。':dirty?'等待自動保存…':'已保存'),
    update(next:WorksheetDocument){
      if(r.invalidDraft){r.error='請先下載損壞草稿備份並載入最新版本，再編輯工作頁。';notify(r);return false;}
      try{r.text=encodeDocument(next);}catch{r.error='內容過長或格式不完整，這次修改未加入；既有文字仍保留。';notify(r);return false;}
      if(!r.conflict)r.error='';preserve(r);notify(r);schedule(r);return true;
    },
    save:()=>save(r),reload:()=>load(r,r.conflict||r.invalidDraft),rawDraft:r.rawBackup??r.text};
}
