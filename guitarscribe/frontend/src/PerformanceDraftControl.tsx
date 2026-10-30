import {useEffect, useRef, useState} from 'react';
import type {SongScore} from './types';

/** One reversible score change; preview requests never save on the server. */
export function PerformanceDraftControl({score,apiBase,onCommit}:{score:SongScore;apiBase:string;onCommit:(base:SongScore,next:SongScore)=>boolean}) {
  const current=useRef(score);current.current=score;
  const request=useRef<AbortController|null>(null);
  const [pending,setPending]=useState(false),[error,setError]=useState('');
  useEffect(()=>{request.current?.abort();setPending(false);setError('');return()=>request.current?.abort();},[score]);
  async function prepare(){
    const controller=new AbortController();request.current?.abort();request.current=controller;
    const obsolete=()=>controller.signal.aborted||current.current!==score;
    setPending(true);setError('');
    try{
      const response=await fetch(`${apiBase}/scores/performance-draft`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(score),signal:controller.signal});
      if(!response.ok)throw new Error('目前無法整理這份譜，原稿已保留。');
      const result=await response.json();
      if(!obsolete()&&!onCommit(score,result.score))setError('工作譜已改變，請重新整理演奏稿。');
    }catch(e){if(!obsolete())setError(e instanceof Error?e.message:'整理失敗，原稿已保留。');}
    finally{if(!obsolete())setPending(false);}
  }
  const params=score.provenance.parameters;
  const prepared=!!params?.performance_draft;
  const unresolved=Number(params?.performance_voicings_unresolved??0);
  return <>
    <button type="button" disabled={pending} onClick={()=>void prepare()}>{pending?'正在整理…':'整理演奏稿'}</button>
    <p className="performance-draft-status" role="status">{prepared
      ? `已整理，可用「復原」回到上一步。${score.analysis.timing_status==='unmetered'?'此曲拍格未確認，仍按原時間換和弦、每段彈一次。':'換和弦位置、譜面與播放使用同一份稿。'}${unresolved?`仍有 ${unresolved} 段未取得完整指型。`:''}${Number(params?.performance_unquantized_edges??0)?'部分短音或人工邊界仍保留原時間。':''}`
      : '保留和弦名稱、短和弦與人工修改；補足可用指型，有 4/4 拍格時整理換和弦位置。'}</p>
    {error?<p role="alert">{error}</p>:null}
  </>;
}
