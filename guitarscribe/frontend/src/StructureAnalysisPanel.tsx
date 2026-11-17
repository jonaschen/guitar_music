import {useEffect,useRef,useState} from 'react';
import {parseStructure,type StructureDocument,type StructureSource} from './songStructureDocument';
import {rootStamp} from './rootPracticeDocument';
type AnalysisStatus={state:string;message:string;candidate:StructureDocument|null;run_id:string|null;elapsed_seconds:number};
export function StructureAnalysisPanel({endpoint,job,source,disabled,hasDocument,onApply}:{endpoint:string;job:string;source:StructureSource|null;disabled:boolean;hasDocument:boolean;onApply:(d:StructureDocument)=>boolean}){
 const [status,setStatus]=useState<AnalysisStatus|null>(null),[pending,setPending]=useState(false),[applied,setApplied]=useState<string|null>(null),[audioError,setAudioError]=useState('');
 const sequence=useRef(0),alive=useRef(true),audio=useRef<HTMLAudioElement|null>(null),stopAt=useRef<number|null>(null);
 const working=!!status&&['running','cancelling'].includes(status.state),candidate=status?.candidate??null;
 async function request(method='GET',force=false){
  if(!source)return;const serial=++sequence.current;setPending(true);
  try{
   const response=await fetch(endpoint+'/analysis',{method,...(method==='POST'?{headers:{'Content-Type':'application/json'},body:JSON.stringify({fingerprint:source.fingerprint,audio_sha256:source.audio_sha256,force})}:{})});
   if(!response.ok)throw Error(response.status===409?'錄音來源或工作狀態已變動，請重新載入結構頁。':'分析狀態連線失敗，請重試；原稿保留。');
   const next=await response.json();if(!alive.current||serial!==sequence.current)return;
   if(next.job_id!==job)throw Error('分析結果的歌曲來源不符。');
   let parsed:StructureDocument|null=null;
   if(next.state==='ready'){
    try{if(!next.candidate)throw Error();parsed=parseStructure(JSON.stringify(next.candidate),source);}catch{throw Error('分析初稿的錄音來源或格式不符，未套用。');}
   }
   setStatus({state:next.state,message:String(next.message??''),candidate:parsed,run_id:next.run_id??null,elapsed_seconds:Number.isFinite(next.elapsed_seconds)?Math.max(0,next.elapsed_seconds):0});
  }catch(error){if(alive.current&&serial===sequence.current)setStatus({state:'connection_error',message:error instanceof TypeError?'分析狀態連線中斷，請更新狀態；原稿保留。':error instanceof Error?error.message:'分析狀態連線失敗。',candidate:null,run_id:null,elapsed_seconds:0});}
  finally{if(alive.current&&serial===sequence.current)setPending(false);}
 }
 useEffect(()=>{alive.current=true;setStatus(null);setApplied(null);void request();return()=>{alive.current=false;sequence.current++;};},[endpoint,job,source?.fingerprint,source?.audio_sha256]);
 useEffect(()=>{if(!source||!status||!['running','cancelling','busy'].includes(status.state)||pending)return;const timer=setTimeout(()=>void request(),2500);return()=>clearTimeout(timer);},[status,pending,source?.fingerprint]);
 useEffect(()=>{const player=audio.current;setAudioError('');stopAt.current=null;return()=>player?.pause();},[candidate]);
 const preview=candidate&&applied!==(status?.run_id??'ready');
 return <section className="ss-analysis" aria-label="歌曲結構自動分析">
  <h2>{hasDocument?'歌曲結構分析':'先分析歌曲結構，再挑一大段練習'}</h2>
  <p>用原錄音找出前奏、主歌、副歌等大段，不必逐一填寫細部根音區段。初稿的名稱與交界仍可回聽修正。</p>
  <p role="status" aria-label="歌曲結構分析狀態">{status?.message??(source?'正在查詢分析狀態…':'正在取得錄音來源…')}{working?` · 已經過 ${rootStamp(status!.elapsed_seconds)}`:''}</p>
  {working?<p>這台電腦完整歌曲約需 15–20 分鐘。可先離開頁面，稍後回來查看；取消分析不會刪掉練習進度。</p>:null}
  <div className="ss-actions">
   <button className={candidate?undefined:"ss-primary"} disabled={!source||disabled||pending||working||status?.state==='unavailable'} onClick={()=>{setApplied(null);void request('POST',hasDocument||status?.state==='ready');}}>{hasDocument||candidate?'重新分析結構':'分析歌曲結構'}</button>
   {working?<button disabled={pending||status?.state==='cancelling'} onClick={()=>void request('DELETE')}>取消結構分析</button>:null}
   <button disabled={!source||pending} onClick={()=>void request()}>更新分析狀態</button>
  </div>
  {preview?<section className="ss-analysis-preview" aria-label="自動結構初稿預覽">
   <h3>分析初稿：{candidate.sections.length} 個歌曲大段</h3>
   <p>{hasDocument?'目前結構尚未改動。選擇替換後才會保存，仍可復原。':'先看這些大段；套用後就能選主歌或副歌進入根音練習。'}</p>
   <audio ref={audio} controls={!disabled} preload="metadata" src={disabled?undefined:`${endpoint}/audio?fingerprint=${source!.fingerprint}&audio_sha256=${source!.audio_sha256}`} onTimeUpdate={()=>{const a=audio.current;if(a&&stopAt.current!==null&&a.currentTime>=stopAt.current){a.pause();stopAt.current=null;}}}/>
   {audioError?<p role="status">{audioError}</p>:null}
   <ol>{candidate.sections.map(s=><li key={s.id}><span>{s.display_label} · {rootStamp(s.start)}–{rootStamp(s.end)} · 待確認</span><button disabled={disabled||s.end-s.start<.1} aria-label={`預覽回聽 ${s.display_label} ${rootStamp(s.start)}`} onClick={()=>{const a=audio.current;if(a){setAudioError('');a.pause();a.currentTime=s.start;stopAt.current=s.end;void a.play().catch(error=>{if(error.name!=='AbortError')setAudioError('原曲暫時無法播放，請稍後再試。');});}}}>聽這段初稿</button></li>)}</ol>
   <button className="ss-primary" disabled={disabled||pending} onClick={()=>{audio.current?.pause();if(onApply(candidate))setApplied(status?.run_id??'ready');}}>{hasDocument?'以初稿替換目前結構':'套用分析初稿'}</button>
  </section>:null}
 </section>;
}
