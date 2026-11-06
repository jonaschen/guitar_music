import type {SongScore} from './types';
import {useTimingPreview} from './PartialTimingSheet';
export type AuditionContent='chord'|'root';
export type AuditionPulse='original'|'bar'|'two'|'one'|'half';
export function AuditionControls({score,content,pulse,onContent,onPulse,sourceVolume,guitarVolume,onSourceVolume,onGuitarVolume}:{
  score:SongScore;content:AuditionContent;pulse:AuditionPulse;onContent:(v:AuditionContent)=>void;onPulse:(v:AuditionPulse)=>void;
  sourceVolume:number;guitarVolume:number;onSourceVolume:(v:number)=>void;onGuitarVolume:(v:number)=>void;
}){
  const preview=useTimingPreview(score);
  const partial=score.analysis.timing_status==='unmetered';
  const available=partial?!!preview?.regions.length:score.beats.length>=2&&['3/4','4/4'].includes(score.analysis.time_signature);
  return <div className="audition-controls">
    <label>撥奏 <select aria-label="撥奏內容" value={content} onChange={e=>onContent(e.target.value as AuditionContent)}><option value="chord">和弦</option><option value="root">只彈根音</option></select></label>
    <label>頻率 <select aria-label="撥奏頻率" value={pulse} onChange={e=>onPulse(e.target.value as AuditionPulse)}>
      <option value="original">沿用原刷奏</option>
      <option value="bar" disabled={!available}>每小節一次</option><option value="two" disabled={!available}>每兩拍一次</option>
      <option value="one" disabled={!available}>每拍一次</option><option value="half" disabled={!available}>每拍兩次</option>
    </select></label>
    <label>原曲音量 <input aria-label="原曲音量" type="range" min="0" max="1" step=".01" value={sourceVolume} onChange={e=>onSourceVolume(Number(e.target.value))}/><output>{Math.round(sourceVolume*100)}%</output></label>
    <label>和弦／根音音量 <input aria-label="和弦／根音音量" type="range" min="0" max="1" step=".01" value={guitarVolume} onChange={e=>onGuitarVolume(Number(e.target.value))}/><output>{Math.round(guitarVolume*100)}%</output></label>
    {partial&&pulse!=='original'?<small role="status">依待確認拍點試聽；未知段暫停伴奏，原曲繼續。這些選項不更改樂譜。</small>:!available?<small>尚無可用拍點，沿用換和弦時的撥奏；仍可切換根音。</small>:null}
  </div>;
}
