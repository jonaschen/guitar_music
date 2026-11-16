import {useEffect,useRef,useState} from 'react';
import type {RootDocument} from './rootPracticeDocument';
import {rootStamp} from './rootPracticeDocument';
export type PracticeSection={id:string;start:number;end:number;name:string};
export function RootStructureNav({api,job,document,active,onSelect}:{api:string;job:string;document:RootDocument;active:PracticeSection|null;onSelect:(s:PracticeSection|null)=>void}){
 const [sections,setSections]=useState<PracticeSection[]>([]),[message,setMessage]=useState('');
 const callback=useRef(onSelect);callback.current=onSelect;
 const url=new URL(window.location.href);url.searchParams.set('practice','structure');url.searchParams.set('job',job);
 for(const key of ['structure','structure_source','section_start','section_end','section_name'])url.searchParams.delete(key);
 useEffect(()=>{
  const controller=new AbortController();
  void(async()=>{try{
   const response=await fetch(`${api}/api/v1/jobs/${encodeURIComponent(job)}/song-structure`,{signal:controller.signal});
   if(!response.ok)throw Error();const result=await response.json();if(controller.signal.aborted)return;
   const doc=result.document;if(!doc){setMessage('尚無歌曲結構，可先建立段落。');return;}
   if(!result.source_matches||doc.source.fingerprint!==document.source.fingerprint||doc.source.source_start!==document.source.source_start||Math.abs(doc.source.duration-document.source.duration)>1e-7){setMessage('歌曲結構來源已變動，暫不套用範圍。');return;}
   let cursor=0;const ids=new Set<string>();const list:PracticeSection[]=doc.sections.map((s:any)=>{if(typeof s.id!=='string'||ids.has(s.id)||!Number.isFinite(s.start)||!Number.isFinite(s.end)||s.start!==cursor||s.end<=s.start||s.end>doc.source.duration||typeof s.display_label!=='string')throw Error();cursor=s.end;ids.add(s.id);return {id:s.id,start:s.start,end:s.end,name:s.display_label};});
   if(!list.length||Math.abs(cursor-doc.source.duration)>1e-7)throw Error();setSections(list);
   const params=new URLSearchParams(window.location.search),id=params.get('structure');if(!id)return;
   const selected=list.find(s=>s.id===id);
   if(params.get('structure_source')!==document.source.fingerprint||!selected||Number(params.get('section_start'))!==selected.start||Number(params.get('section_end'))!==selected.end){setMessage('連結的段落已改動，請從清單重新選取。');return;}
   callback.current(selected);
  }catch{if(!controller.signal.aborted)setMessage('歌曲結構暫時無法取得，仍可練習整首。');}})();
  return()=>controller.abort();
 },[api,job,document.source.fingerprint,document.source.duration,document.source.source_start]);
 const overlap=active?document.segments.filter(s=>s.start<active.end&&s.end>active.start):document.segments;
 const crossing=!!active&&overlap.some(s=>s.start<active.start||s.end>active.end);
 return <section aria-label="歌曲結構導覽" className="root-structure-nav"><div><label>歌曲大段 <select aria-label="歌曲大段" value={active?.id??''} onChange={e=>{const next=sections.find(s=>s.id===e.target.value)??null;callback.current(next);const link=new URL(window.location.href);for(const k of ['structure','structure_source','section_start','section_end','section_name'])link.searchParams.delete(k);window.history.replaceState(null,'',link);}}><option value="">整首歌曲</option>{sections.map((s,i)=><option value={s.id} key={s.id}>{i+1}. {s.name} {rootStamp(s.start)}–{rootStamp(s.end)}</option>)}</select></label><a href={url.pathname+url.search}>整理歌曲結構</a></div>{active?<p>目前 {active.name} · 顯示 {overlap.length}／{document.segments.length} 個根音區段。{crossing?'跨交界的小節會完整保留，採用範圍仍以右側標示為準。':'根音區段與進度保持原樣。'}</p>:null}{message?<p role="status">{message}</p>:null}</section>;
}
