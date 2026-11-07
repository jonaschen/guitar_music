import {createContext,useContext,useState,type ReactNode} from 'react';
import type {SongScore} from './types';
import {useWorksheet} from './worksheetState';
import {sourceJobId} from './scoreVersion';
import {anchorMatchesSource,anchorStatus,notesInRange,type NotePosition} from './songNoteTimeline';
type Notes={job:string;api:string;score:SongScore;sheet:ReturnType<typeof useWorksheet>;selected:string|null;editRequest:number;scrollToEditor:boolean;marking:boolean;setMarking:(value:boolean)=>void;select:(id:string|null,scroll?:boolean)=>void};
const Context=createContext<Notes|null>(null);
function SourceNotes({job,score,children}:{job:string;score:SongScore;children:ReactNode}){
  const api='/backend',sheet=useWorksheet(job,api),[request,setRequest]=useState<{id:string|null;nonce:number;scroll:boolean}>({id:null,nonce:0,scroll:true});
  const [marking,setMarking]=useState(false);
  const select=(id:string|null,scroll=true)=>setRequest(previous=>({id,nonce:previous.nonce+1,scroll}));
  return <Context.Provider value={{job,api,score,sheet,selected:request.id,editRequest:request.nonce,scrollToEditor:request.scroll,marking,setMarking,select}}>{children}</Context.Provider>;
}
export function SongNotesProvider({score,children}:{score:SongScore;children:ReactNode}){
  const job=sourceJobId(score);
  return job?<SourceNotes key={job} job={job} score={score}>{children}</SourceNotes>:<>{children}</>;
}
export const useSongNotes=()=>useContext(Context);
/** Each inline occurrence points to the same persisted row; continuation is not another copy. */
export function LocatedSongNotes({start,end,positions,onSeek,disabled,onEdit}:{start:number;end:number;positions:NotePosition[];onSeek:(time:number)=>void;disabled:boolean;onEdit?:()=>void}){
  const notes=useSongNotes();if(!notes)return null;
  const rows=notesInRange(notes.sheet.document.lines,notes.score,start,end);
  if(!rows.length)return null;
  return <div className="located-song-notes" aria-label={`歌詞與簡譜 ${start.toFixed(2)}–${end.toFixed(2)} 秒`}>
    {rows.map(row=>{
      const a=row.anchor!,continued=a.time<start,status=anchorStatus(a,notes.score,positions),number=notes.sheet.document.lines.findIndex(r=>r.id===row.id)+1;
      return <div key={row.id} className="located-song-note" data-note-id={row.id} data-note-time={a.time}>
        <button type="button" className="note-text" aria-label={`編輯第${number}組歌詞與簡譜`} onClick={()=>{onEdit?.();notes.select(row.id);}}>
          {continued?<span>↳ 第{number}組延續</span>:<><span className="located-lyric">{row.lyric||'（待填歌詞）'}</span><span className="located-notation">{row.notation||'（待填簡譜）'}</span></>}
          <small>{a.time.toFixed(2)}{a.end!==null?`–${a.end.toFixed(2)}`:''} 秒{status?' · 位置待確認':a.kind==='local'?' · 小節草稿待確認':''}</small>
        </button>
        <button type="button" disabled={disabled||!anchorMatchesSource(a,notes.score)} aria-label={`從第${number}組位置播放`} onClick={()=>onSeek(a.time)}>從此播放</button>
      </div>;
    })}
  </div>;
}
