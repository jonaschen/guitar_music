import type {SongScore} from './types';
import {notationBars} from './melodyNotation';
import type {TimingPreview} from './PartialTimingSheet';
import type {WorksheetAnchor,WorksheetLine} from './worksheetDocument';
export type NotePosition={start:number;end:number;label:string;kind:'metered'|'local';grid_id:string};
/** Same cropped opening rule as the visible score; no second bar numbering scheme. */
export function readingBars(score:SongScore){
  const raw=notationBars(score);
  return raw[0]?.number===-1&&raw[1]?.number===0&&!score.beats.some(b=>b.time<raw[1].start)?[{...raw[1],start:raw[0].start},...raw.slice(2)]:raw;
}
function identity(value:unknown){let hash=2166136261;for(const c of JSON.stringify(value)){hash^=c.charCodeAt(0);hash=Math.imul(hash,16777619);}return (hash>>>0).toString(16);}
export function fullNotePositions(score:SongScore,bars:ReturnType<typeof readingBars>):NotePosition[]{
  const beats=score.beats;
  if(score.analysis.timing_status==='unmetered'||beats.length<2||beats.some((b,i)=>!Number.isFinite(b.time)||b.time<0||i>0&&b.time<=beats[i-1].time))return [];
  const grid_id=identity([score.analysis.time_signature,beats.map(b=>[b.time,b.beat,b.measure]),bars]);
  return bars.map(b=>({start:b.start,end:b.end,label:b.number===0?'起始片段':`Bar ${b.number}`,kind:'metered',grid_id}));
}
export function localNotePositions(preview:TimingPreview|null):NotePosition[]{
  if(!preview)return [];
  const grid_id=identity(preview.regions);
  return preview.regions.flatMap((r,ri)=>r.bars.map((b,i)=>({start:b.start,end:b.end,label:`段落 ${ri+1} 第 ${i+1} 小節（草稿待確認）`,kind:'local' as const,grid_id})));
}
export function anchorStatus(anchor:WorksheetAnchor,score:SongScore,positions:NotePosition[]){
  if(anchor.source_start_seconds!==(score.song.source_start_seconds??0)||anchor.duration_seconds!==score.song.duration_seconds)return '來源時間範圍已改變；請重新確認定位';
  if(anchor.kind!=='seconds'&&!positions.some(p=>p.kind===anchor.kind&&p.grid_id===anchor.grid_id))return '拍格已改變；保留原秒數，請重新確認定位';
  return '';
}
export function anchorMatchesSource(anchor:WorksheetAnchor,score:SongScore){return anchor.source_start_seconds===(score.song.source_start_seconds??0)&&anchor.duration_seconds===score.song.duration_seconds;}
export function notesInRange(lines:WorksheetLine[],score:SongScore,start:number,end:number){
  return lines.filter(r=>r.anchor&&anchorMatchesSource(r.anchor,score)&&(r.anchor.end===null?r.anchor.time>=start&&r.anchor.time<end:r.anchor.time<end&&r.anchor.end>start));
}

export function chordTimePieces(score:SongScore,start=0,end=score.song.duration_seconds){
  const pieces:Array<{start:number;end:number;chord?:SongScore['chords'][number]}>=[];let cursor=start;
  for(const c of score.chords){
    if(c.end<=start||c.start>=end)continue;
    const from=Math.max(start,c.start),to=Math.min(end,c.end);
    if(from>cursor)pieces.push({start:cursor,end:from});
    pieces.push({start:from,end:to,chord:c});cursor=Math.max(cursor,to);
  }
  if(cursor<end)pieces.push({start:cursor,end});return pieces;
}
