import {encodeDocument,type WorksheetAnchor,type WorksheetDocument} from './worksheetDocument';
export type MarkFrame={duration_seconds:number;source_start_seconds:number};
export type MarkUndo={id:string;after:WorksheetAnchor};
const sameFrame=(a:WorksheetAnchor,frame:MarkFrame)=>a.duration_seconds===frame.duration_seconds&&a.source_start_seconds===frame.source_start_seconds;
export function markLyric(document:WorksheetDocument,id:string,time:number,frame:MarkFrame){
  const index=document.lines.findIndex(row=>row.id===id),row=document.lines[index];
  if(!row||!row.lyric.trim())throw Error('這行沒有歌詞，可略過這句。');
  if(row.anchor)throw Error('這句已有位置，已保留；可略過或到微調修改。');
  if(!Number.isFinite(time)||time<0||time>=frame.duration_seconds)throw Error('原曲已結束或位置無效，請先播放到這句開頭。');
  const before=document.lines.slice(0,index).map(r=>r.anchor).filter(a=>a&&sameFrame(a,frame)).at(-1);
  const after=document.lines.slice(index+1).map(r=>r.anchor).find(a=>a&&sameFrame(a,frame));
  if(before&&time<=before.time||after&&time>=after.time)throw Error('這裡與前後已標位置順序不符，請回聽這句再標記。');
  const anchor:WorksheetAnchor={time,end:null,...frame,kind:'seconds',grid_id:null};
  const next={...document,lines:document.lines.map(r=>r.id===id?{...r,anchor}:r)};
  encodeDocument(next);return {document:next,undo:{id,after:anchor} as MarkUndo};
}
export function undoLyricMark(document:WorksheetDocument,undo:MarkUndo){
  const row=document.lines.find(r=>r.id===undo.id),a=row?.anchor,b=undo.after;
  if(!a||a.time!==b.time||a.end!==b.end||a.source_start_seconds!==b.source_start_seconds||a.duration_seconds!==b.duration_seconds||a.kind!==b.kind||a.grid_id!==b.grid_id)throw Error('這句位置已被修改，未撤銷其他修改。');
  return {...document,lines:document.lines.map(r=>r.id===undo.id?{...r,anchor:null}:r)};
}
