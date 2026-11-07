import {LocatedSongNotes} from './SongNotes';
import type {NotePosition} from './songNoteTimeline';
import type {SongScore} from './types';
import {timeLabel} from './PartialTimingSheet';

/** Continuous seconds-based reading: no inferred bars, merging, or equal durations. */
export function ContinuousChordReading({score,playing,playhead,disabled,onSeek,onEdit,positions=[]}:{score:SongScore;playing:boolean;playhead:number;disabled:boolean;onSeek:(from:number)=>void;onEdit?:()=>void;positions?:NotePosition[]}){
  const pieces:Array<{start:number;end:number;id?:string;symbol?:string}>=[];
  let cursor=0;
  for(const chord of score.chords){
    if(chord.start>cursor)pieces.push({start:cursor,end:chord.start});
    pieces.push({start:chord.start,end:chord.end,id:chord.id,symbol:chord.symbol});
    cursor=Math.max(cursor,chord.end);
  }
  if(cursor<score.song.duration_seconds)pieces.push({start:cursor,end:score.song.duration_seconds});
  return <div className="continuous-chord-reading" aria-label="連續和弦讀譜">
    {pieces.map((piece,i)=>{
      const gap=piece.id===undefined,rest=!gap&&['n','nc','n.c.','no_chord'].includes((piece.symbol??'').trim().toLowerCase());
      return <div className="reading-piece" key={piece.id??`gap-${i}`}><button type="button" data-chord-id={piece.id} data-gap={gap?'true':undefined}
        data-start={piece.start} data-end={piece.end} className={`${gap?'reading-gap ':rest?'reading-rest ':''}${playing&&playhead>=piece.start&&playhead<piece.end?'current-chord':''}`}
        disabled={disabled} aria-label={`播放 ${piece.start.toFixed(2)} 秒的 ${piece.symbol??'未標和弦'}`}
        title={`${piece.start.toFixed(3)}–${piece.end.toFixed(3)} 秒${piece.symbol?' · '+piece.symbol:''}`}
        onClick={()=>onSeek(piece.start)}>
        <strong>{gap?'未標和弦':rest?`${piece.symbol} · 休止`:piece.symbol}</strong>
        <small>{timeLabel(piece.start)}–{timeLabel(piece.end)}</small>
      </button><LocatedSongNotes onEdit={onEdit} start={piece.start} end={piece.end} positions={positions} onSeek={onSeek} disabled={disabled}/></div>;
    })}
    {!score.chords.length?<p>目前沒有和弦，仍可播放原曲或還原版本。</p>:null}
  </div>;
}
