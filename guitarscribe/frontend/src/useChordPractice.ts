import {useEffect,useRef,useState} from 'react';
import {parseStructure,type StructureDocument} from './songStructureDocument';
import {parseChordPractice,sameSource,restoreChordScope,type ChordPracticeDocument,type ChordLock} from './chordPracticeDocument';
const canonical=(v:unknown):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a.localeCompare(b))):x);
export function useChordPractice(api:string,job:string){
 const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}`,key=`guitarscribe.chords.draft.v1.${job}`;
 const [document,setDocument]=useState<ChordPracticeDocument|null>(null),[structure,setStructure]=useState<StructureDocument|null>(null),[lock,setLock]=useState<ChordLock|null>(null);
 const [message,setMessage]=useState('正在載入段落與和弦…'),[blocked,setBlocked]=useState(false),[busy,setBusy]=useState(false),[tick,setTick]=useState(0),[reload,setReload]=useState(0);
 const state=useRef({document:null as ChordPracticeDocument|null,structure:null as StructureDocument|null,structureVersion:0,lock:null as ChordLock|null,version:0,saved:'',blocked:false,busy:false,alive:true,hard:false});
 const undo=useRef<ChordPracticeDocument[]>([]),redo=useRef<ChordPracticeDocument[]>([]);
 function readDraft(){try{return sessionStorage.getItem(key);}catch{return null;}}
 function clearDraft(){try{sessionStorage.removeItem(key);}catch{/* Server snapshot is still authoritative. */}}
 const block=(text:string,hard=true)=>{state.current.blocked=true;state.current.hard=hard;setBlocked(true);setMessage(text);};
 function retain(){const s=state.current;try{sessionStorage.setItem(key,JSON.stringify({version:s.version,document:s.document,lock:s.lock}));}catch{setMessage('瀏覽器無法保留草稿，請下載和弦備份。');}}
 function selectLock(id:string){const s=state.current;if(s.blocked||s.busy||!s.structure||!s.document||canonical(s.document)!==s.saved)return false;const section=s.structure.sections.find(x=>x.id===id);if(!section)return false;
  const next={section_id:id,name:section.display_label,start:section.start,end:section.end,structure_version:s.structureVersion};s.lock=next;setLock(next);undo.current=[];redo.current=[];setTick(t=>t+1);return true;}
 function unlock(){const s=state.current;if(s.busy||s.blocked||canonical(s.document)!==s.saved)return false;s.lock=null;setLock(null);undo.current=[];redo.current=[];setTick(t=>t+1);return true;}
 useEffect(()=>{const s=state.current,controller=new AbortController();s.alive=true;s.blocked=false;s.hard=false;s.document=null;s.lock=null;setDocument(null);setStructure(null);setLock(null);setBlocked(false);setMessage('正在載入段落與和弦…');undo.current=[];redo.current=[];
  void(async()=>{try{
   const replies=await Promise.all([fetch(endpoint+'/chord-practice',{signal:controller.signal}),fetch(endpoint+'/song-structure',{signal:controller.signal})]);
   if(replies.some(r=>!r.ok))throw Error('段落或和弦稿暫時無法載入，請重試。');const [saved,sections]=await Promise.all(replies.map(r=>r.json()));if(controller.signal.aborted)return;
   if(saved.job_id===job&&saved.document){const retained=parseChordPractice(JSON.stringify(saved.document));if(retained.source.job_id===job){s.document=retained;setDocument(retained);}}
   if(saved.job_id!==job||sections.job_id!==job||!saved.source_matches||!sections.source_matches||!saved.current_source||!sections.current_source||!sameSource(saved.current_source,sections.current_source))throw Error('錄音來源已變動，請回到歌曲結構核對。');
   if(!sections.document)throw Error('請先在歌曲結構頁套用或保存結構，再選一段練和弦。');
   const doc=parseChordPractice(JSON.stringify(saved.document),saved.current_source),str=parseStructure(JSON.stringify(sections.document),saved.current_source);
   if(doc.source.job_id!==job||!Number.isInteger(saved.version)||saved.version<0||!Number.isInteger(sections.version)||sections.version<1)throw Error('載入的來源或版本不符。');
   s.document=doc;s.structure=str;s.version=saved.version;s.structureVersion=sections.version;s.saved=canonical(doc);setStructure(str);setMessage(saved.version?'已保存':'尚未採用和弦；原分析僅供參考。');
   const raw=readDraft();if(raw){try{
    const cached=JSON.parse(raw),draft=parseChordPractice(JSON.stringify(cached.document),doc.source);
    if(canonical(draft)!==s.saved){s.document=draft;s.lock=cached.lock;const section=str.sections.find(x=>x.id===cached.lock?.section_id);
     if(cached.version!==s.version||cached.lock?.structure_version!==s.structureVersion||!section||section.start!==cached.lock.start||section.end!==cached.lock.end)block('段落或版本已變動；已保留未保存草稿，請下載備份再重新載入。');else setMessage('已恢復未保存和弦，正在繼續保存…');
    }else clearDraft();
   }catch{block('本機和弦草稿無法核對，請先下載原始備份再重新載入。');}}
   setDocument(s.document);setLock(s.lock);
   if(!s.lock&&!s.blocked){const p=new URLSearchParams(location.search),id=p.get('structure');if(id){const section=str.sections.find(x=>x.id===id);
     if(!section||p.get('structure_source')!==doc.source.fingerprint||Number(p.get('section_start'))!==section.start||Number(p.get('section_end'))!==section.end)setMessage('連結的段落已改動，請從清單重新選取並鎖定。');else selectLock(id);
   }}setTick(t=>t+1);
  }catch(e){if(!controller.signal.aborted)block(e instanceof Error?e.message:'載入失敗，請重試。');}})();return()=>{s.alive=false;controller.abort();};
 },[endpoint,key,reload]);
 async function flush(){const s=state.current;if(!s.document||!s.lock||s.busy||s.blocked||canonical(s.document)===s.saved)return;s.busy=true;setBusy(true);setMessage('正在保存和弦…');
  try{while(s.alive&&!s.blocked&&s.document&&s.lock&&canonical(s.document)!==s.saved){const sent=s.document,encoded=canonical(sent);
   const response=await fetch(endpoint+'/chord-practice',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:s.version,structure_version:s.lock.structure_version,section_id:s.lock.section_id,document:sent})});if(!s.alive)return;
   if(!response.ok){block(response.status===409?'段落、來源或版本已變動；草稿保留，請下載備份再重新載入。':'保存失敗，和弦草稿已保留；可重試或下載備份。',response.status===409);return;}
   const result=await response.json();if(!s.alive)return;if(result.job_id!==job||result.version!==s.version+1||canonical(parseChordPractice(JSON.stringify(result.document),sent.source))!==encoded){block('保存回覆不符，請下載草稿再重新載入。');return;}
   s.version=result.version;s.saved=encoded;if(canonical(s.document)===s.saved)clearDraft();else retain();
  }if(s.alive&&!s.blocked)setMessage('已保存');
  }catch{if(s.alive)block('連線中斷，和弦草稿已保留；可重試或下載備份。',false);}finally{s.busy=false;if(s.alive){setBusy(false);setTick(t=>t+1);}}
 }
 useEffect(()=>{const timer=setTimeout(()=>void flush(),450);return()=>clearTimeout(timer);},[document,tick]);
 useEffect(()=>{const leave=(e:BeforeUnloadEvent)=>{const s=state.current;if(s.document&&canonical(s.document)!==s.saved){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[]);
 useEffect(()=>{if(!lock)return;const controller=new AbortController();let running=false;
  async function check(){const s=state.current;if(running||s.blocked||window.document.hidden)return;running=true;try{const r=await fetch(endpoint+'/song-structure',{signal:controller.signal});if(!r.ok)return;const snapshot=await r.json();if(!controller.signal.aborted&&(!snapshot.source_matches||snapshot.version!==s.lock?.structure_version||!snapshot.current_source||!s.document||!sameSource(snapshot.current_source,s.document.source)))block('歌曲結構或來源已變動，請保存草稿備份後重新載入並選段。');}catch{/* PUT also checks the current source and structure. */}finally{running=false;}}
  const timer=setInterval(()=>void check(),15000);window.addEventListener('focus',check);return()=>{clearInterval(timer);window.removeEventListener('focus',check);controller.abort();};
 },[lock?.section_id,lock?.structure_version,endpoint]);
 function update(next:ChordPracticeDocument,record=true){const s=state.current;if(s.blocked||!s.document||!s.lock)return false;try{const parsed=parseChordPractice(JSON.stringify(next),s.document.source);if(record){undo.current.push(s.document);undo.current=undo.current.slice(-50);redo.current=[];}s.document=parsed;setDocument(parsed);retain();setMessage('等待保存…');setTick(t=>t+1);return true;}catch(e){setMessage(String(e));return false;}}
 function travel(back:boolean){const from=back?undo:redo,to=back?redo:undo,s=state.current;if(s.blocked||!s.document||!from.current.length)return;if(!s.lock)return;const past=from.current[from.current.length-1];try{const next=restoreChordScope(s.document,past,s.lock);to.current.push(s.document);from.current.pop();update(next,false);}catch(e){setMessage(String(e));}}
 return {document,structure,lock,message,blocked,busy,synced:!!document&&canonical(document)===state.current.saved,selectLock,unlock,update,undo:()=>travel(true),redo:()=>travel(false),canUndo:!!undo.current.length,canRedo:!!redo.current.length,
  retry:()=>{if(state.current.hard||!state.current.document){setReload(r=>r+1);return;}state.current.blocked=false;setBlocked(false);setTick(t=>t+1);},
  loadLatest:()=>{if(state.current.busy)return;clearDraft();setReload(r=>r+1);},rawDraft:()=>readDraft()??JSON.stringify(state.current.document)};
}
