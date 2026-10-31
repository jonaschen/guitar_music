import type {SongScore} from './types';

/** Uses the shared score, autosave and undo path; no separate player state. */
export function DownbeatRhythmControl({score,onCommit}:{score:SongScore;onCommit:(base:SongScore,next:SongScore)=>boolean}) {
  if(score.analysis.timing_status==='unmetered'||!['3/4','4/4'].includes(score.analysis.time_signature)||!score.beats.length)return null;
  const selected=score.rhythm.pattern_id==='observed-downbeats-v1';
  const meter=Number(score.analysis.time_signature[0]);
  return <>
    <button type="button" disabled={selected} onClick={()=>onCommit(score,{...score,rhythm:{
      pattern_id:'observed-downbeats-v1',label:'每小節一下',subdivision:4,
      display:Array.from({length:meter},(_,i)=>i===0?'D':null),
      accents:Array.from({length:meter},(_,i)=>i===0?1:0),confidence:0,
    }})}>{selected?'已選：每小節一下':'每小節一下'}</button>
    {selected?<p className="performance-draft-status" role="status">依目前拍格，在每小節第一拍刷奏；換和弦不加刷。可用「復原」回到原刷法。</p>:null}
  </>;
}
