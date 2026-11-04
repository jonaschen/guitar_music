import {useEffect, useState} from 'react';
import type {SongScore} from './types';
import {sourceJobId} from './scoreVersion';

export type LocalBar = {start:number;end:number;beats:number[]};
export type TimingPreview = {job_id:string;duration_seconds:number;source_start_seconds:number;covered_seconds:number;
  regions:Array<{start:number;end:number;beats_per_bar:number;bars:LocalBar[]}>};
export const timeLabel=(seconds:number)=>`${Math.floor(seconds/60)}:${(seconds%60).toFixed(1).padStart(4,'0')}`;

export function useTimingPreview(score:SongScore){
  const job=sourceJobId(score),duration=score.song.duration_seconds,offset=score.song.source_start_seconds??0;
  const key=`${job}:${duration}:${offset}`;
  const [loaded,setLoaded]=useState<{key:string;data:TimingPreview}|null>(null);
  useEffect(()=>{
    if(!job)return;
    const controller=new AbortController();
    void fetch(`/backend/api/v1/jobs/${encodeURIComponent(job)}/timing-preview`,{signal:controller.signal})
      .then(r=>r.ok?r.json():null).then((data:TimingPreview|null)=>{
        if(!controller.signal.aborted&&data?.job_id===job&&data.duration_seconds===duration&&data.source_start_seconds===offset&&Array.isArray(data.regions))
          setLoaded({key,data});
      }).catch(()=>{/* Missing older diagnostics leave the existing time sheet usable. */});
    return ()=>controller.abort();
  },[job,duration,offset,key]);
  return loaded?.key===key?loaded.data:null;
}

/** Presentation only. Unknown ranges have seconds, never invented bar numbers. */
export function PartialTimingSheet({score,preview,playing,playhead,disabled,onSeek}:{score:SongScore;preview:TimingPreview;
  playing:boolean;playhead:number;disabled:boolean;onSeek:(from:number)=>void}){
  const pieces:Array<{start:number;end:number;region?:TimingPreview['regions'][number];index?:number}>=[];
  let cursor=0;
  preview.regions.forEach((region,index)=>{
    if(region.start>cursor)pieces.push({start:cursor,end:region.start});
    pieces.push({start:region.start,end:region.end,region,index:index+1});cursor=region.end;
  });
  if(cursor<score.song.duration_seconds)pieces.push({start:cursor,end:score.song.duration_seconds});
  function chords(start:number,end:number,showTime=false){
    const entries=score.chords.filter(c=>c.end>start&&c.start<end);
    return entries.length?entries.map(c=>{
      const from=Math.max(start,c.start),to=Math.min(end,c.end);
      return <button key={c.id} type="button" data-chord-id={c.id} data-start={from} data-end={to}
        className={playing&&playhead>=from&&playhead<to?'current-chord':''} disabled={disabled}
        aria-label={`播放 ${from.toFixed(2)} 秒的 ${c.symbol}`} title={`${from.toFixed(2)}–${to.toFixed(2)} 秒`}
        onClick={()=>onSeek(from)}>{showTime?<small>{timeLabel(from)}</small>:null}<strong>{c.symbol}</strong>{c.start<start?<span aria-label="延續"> —</span>:null}</button>;
    }):<span className="no-chord">—</span>;
  }
  return <div className="partial-timing-sheet" aria-label="局部小節預覽">
    {pieces.map(piece=><section key={piece.start} className={piece.region?'partial-region':'partial-unknown'}>
      <p className="partial-region-label">{timeLabel(piece.start)}–{timeLabel(piece.end)} · {piece.region?`段落 ${piece.index} · ${piece.region.beats_per_bar}/4 小節草稿`:'小節未確認 · 按時間排列'}</p>
      {piece.region?<div className="notation-sheet">{piece.region.bars.map((bar,i)=><div
        className={`notation-measure${playing&&playhead>=bar.start&&playhead<bar.end?' current-measure':''}`}
        key={bar.start} aria-label={`段落 ${piece.index} 第 ${i+1} 小節`}>
        <span className="measure-number">{piece.index}.{i+1}</span>
        <div className="measure-chords">{chords(bar.start,bar.end)}</div>
      </div>)}</div>:<div className="unknown-chords">{chords(piece.start,piece.end,true)}</div>}
    </section>)}
  </div>;
}
