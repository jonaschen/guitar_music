import {useEffect,useRef,useState} from 'react';
import {parseStructure,type StructureDocument,type StructureSource,type StructureSnapshot} from './songStructureDocument';
const canonical=(v:any):string=>JSON.stringify(v,(_,value)=>value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b))):value);
export function useSongStructure(api:string,job:string){
 const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}/song-structure`,key=`guitarscribe.structure.draft.v1.${job}`;
 const [document,setDocument]=useState<StructureDocument|null>(null),[source,setSource]=useState<StructureSource|null>(null),[message,setMessage]=useState('正在載入歌曲結構…'),[blocked,setBlocked]=useState(false),[busy,setBusy]=useState(false),[tick,setTick]=useState(0),[reload,setReload]=useState(0);
 const state=useRef({document:null as StructureDocument|null,source:null as StructureSource|null,version:0,saved:'null',alive:true,blocked:false,busy:false,sourceBlocked:false,loaded:false,retryLoad:false});
 const undo=useRef<StructureDocument[]>([]),redo=useRef<StructureDocument[]>([]);
 const block=(text:string,retryLoad=true)=>{state.current.retryLoad=retryLoad;state.current.blocked=true;setBlocked(true);setMessage(text);};
 function retain(){const s=state.current;if(s.document)try{sessionStorage.setItem(key,JSON.stringify({version:s.version,document:s.document}));}catch{setMessage('瀏覽器無法保留草稿，請下載結構備份。');}}
 useEffect(()=>{
  const s=state.current;s.alive=true;s.loaded=false;s.blocked=false;s.sourceBlocked=false;s.document=null;setDocument(null);setBlocked(false);undo.current=[];redo.current=[];
  const controller=new AbortController();
  void(async()=>{try{
   const response=await fetch(endpoint,{signal:controller.signal});if(!response.ok)throw Error('歌曲結構暫時無法載入，請重試。');
   const result:StructureSnapshot=await response.json();if(controller.signal.aborted)return;
   if(result.job_id!==job)throw Error('載入的歌曲不符。');
   const doc=result.document?parseStructure(JSON.stringify(result.document)):null;
   s.loaded=true;s.source=result.current_source;s.document=doc;s.version=result.version;s.saved=canonical(doc);setSource(result.current_source);
   let draft:string|null=null;try{draft=sessionStorage.getItem(key);}catch{/* Server remains available. */}
   if(draft){try{
    const cached=JSON.parse(draft),parsed=parseStructure(JSON.stringify(cached.document),doc?.source??result.current_source??undefined);
    if(parsed.source.job_id!==job)throw Error();
    if(canonical(parsed)!==s.saved){s.document=parsed;if(cached.version!==s.version)block('另一分頁已更新；本頁草稿保留，請先下載再載入最新版本。');else setMessage('已恢復尚未保存的結構草稿。');}
    else{sessionStorage.removeItem(key);setMessage('已保存');}
   }catch{block('本機草稿來源或格式不符；請先下載原始草稿，再載入最新版本。');}}
   else setMessage(doc?'已保存':'這首歌還沒有歌曲結構，可建立手動初稿。');
   if(!result.source_matches){s.sourceBlocked=true;block(result.source_error||'錄音來源已變動，已停止編輯；仍可下載原稿。');}
   setDocument(s.document);setTick(t=>t+1);
  }catch(error){if(!controller.signal.aborted){block('歌曲結構載入失敗，草稿保留；請重試載入。');try{const raw=sessionStorage.getItem(key);if(raw){const cached=JSON.parse(raw);s.document=parseStructure(JSON.stringify(cached.document));setDocument(s.document);}}catch{/* Raw draft remains downloadable. */}}}})();
  return()=>{s.alive=false;controller.abort();};
 },[endpoint,key,job,reload]);
 async function flush(){
  const s=state.current;if(!s.document||s.busy||s.blocked||canonical(s.document)===s.saved)return;
  s.busy=true;setBusy(true);setMessage('正在保存結構…');
  try{while(s.alive&&!s.blocked&&s.document&&canonical(s.document)!==s.saved){
   const sent=s.document,encoded=canonical(sent);
   const response=await fetch(endpoint,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:s.version,document:sent})});
   if(!s.alive)return;
   if(!response.ok){block(response.status===409?'版本或來源已變動；本頁草稿保留，請先下載再載入最新版本。':'保存失敗；草稿保留，可重試或下載備份。',response.status===409);return;}
   const result:StructureSnapshot=await response.json();
   if(result.job_id!==job||!result.document||canonical(parseStructure(JSON.stringify(result.document),sent.source))!==encoded||result.version!==s.version+1){block('保存回覆不符，草稿已保留，請下載後重新載入。');return;}
   s.version=result.version;s.saved=encoded;
   if(canonical(s.document)===encoded){try{sessionStorage.removeItem(key);}catch{/* Saved on server. */}}else retain();
  }if(s.alive)setMessage('已保存');
  }catch{if(s.alive)block('連線中斷，草稿已保留；可重試或下載備份。',false);}
  finally{s.busy=false;if(s.alive){setBusy(false);setTick(t=>t+1);}}
 }
 useEffect(()=>{const timer=setTimeout(()=>void flush(),450);return()=>clearTimeout(timer);},[document,tick]);
 useEffect(()=>{const handler=(e:BeforeUnloadEvent)=>{if(state.current.document&&canonical(state.current.document)!==state.current.saved){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[]);
 function update(next:StructureDocument,record=true){const s=state.current;if(s.blocked||!s.source)return false;try{const parsed=parseStructure(JSON.stringify(next),s.source);if(record&&s.document){undo.current=[...undo.current.slice(-49),s.document];redo.current=[];}s.document=parsed;setDocument(parsed);retain();setMessage('尚未保存…');setTick(t=>t+1);return true;}catch(error){setMessage(String(error));return false;}}
 function travel(back:boolean){const s=state.current,from=back?undo:redo,to=back?redo:undo;if(s.blocked||!s.document||!from.current.length)return;to.current.push(s.document);update(from.current.pop()!,false);}
 return {document,source,message,blocked,busy,audioAllowed:!!source&&state.current.loaded&&!state.current.sourceBlocked,update,canUndo:!!undo.current.length,canRedo:!!redo.current.length,undo:()=>travel(true),redo:()=>travel(false),
  retry:()=>{if(state.current.retryLoad||!state.current.loaded||!state.current.document||state.current.sourceBlocked){setReload(r=>r+1);return;}state.current.blocked=false;setBlocked(false);setTick(t=>t+1);},
  loadLatest:()=>{if(state.current.busy)return;try{sessionStorage.removeItem(key);}catch{/* Optional cache. */}setReload(r=>r+1);},
  rawDraft:()=>{try{return sessionStorage.getItem(key)??JSON.stringify(state.current.document);}catch{return JSON.stringify(state.current.document);}},endpoint};
}
