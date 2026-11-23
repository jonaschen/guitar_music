import {useEffect,useRef,useState} from 'react';
import type {SongScore} from './types';
type Advice={capo:number;shape_key:string;difficulty:number;open_chords:number;barre_chords:number;covered_chords:number;total_chords:number;transition_cost:number;position_penalty:number;ranking_score:number;voicing_plan:Record<string,string>};

/** Suggestions are read-only; only an explicit selection changes arrangement. */
export function CapoAdvice({score,apiBase,onChoose,disabled=false}:{score:SongScore;apiBase:string;onChoose:(capo:number,plan:Record<string,string>)=>void;disabled?:boolean}){
 const [maximum,setMaximum]=useState<string|null>(null),[preferred,setPreferred]=useState('');
 const limit=maximum??String(score.guitar.max_capo);
 const [result,setResult]=useState<{score:SongScore;key:string;rows:Advice[]}|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('比較不會修改原譜，採用方案才會改變 Capo。');
 const key=JSON.stringify([limit,preferred]),current=useRef({score,key}),request=useRef(0);current.current={score,key};
 const valid=limit.trim()!==''&&Number.isInteger(Number(limit))&&Number(limit)>=0&&Number(limit)<=score.guitar.max_capo
  &&(preferred===''||(Number.isInteger(Number(preferred))&&Number(preferred)>=0&&Number(preferred)<=score.guitar.max_fret));
 const standard=score.guitar.tuning.join(',')==='40,45,50,55,59,64';
 const rows=result?.score===score&&result.key===key?result.rows:null;
 useEffect(()=>{request.current++;setBusy(false);setMessage('比較不會修改原譜，採用方案才會改變 Capo。');},[score,key]);
 useEffect(()=>()=>{request.current++;},[]);
 async function compare(){
  if(busy||disabled||!valid||!standard)return;
  const ticket=++request.current,base=score,parameters=key;
  const obsolete=()=>ticket!==request.current||base!==current.current.score||parameters!==current.current.key;
  setBusy(true);setResult(null);setMessage('正在比較完整按法與前後換把…');
  try{
   const response=await fetch(`${apiBase}/scores/capo-recommendations`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({score,max_capo:Number(limit),preferred_fret:preferred===''?null:Number(preferred)})});
   const body=await response.json();if(!response.ok)throw Error(typeof body.detail==='string'?body.detail:'暫時無法比較按法。');
   if(obsolete())return;
   if(!Array.isArray(body)||body.some(r=>!Number.isInteger(r.capo)||r.capo<0||r.capo>Number(limit)||!Number.isInteger(r.covered_chords)||!Number.isInteger(r.total_chords)||r.covered_chords<0||r.covered_chords>r.total_chords||!Number.isFinite(r.ranking_score+r.transition_cost+r.position_penalty+r.difficulty)||!r.voicing_plan||typeof r.voicing_plan!=='object'||Array.isArray(r.voicing_plan)||Object.values(r.voicing_plan).some(v=>typeof v!=='string')))throw Error('建議格式無法核對，原譜保留。');
   setResult({score:base,key:parameters,rows:body});setMessage(body.length?'已依完整覆蓋、按法難度及換把成本排序。仍需依自己的手感選擇。':'目前沒有可比較的和弦。');
  }catch(error){if(!obsolete())setMessage(error instanceof Error?error.message:'暫時無法比較按法。');}
  finally{if(!obsolete())setBusy(false);}
 }
 return <details className="capo-advice"><summary>比較較容易的 Capo 按法</summary>
  <p>以標準調弦比較目前已填的和弦；不改原曲音高、根音稿或歌曲結構。按法與換把分數是估計，不代表演奏難度的客觀量尺。</p>
  <div className="capo-advice-fields"><label>建議最高 Capo<input aria-label="建議最高 Capo" type="number" min="0" max={score.guitar.max_capo} value={limit} onChange={e=>setMaximum(e.target.value)}/></label>
  <label>偏好把位（Capo 起算，選填）<input aria-label="偏好把位" type="number" min="0" max={score.guitar.max_fret} value={preferred} placeholder="不指定" onChange={e=>setPreferred(e.target.value)}/></label></div>
  {!valid?<p>最高 Capo 需為 0–{score.guitar.max_capo}；偏好把位需為 0–{score.guitar.max_fret} 的整數或留空。</p>:null}
  {!standard?<p>目前僅支援標準調弦 EADGBE。</p>:null}
  <button type="button" disabled={busy||disabled||!valid||!standard} onClick={()=>void compare()}>{busy?'正在比較…':'比較按法方案'}</button><p role="status" aria-label="Capo 建議狀態">{message}</p>
  {rows?<div className="capo-advice-options">{rows.slice(0,3).map(row=><section key={row.capo} aria-label={`Capo 方案 ${row.capo}`}><strong>Capo {row.capo} · 按法調性 {row.shape_key}</strong>
   <p>完整按法 {row.covered_chords} / {row.total_chords} · 開放 {row.open_chords} · 橫按 {row.barre_chords}</p>
   <p>按法難度 {row.difficulty} · 換把成本 {row.transition_cost}{preferred!==''?` · 把位差距 ${row.position_penalty}`:''}</p>
   {row.covered_chords<row.total_chords?<p>部分和弦沒有完整按法；不以單根音代替整個和弦。</p>:null}
   <button type="button" disabled={disabled||row.covered_chords<row.total_chords||row.total_chords===0} onClick={()=>onChoose(row.capo,row.voicing_plan)}>採用 Capo {row.capo}</button>
  </section>)}</div>:null}
 </details>;
}
