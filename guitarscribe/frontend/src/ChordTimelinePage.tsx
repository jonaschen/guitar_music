import {useState, type ComponentProps} from 'react';
import {type ChordSongPage} from './ChordSongPage';
import {type ReviewMode} from './AccompanimentReview';
import './chordTimeline.css';

const stamp=(seconds:number)=>`${Math.floor(seconds/60)}:${(seconds%60).toFixed(1).padStart(4,'0')}`;
/** A seconds-based chord sheet. Never derives measures from rejected timing. */
export function ChordTimelinePage({score,sourceAvailable,playing,preparing,playhead,guitarVolume,onVolume,onPlay,onStop,onEditChord,keyControls,secondaryActions,editPanel,speed=1,onSpeed}:ComponentProps<typeof ChordSongPage>){
  const [mode,setMode]=useState<ReviewMode>('mix'),[editing,setEditing]=useState(false);
  const [loop,setLoop]=useState(false),[start,setStart]=useState('0'),[end,setEnd]=useState(String(score.song.duration_seconds));
  const duration=score.song.duration_seconds;
  const valid=start.trim()!==''&&end.trim()!==''&&Number(start)>=0&&Number(start)<Number(end)&&Number(end)<=duration;
  const rangeStart=loop?Number(start):0,rangeEnd=loop?Number(end):duration;
  const unavailable=mode!=='guitar'&&(!sourceAvailable||mode==='mix'&&!score.key_context.audio_matches_notation);
  const change=(fn:()=>void)=>{onStop();fn();};
  const play=(from?:number)=>onPlay(mode,rangeStart,rangeEnd,loop,from);
  return <section className="song-sheet" aria-label="和弦核對">
    <div className="song-controls">
      <button className="primary-action" type="button" disabled={!playing&&!preparing&&(unavailable||loop&&!valid)} onClick={()=>playing||preparing?onStop():play(playhead>=rangeStart&&playhead<rangeEnd?playhead:undefined)}>{preparing?'取消準備':playing?'暫停':'播放'}</button>
      <label>聲音 <select aria-label="播放聲音" value={mode} onChange={e=>change(()=>setMode(e.target.value as ReviewMode))}><option value="mix">原曲＋吉他</option><option value="source">原曲</option><option value="guitar">吉他</option></select></label>
      {keyControls}
    </div>
    <p className="playback-status" role="status">{preparing?'正在準備聲音…':playing?'播放中':'已暫停'} · {stamp(playhead)} / {stamp(duration)}</p>
    {unavailable?<p role="status">{!sourceAvailable?'原曲暫時無法使用，請選「吉他」播放。':'已移調，請選「吉他」，或回到原調合奏。'}</p>:null}
    <p className="sheet-hint">和弦時間表 · 拍格尚未確認，依實際秒數排列；吉他在每次換和弦時彈一下。</p>
    <details className="song-options"><summary>練習與編輯</summary>
      <div className="secondary-controls">
        <label><input type="checkbox" checked={loop} onChange={e=>change(()=>setLoop(e.target.checked))}/>循環選取時間</label>
        {loop?<><label>從（秒）<input type="number" min="0" step="0.1" value={start} onChange={e=>change(()=>setStart(e.target.value))}/></label><label>到（秒）<input type="number" min="0" step="0.1" max={duration} value={end} onChange={e=>change(()=>setEnd(e.target.value))}/></label></>:null}
        <label>吉他練習速度 <select aria-label="吉他練習速度" disabled={mode!=='guitar'} value={mode==='guitar'?speed:1} onChange={e=>change(()=>onSpeed?.(Number(e.target.value)))}>{[.5,.75,1,1.25].map(n=><option key={n} value={n}>{n*100}%</option>)}</select></label>
        <label>吉他音量 <input aria-label="核對吉他音量" type="range" min="0" max="1" step=".01" value={guitarVolume} onChange={e=>change(()=>onVolume(Number(e.target.value)))}/></label>
        <button type="button" onClick={()=>change(()=>setEditing(v=>!v))} aria-pressed={editing}>{editing?'完成編輯':'編輯和弦'}</button>
        <button type="button" disabled={unavailable||preparing||loop&&!valid} onClick={()=>{onStop();play(rangeStart);}}>從頭播放</button>
        {secondaryActions}
      </div>
      {loop&&!valid?<p role="alert">請填入歌曲範圍內的起訖秒數，結束須晚於開始。</p>:null}
      <p>原曲合奏維持原速；切換「吉他」可調整練習速度。</p>
    </details>
    <p className="sheet-hint">{editing?'點和弦修改名稱、時間或刪除；修改會自動保存。':'點和弦即可從該處播放。'}</p>
    {editing?editPanel:null}
    <div className="chord-timeline" aria-label="和弦時間表">
      {score.chords.map(c=><button type="button" key={c.id} className={playing&&playhead>=c.start&&playhead<c.end?'current-chord':''} aria-label={`${editing?'編輯':'播放'} ${c.start.toFixed(2)} 秒的 ${c.symbol}`} disabled={!editing&&unavailable} title={`${c.start.toFixed(2)}–${c.end.toFixed(2)} 秒`} onClick={()=>{
        onStop();
        if(editing)onEditChord?.(c.id);
        else {const within=loop&&valid&&c.start>=rangeStart&&c.start<rangeEnd;if(!within)setLoop(false);onPlay(mode,within?rangeStart:0,within?rangeEnd:duration,within,c.start);}
      }}><small>{stamp(c.start)}</small><strong>{c.symbol}</strong><span>{(c.end-c.start).toFixed(2)} 秒</span></button>)}
      {!score.chords.length?<p>目前沒有和弦，仍可播放原曲或還原版本。</p>:null}
    </div>
  </section>;
}
