import {useEffect,useRef,useState} from 'react';
import {parseRootDocument,type RootDocument,type RootSnapshot} from './rootPracticeDocument';

export function useRootPractice(api:string,job:string){
  const [document,setDocument]=useState<RootDocument|null>(null),[message,setMessage]=useState('正在載入練習…');
  const [blocked,setBlocked]=useState(false),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0),[reload,setReload]=useState(0);
  const state=useRef({version:0,document:null as RootDocument|null,saved:'',alive:true,busy:false,blocked:false});
  const undo=useRef<RootDocument[]>([]),redo=useRef<RootDocument[]>([]);
  const draftKey=`guitarscribe.root-practice.v1.${job}`;
  const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}/root-practice`;
  function retain(){const s=state.current;if(s.document)try{sessionStorage.setItem(draftKey,JSON.stringify({version:s.version,document:s.document}));}catch{setMessage('瀏覽器無法保留離線草稿，請下載備份。');}}
  function block(text:string){state.current.blocked=true;setBlocked(true);setMessage(text);}
  useEffect(()=>{
    const s=state.current;s.alive=true;s.blocked=false;setBlocked(false);setDocument(null);s.document=null;undo.current=[];redo.current=[];
    const controller=new AbortController();
    void (async()=>{try{
      const response=await fetch(endpoint,{signal:controller.signal});if(!response.ok)throw Error('練習暫時無法載入；請稍後重新載入。');
      const result=await response.json() as RootSnapshot;if(controller.signal.aborted||result.job_id!==job)return;
      const server=parseRootDocument(JSON.stringify(result.document));if(server.source.job_id!==job)throw Error('來源不符，已停止載入。');
      s.version=result.version;s.saved=JSON.stringify(server);s.document=server;
      let draft:string|null=null;
      try{draft=sessionStorage.getItem(draftKey);}catch{/* Server persistence still works without browser storage. */}
      if(draft){
        try{const local=JSON.parse(draft);const parsed=parseRootDocument(JSON.stringify(local.document),server.source);
          if(JSON.stringify(parsed)!==s.saved){s.document=parsed;if(local.version!==result.version)block('已保留本頁草稿，但另一分頁也有修改。請先下載草稿，再載入最新版本。');else setMessage('已恢復本頁未保存草稿，正在保存。');}
          else {sessionStorage.removeItem(draftKey);setMessage(result.version?'已保存':'尚未採用任何根音');}
        }catch{block('離線草稿格式或來源不符。請先下載原始草稿，再載入最新版本。');}
      }else setMessage(result.version?'已保存':'尚未採用任何根音');
      setDocument(s.document);setRevision(v=>v+1);
    }catch(error){if(!controller.signal.aborted){block(error instanceof Error?error.message:'載入失敗。');}}})();
    return()=>{s.alive=false;controller.abort();};
  },[endpoint,job,reload]);

  async function flush(){
    const s=state.current;if(!s.document||s.busy||s.blocked||JSON.stringify(s.document)===s.saved)return;
    s.busy=true;setBusy(true);setMessage('正在保存…');
    try{
      while(s.alive&&!s.blocked&&s.document&&JSON.stringify(s.document)!==s.saved){
        const sent=s.document;const encoded=JSON.stringify(sent);
        const response=await fetch(endpoint,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:s.version,document:sent})});
        if(!s.alive)return;
        if(!response.ok){block(response.status===409?'另一分頁已更新進度；本頁草稿保留，請先下載再載入最新版本。':'保存失敗；草稿保留在本分頁，可重試或下載備份。');return;}
        const saved=await response.json() as RootSnapshot;
        if(saved.job_id!==job||JSON.stringify(saved.document)!==encoded){
          // Server key ordering is immaterial; validate content structurally below.
          if(saved.job_id!==job||JSON.stringify(parseRootDocument(JSON.stringify(saved.document)).segments)!==JSON.stringify(sent.segments)||saved.document.source.fingerprint!==sent.source.fingerprint){block('保存回覆不符；請先下載草稿再重新載入。');return;}
        }
        s.version=saved.version;s.saved=encoded;
        if(JSON.stringify(s.document)===encoded){try{sessionStorage.removeItem(draftKey);}catch{/* Server copy is saved. */}}else retain();
      }
      if(s.alive)setMessage('已保存');
    }catch{if(s.alive)block('連線中斷；草稿保留在本分頁，可重試或下載備份。');}
    finally{s.busy=false;if(s.alive){setBusy(false);setRevision(v=>v+1);}}
  }
  useEffect(()=>{const timer=setTimeout(()=>void flush(),450);return()=>clearTimeout(timer);},[document,revision]);
  useEffect(()=>{const handler=(event:BeforeUnloadEvent)=>{const s=state.current;if(s.document&&JSON.stringify(s.document)!==s.saved){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',handler);return()=>window.removeEventListener('beforeunload',handler);},[]);
  function update(next:RootDocument,history=true){
    const s=state.current;if(!s.document||s.blocked)return false;
    try{parseRootDocument(JSON.stringify(next),s.document.source);}catch(e){setMessage(e instanceof Error?e.message:'資料無效');return false;}
    if(history){undo.current=[...undo.current.slice(-49),s.document];redo.current=[];}
    s.document=next;setDocument(next);retain();setMessage('尚未保存…');setRevision(v=>v+1);return true;
  }
  function travel(back:boolean){const from=back?undo:redo,to=back?redo:undo,s=state.current;if(!s.document||s.blocked||!from.current.length)return;const next=from.current.pop()!;to.current.push(s.document);update(next,false);}
  function retry(){state.current.blocked=false;setBlocked(false);setRevision(v=>v+1);if(!state.current.document)setReload(v=>v+1);}
  function loadLatest(){if(state.current.busy)return;try{sessionStorage.removeItem(draftKey);}catch{/* Loading server remains possible. */}setReload(v=>v+1);}
  function rawDraft(){try{return sessionStorage.getItem(draftKey)??JSON.stringify(state.current.document);}catch{return JSON.stringify(state.current.document);}}
  return {document,message,blocked,busy,update,undo:()=>travel(true),redo:()=>travel(false),canUndo:!!undo.current.length,canRedo:!!redo.current.length,retry,loadLatest,rawDraft};
}
