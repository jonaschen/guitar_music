import {useState} from 'react';
import {relativeChord} from './chordTheory';
import {rootStamp} from './rootPracticeDocument';
export type DegreeChord={id?:string;start:number;end:number;symbol:string|null};
type Range={start:number;end:number};
export function ChordDegreeView({chords,tonic,mode,range,scope,dirty,blocked}:{
 chords:DegreeChord[];tonic:string|null;mode:string;range:Range;scope:Range|null;dirty:boolean;blocked:boolean;
}){
 const [view,setView]=useState('names');
 const start=Math.max(range.start,scope?.start??range.start),end=Math.min(range.end,scope?.end??range.end);
 const validRange=Number.isFinite(start+end)&&end>start;
 const ready=!!tonic&&['major','minor'].includes(mode)&&!blocked;
 const rows=validRange?chords.filter(c=>c.start<end&&c.end>start):[];
 return <details><summary>用級數理解這段和弦</summary>
  <p aria-label="級數使用的假設">依 {tonic??'未定'} {mode==='major'?'大調':mode==='minor'?'小調':'未定／其他'}{dirty?'（試算，假設尚未保存）':'（目前載入的假設）'}。這是名稱換算，不是自動判斷音樂功能。</p>
  <label>和弦級數顯示方式<select aria-label="和弦級數顯示方式" value={view} onChange={e=>setView(e.target.value)}>
   <option value="names">實際和弦名稱</option><option value="roman">羅馬級數</option><option value="numbers">數字級數</option>
  </select></label>
  {blocked?<p>來源或版本待核對，先保留實際和弦名稱。</p>:!ready?<p>主音或調式尚未確定，先保留實際和弦名稱。</p>:null}
  {scope?<p>只套用此局部假設的 {rootStamp(scope.start)}–{rootStamp(scope.end)}；超出範圍不延伸推定。</p>:null}
  <ol className="learning-degrees" aria-label="依假設換算的和弦行進">{rows.map(c=>{
   const derived=ready&&c.symbol?relativeChord(c.symbol,tonic,mode):null;
   return <li key={c.id??`${c.start}:${c.end}`}><span>{rootStamp(Math.max(start,c.start))}–{rootStamp(Math.min(end,c.end))}</span>{' '}
    {c.symbol??'待聽'}{c.symbol==='N.C.'?'（無和弦）':ready&&view!=='names'&&c.symbol ? derived ? <>
     {' → '}{view==='roman'?derived.roman:derived.number}{derived.bassName?` · 低音 ${derived.bassName}${derived.bassDegree?`（${derived.bassDegree} 級）`:''}`:''}
    </>:'（尚未支援級數換算）':null}</li>;
  })}</ol>
  {!rows.length?<p>{validRange?'這個範圍尚無和弦區段。':'目前 A–B 不在這個假設的範圍內。'}</p>:null}
  <p>以主音為 1、同主音大音階為級數基準；例如 A 小調的 C 記為 ♭III。羅馬大小寫區分大／小和弦；° 是減、ø 是半減、+ 是增。數字後 m 表示小和弦，括號表示類型或延伸音。</p>
  <p>低音另列，不把 C/E 的 E 當根音；add6 是加六音，不是轉位數字。未填的和弦保留待聽，不會從根音或原分析補答案。</p>
 </details>;
}
