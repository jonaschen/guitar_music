import {useEffect,useRef,useState} from 'react';
import type {StructureSource} from './songStructureDocument';
const names=['C','C♯ / D♭','D','D♯ / E♭','E','F','F♯ / G♭','G','G♯ / A♭','A','A♯ / B♭','B'];
type Energy={state:'available'|'insufficient';pitch_classes:{pitch_class:number;relative_db:number}[]};
export function RecordingPitchEnergy({api,job,source,range,disabled}:{api:string;job:string;source:StructureSource;range:{start:number;end:number};disabled:boolean}){
 const [result,setResult]=useState<Energy|null>(null),[message,setMessage]=useState('按需讀取目前 A–B；不會加入參考音。'),[busy,setBusy]=useState(false);
 const pending=useRef<AbortController|null>(null),generation=useRef(0);
 const valid=Number.isFinite(range.start+range.end)&&range.start>=0&&range.end<=source.duration&&range.end-range.start>=.5&&range.end-range.start<=30;
 useEffect(()=>{generation.current++;pending.current?.abort();setResult(null);setBusy(false);setMessage('範圍改變後請重新查看錄音線索。');return()=>{generation.current++;pending.current?.abort();};},[source.fingerprint,source.audio_sha256,range.start,range.end,disabled]);
 async function analyze(){if(!valid||disabled||busy)return;const ticket=++generation.current,controller=new AbortController();pending.current=controller;setBusy(true);setResult(null);setMessage('正在讀取這段錄音的音級能量…');try{
  const response=await fetch(`${api}/api/v1/jobs/${encodeURIComponent(job)}/learning-practice/pitch-energy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fingerprint:source.fingerprint,audio_sha256:source.audio_sha256,...range}),signal:controller.signal});if(!response.ok)throw Error(response.status===409?'錄音來源已改變，請重新載入。':'錄音線索暫時無法讀取，原有和弦稿仍保留。');
  const data=await response.json();if(ticket!==generation.current)return;
  if(data.source?.fingerprint!==source.fingerprint||data.source?.audio_sha256!==source.audio_sha256||data.start!==range.start||data.end!==range.end||data.method!=='stft-pitch-class-energy-v1'||!['available','insufficient'].includes(data.state)||!Array.isArray(data.pitch_classes)||data.state==='available'&&(data.pitch_classes.length!==12||data.pitch_classes.some((r:any,i:number)=>r.pitch_class!==i||!Number.isFinite(r.relative_db)||r.relative_db>0||r.relative_db< -100)))throw Error('線索的來源或範圍無法核對，請重試。');
  setResult(data);setMessage(data.state==='available'?'已取得這段錄音的頻率能量；不是音符或和弦判定。':'這段太安靜或指定頻帶能量不足，無法提供線索。');
 }catch(e){if(ticket===generation.current&&!controller.signal.aborted)setMessage(e instanceof Error?e.message:'線索暫時無法讀取。');}finally{if(ticket===generation.current)setBusy(false);}}
 return <details className="learning-panel"><summary>錄音音級線索</summary><p>目前 A–B：{valid?`${range.start.toFixed(2)}–${range.end.toFixed(2)} 秒`:'請選 0.5–30 秒'}。將 C2–C7 附近頻率能量折合成十二音級；人聲、泛音、和弦外旋律與打擊聲都可能影響它。</p><button disabled={disabled||busy||!valid} onClick={()=>void analyze()}>{busy?'讀取中…':'查看這段錄音的音級能量'}</button><p role="status" aria-label="錄音音級線索狀態">{message}</p>
 {result?.state==='available'?<><p>0 dB 為本段最強音級；較小表示相對較弱，不是正確機率，也不能直接判定根音、轉位或組成音。</p><div aria-label="錄音十二音級能量">{result.pitch_classes.map(r=><div key={r.pitch_class} className="learning-energy-row"><span>{names[r.pitch_class]}</span><meter aria-label={`${names[r.pitch_class]} 相對能量`} min={-60} max={0} value={Math.max(-60,r.relative_db)}/><output>{r.relative_db.toFixed(1)} dB</output></div>)}</div></>:null}</details>;
}
