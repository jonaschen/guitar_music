import {useEffect, useState} from 'react';
import type {AnalysisJob} from './types';

const labels: Record<string,string> = {
  queued:'等待分析名額', resolving:'準備原曲音檔', preprocessing:'整理音訊',
  beat_analysis:'尋找拍點與小節', chord_analysis:'辨認和弦',
  vocal_separation:'分離人聲', melody_analysis:'分析旋律', postprocessing:'整理分析結果',
};
function elapsed(since:string, now:number) {
  const timestamp=Date.parse(since);
  if (!Number.isFinite(timestamp)) return null;
  const seconds=Math.max(0,Math.floor((now-timestamp)/1000));
  return `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;
}

export function AnalysisProgress({job,onCancel}:{job:AnalysisJob;onCancel:()=>void}) {
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return ()=>clearInterval(timer);},[]);
  const total=elapsed(job.created_at,now),stage=elapsed(job.updated_at,now);
  return <section className="job-progress" aria-label="分析進度">
    <strong aria-live="polite">{labels[job.status]??job.message}</strong>
    <progress aria-label="正在分析" />
    {job.status==='queued' ? total&&<p>已等待 {total}</p> : <p>
      {stage ? `本階段已經過 ${stage}` : '正在處理這個階段'}{total ? `；總共已經過 ${total}` : ''}
    </p>}
    <p>各階段耗時不同，完成後會自動開啟結果。重新開啟此頁仍可查看進度。</p>
    <button className="ghost-button" type="button" onClick={onCancel}>Cancel analysis</button>
  </section>;
}
