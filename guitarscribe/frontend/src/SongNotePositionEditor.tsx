import {useState} from 'react';
import type {SongScore} from './types';
import type {WorksheetAnchor,WorksheetLine} from './worksheetDocument';
import {anchorStatus,type NotePosition} from './songNoteTimeline';
export function SongNotePositionEditor({row,score,positions,playhead,onChange,onSeek,disabled,playbackDisabled}:{row:WorksheetLine;score:SongScore;positions:NotePosition[];playhead:number;onChange:(anchor:WorksheetAnchor|null)=>void;onSeek:(time:number)=>void;disabled:boolean;playbackDisabled:boolean}){
  const [from,setFrom]=useState(String(row.anchor?.time??'')),[to,setTo]=useState(row.anchor?.end===null||!row.anchor?'':String(row.anchor.end));
  const [kind,setKind]=useState<WorksheetAnchor['kind']>(row.anchor?.kind??'seconds'),[message,setMessage]=useState('');
  const status=row.anchor?anchorStatus(row.anchor,score,positions):'未定位；來源字幕時間不代表已確認';
  const valid=from.trim()!==''&&Number.isFinite(Number(from))&&Number(from)>=0&&Number(from)<score.song.duration_seconds&&(to.trim()===''||Number.isFinite(Number(to))&&Number(to)>Number(from)&&Number(to)<=score.song.duration_seconds);
  function seconds(start:string,end=''){setFrom(start);setTo(end);setKind('seconds');}
  return <div className="note-position-editor">
    <p role="status">{status||'已指定位置'}{row.anchor?` · ${row.anchor.time.toFixed(2)}${row.anchor.end!==null?'–'+row.anchor.end.toFixed(2):''} 秒`:''}</p>
    {positions.length?<><label>起始小節<select aria-label="筆記起始小節" value={positions.findIndex(p=>p.start===Number(from)&&from!==''&&p.kind===kind)} onChange={e=>{const p=positions[Number(e.target.value)];if(p){setFrom(String(p.start));setTo(String(p.end));setKind(p.kind);}}}><option value="-1">請選擇小節，或改用秒數</option>{positions.map((p,i)=><option key={i} value={i}>{p.label} · {p.start.toFixed(2)}–{p.end.toFixed(2)}秒</option>)}</select></label>
    <label>延續到小節結尾<select aria-label="筆記結束小節" value={positions.findIndex(p=>p.end===Number(to)&&to!==''&&p.kind===kind)} onChange={e=>{const p=positions[Number(e.target.value)];if(p)setTo(String(p.end));}}><option value="-1">依下方結束秒數</option>{positions.map((p,i)=>p.end>Number(from)?<option key={i} value={i}>{p.label} · {p.end.toFixed(2)}秒</option>:null)}</select></label></>:<p>沒有可靠的小節位置，請用歌曲內的秒數定位。</p>}
    <label>開始秒數<input aria-label="筆記開始秒數" type="number" min="0" step="0.01" value={from} onChange={e=>seconds(e.target.value,to)}/></label>
    <label>結束秒數（可空白）<input aria-label="筆記結束秒數" type="number" min="0" step="0.01" value={to} onChange={e=>{setTo(e.target.value);setKind('seconds');}}/></label>
    <button type="button" onClick={()=>seconds(String(playhead))}>使用目前播放位置作為開始</button>
    {row.start!==null?<button type="button" onClick={()=>seconds(String(row.start),row.end!==null?String(row.end):'')}>帶入來源參考時間（仍需確認）</button>:null}
    <p>一句可跨小節，依實際起訖保留同一組文字；跨未知段仍按秒數，不推算歌詞或簡譜節奏。</p>
    {status.startsWith('拍格')||status.startsWith('來源')?<p>重新確認會保留下方秒數；若已不是目前的小節起點，改為秒數定位。請先核對來源及位置。</p>:null}
    <button type="button" disabled={!valid||disabled} onClick={()=>{const current=kind==='seconds'?undefined:positions.find(p=>p.kind===kind&&p.start===Number(from));onChange({time:Number(from),end:to.trim()===''?null:Number(to),kind:current?.kind??'seconds',grid_id:current?.grid_id??null,source_start_seconds:score.song.source_start_seconds??0,duration_seconds:score.song.duration_seconds});setMessage('已指定位置，將顯示在和弦譜對應處。');}}>確認歌詞與簡譜位置</button>
    {row.anchor?<><button type="button" disabled={disabled} onClick={()=>{onChange(null);setMessage('已解除定位，文字仍保留在待安排列。');}}>解除定位並保留文字</button><button type="button" disabled={disabled||playbackDisabled||!!status&&status.startsWith('來源')} onClick={()=>onSeek(row.anchor!.time)}>從此位置播放</button></>:null}
    {message?<p role="status">{message}</p>:null}
  </div>;
}
