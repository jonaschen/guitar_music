import {LyricsWorksheet} from './LyricsWorksheet';
import {LocatedSongNotes,useSongNotes} from './SongNotes';
import {localNotePositions,chordTimePieces} from './songNoteTimeline';
import {ContinuousChordReading} from './ContinuousChordReading';
import {useEffect, useRef, useState, type ComponentProps} from 'react';
import {type ChordSongPage} from './ChordSongPage';
import {type ReviewMode} from './AccompanimentReview';
import {PartialTimingSheet,useTimingPreview} from './PartialTimingSheet';
import './chordTimeline.css';
import {sourceJobId} from './scoreVersion';

const stamp=(seconds:number)=>`${Math.floor(seconds/60)}:${(seconds%60).toFixed(1).padStart(4,'0')}`;
/** A seconds-based chord sheet. Never derives measures from rejected timing. */
export function ChordTimelinePage({score,sourceAvailable,playing,preparing,playhead,guitarVolume,onVolume,onPlay,onStop,onEditChord,playbackControls,keyControls,secondaryActions,editPanel,fingeringGuide,speed=1,onSpeed,readPlaybackTime}:ComponentProps<typeof ChordSongPage>){
  const notes=useSongNotes();
  const [mode,setMode]=useState<ReviewMode>(score.song.source_type==='example'?'guitar':'mix'),[editing,setEditing]=useState(false);
  const [loop,setLoop]=useState(false),[start,setStart]=useState('0'),[end,setEnd]=useState(String(score.song.duration_seconds));
  const [follow,setFollow]=useState(true);

  const preview=useTimingPreview(score);
  const positions=localNotePositions(preview);
  const timingView=new URLSearchParams(window.location.search).get('timingView');
  const candidatePath=/^\/reading-candidate-[^/]+(?:\/|$)/.test(window.location.pathname);
  const automaticReading=candidatePath||timingView==='auto';
  const autoPreview=timingView==='auto'||candidatePath&&timingView===null;
  const viewKey=`${sourceJobId(score)}:${score.song.duration_seconds}:${score.song.source_start_seconds??0}`;
  const [viewChoice,setViewChoice]=useState<{key:string;preview:boolean}|null>(null);
  const showPreview=viewChoice?.key===viewKey?viewChoice.preview:autoPreview||timingView==='partial';
  const setShowPreview=(preview:boolean)=>setViewChoice({key:viewKey,preview});
  useEffect(()=>{if(autoPreview)setEditing(false);},[autoPreview,viewKey]);
  const hasPreview=!!preview?.regions.length;
  const previewVisible=showPreview&&hasPreview&&!editing;
  const compactVisible=automaticReading&&showPreview&&!hasPreview&&!editing;
  const sheetRef=useRef<HTMLDivElement>(null),transportRef=useRef<HTMLDivElement>(null);
  const current=score.chords.find(c=>playhead>=c.start&&playhead<c.end);
  const next=score.chords.find(c=>c.start>playhead);
  useEffect(()=>{
    if(!playing||editing||!follow||notes?.marking)return;
    const element=Array.from(sheetRef.current?.querySelectorAll<HTMLButtonElement>('button')??[]).find(el=>(current?el.dataset.chordId===current.id:el.dataset.gap==='true')&&(!el.dataset.start||playhead>=Number(el.dataset.start)&&playhead<Number(el.dataset.end)));
    if(!element)return;
    const rect=element.getBoundingClientRect(),top=transportRef.current?.getBoundingClientRect().bottom??0;
    if(rect.top<top+16||rect.bottom>window.innerHeight-24)window.scrollBy({top:rect.top-top-16,behavior:'instant'});
  },[current?.id,playing,editing,follow,previewVisible,compactVisible,playhead,notes?.marking]);
  const duration=score.song.duration_seconds;
  const valid=start.trim()!==''&&end.trim()!==''&&Number(start)>=0&&Number(start)<Number(end)&&Number(end)<=duration;
  const rangeStart=loop?Number(start):(score.song.source_type==='example'?score.chords[0]?.start??0:0),rangeEnd=loop?Number(end):duration;
  const unavailable=mode!=='guitar'&&!sourceAvailable;
  const change=(fn:()=>void)=>{onStop();fn();};
  const play=(from?:number)=>onPlay(mode,rangeStart,rangeEnd,loop,from);
  const playNote=(from:number)=>{onStop();const within=loop&&valid&&from>=rangeStart&&from<rangeEnd;if(!within)setLoop(false);onPlay(mode,within?rangeStart:0,within?rangeEnd:duration,within,from);};
  const toggleMarking=()=>{if(preparing||playing&&mode!=='guitar'){onStop();return;}const targetMode='source' as const;setMode('source');const from=readPlaybackTime?.()??playhead;onPlay(targetMode,0,duration,false,from>=duration?0:from);};
  const replayMarking=(from:number)=>{const targetMode='source' as const;setMode('source');onStop();onPlay(targetMode,0,score.song.duration_seconds,false,from);};
  return <section className="song-sheet" aria-label="和弦核對">
    <div className="timeline-transport" style={notes?.marking?{position:'static'}:undefined} ref={transportRef}><div className="song-controls">
      <button className="primary-action" type="button" disabled={!playing&&!preparing&&(unavailable||loop&&!valid)} onClick={()=>playing||preparing?onStop():play(playhead>=rangeStart&&playhead<rangeEnd?playhead:undefined)}>{preparing?'取消準備':playing?'暫停':'播放'}</button>
      <label>聲音 <select aria-label="播放聲音" value={mode} onChange={e=>change(()=>setMode(e.target.value as ReviewMode))}><option value="mix">原曲＋吉他</option><option value="source">原曲（原調）</option><option value="guitar">吉他</option></select></label>
    </div>
    {playbackControls}
    {playing?<p className="chord-follow-cue" aria-label="跟彈提示">目前 <strong>{current?.symbol??(compactVisible?'未標和弦':'休止')}</strong><span>接著 {next?.symbol??'結束'}</span></p>:null}
    </div>
    {keyControls?<div className="song-controls key-controls">{keyControls}</div>:null}
    <p className="playback-status" role="status">{preparing?'正在準備聲音…':playing?'播放中':'已暫停'} · {stamp(playhead)} / {stamp(duration)}</p>
    {unavailable?<p role="status">{!sourceAvailable?'原曲暫時無法使用，請選「吉他」播放。':'已移調，請選「吉他」，或回到原調合奏。'}</p>:null}
    {!score.key_context.audio_matches_notation?<p role="status">原曲維持原調；吉他使用目前和弦，可能不同調，供聽感核對。</p>:null}
    {automaticReading?<div className="reading-view-controls" role="group" aria-label="讀譜方式">
      <button type="button" aria-pressed={previewVisible||compactVisible} disabled={editing} onClick={()=>setShowPreview(true)}>{hasPreview?'局部譜 · 待確認':'連續和弦 · 待確認'}</button>
      <button type="button" aria-pressed={!previewVisible&&!compactVisible} disabled={editing} onClick={()=>setShowPreview(false)}>時間明細</button>
      <small>{hasPreview?`${Math.round(preview!.covered_seconds)} 秒小節草稿`:'小節位置未確認'}</small>
    </div>:null}
    <p className="sheet-hint">{compactVisible?'小節未確認；和弦依偵測時間連續排列，長短以時間為準。':previewVisible?(automaticReading?'小節草稿待確認；未知段按時間排列。看譜方式不改變聲音。':'小節草稿尚待確認；不確定處按時間顯示，各段重新編號。'):editing&&automaticReading?'正在時間明細編輯；完成後返回原閱讀方式。':'這首歌的小節位置尚未確認，先顯示和弦時間表。每列是一段和弦，不是一小節；撥奏依播放器選項。'}</p>
    {hasPreview&&!automaticReading?<label className="partial-preview-toggle"><input type="checkbox" checked={showPreview} onChange={e=>setShowPreview(e.target.checked)}/>預覽可辨識的小節（{Math.round(preview!.covered_seconds)} 秒）</label>:null}
    {previewVisible&&!automaticReading?<p className="sheet-hint">切換看譜方式不改變聲音；撥奏依播放器選項。編輯時回到時間表。</p>:null}
    {fingeringGuide}
    <LyricsWorksheet playing={playing} preparing={preparing} sourceAvailable={sourceAvailable} canMark={sourceAvailable&&mode!=='guitar'} readTime={readPlaybackTime??(()=>playhead)} onToggleMarking={toggleMarking} onReplayMarking={replayMarking} onEdit={onStop} positions={positions} playhead={playhead} onSeek={playNote} disabled={unavailable||preparing}/>
    <details className="song-options"><summary>練習與編輯</summary>
      <div className="secondary-controls">
        <label><input type="checkbox" checked={follow} onChange={e=>setFollow(e.target.checked)}/>跟隨播放位置</label>
        <label><input type="checkbox" checked={loop} onChange={e=>change(()=>setLoop(e.target.checked))}/>循環選取時間</label>
        {loop?<><label>從（秒）<input type="number" min="0" step="0.1" value={start} onChange={e=>change(()=>setStart(e.target.value))}/></label><label>到（秒）<input type="number" min="0" step="0.1" max={duration} value={end} onChange={e=>change(()=>setEnd(e.target.value))}/></label></>:null}
        <label>吉他練習速度 <select aria-label="吉他練習速度" disabled={mode!=='guitar'} value={mode==='guitar'?speed:1} onChange={e=>change(()=>onSpeed?.(Number(e.target.value)))}>{[.5,.75,1,1.25].map(n=><option key={n} value={n}>{n*100}%</option>)}</select></label>
        <button type="button" onClick={()=>change(()=>setEditing(v=>!v))} aria-pressed={editing}>{editing?'完成編輯':automaticReading?'到時間表編輯':'編輯和弦'}</button>
        <button type="button" disabled={unavailable||preparing||loop&&!valid} onClick={()=>{onStop();play(rangeStart);}}>從頭播放</button>
        {secondaryActions}
      </div>
      {loop&&!valid?<p role="alert">請填入歌曲範圍內的起訖秒數，結束須晚於開始。</p>:null}
      <p>原曲合奏維持原速；切換「吉他」可調整練習速度。</p>
    </details>
    <p className="sheet-hint">{editing?'點和弦修改名稱、時間或刪除；修改會自動保存。':'點和弦即可從該處播放。'}</p>
    {editing?editPanel:null}
    <div ref={sheetRef}>
    {compactVisible?<ContinuousChordReading onEdit={onStop} positions={positions} score={score} playing={playing} playhead={playhead} disabled={unavailable} onSeek={from=>{
      onStop();const within=loop&&valid&&from>=rangeStart&&from<rangeEnd;
      if(!within)setLoop(false);onPlay(mode,within?rangeStart:0,within?rangeEnd:duration,within,from);
    }}/>:previewVisible?<PartialTimingSheet onEdit={onStop} positions={positions} score={score} preview={preview!} playing={playing} playhead={playhead} disabled={unavailable} onSeek={from=>{
      onStop();const within=loop&&valid&&from>=rangeStart&&from<rangeEnd;
      if(!within)setLoop(false);onPlay(mode,within?rangeStart:0,within?rangeEnd:duration,within,from);
    }}/>:<>
    <div className="timeline-columns" aria-hidden="true"><span>時間範圍</span><span>和弦</span><span>長度</span></div>
    <div className="chord-timeline" aria-label="和弦時間表">
      {chordTimePieces(score).map((piece,i)=>{const c=piece.chord;return <div key={c?.id??`gap-${i}`}>{c?<button type="button" data-chord-id={c.id} className={playing&&playhead>=c.start&&playhead<c.end?'current-chord':''} aria-label={`${editing?'編輯':'播放'} ${c.start.toFixed(2)} 秒的 ${c.symbol}`} disabled={!editing&&unavailable} title={`${c.start.toFixed(2)}–${c.end.toFixed(2)} 秒`} onClick={()=>{
        onStop();
        if(editing)onEditChord?.(c.id);
        else {const within=loop&&valid&&c.start>=rangeStart&&c.start<rangeEnd;if(!within)setLoop(false);onPlay(mode,within?rangeStart:0,within?rangeEnd:duration,within,c.start);}
      }}><small>{stamp(c.start)}–{stamp(c.end)}</small><strong>{c.symbol}</strong><span>{(c.end-c.start).toFixed(2)} 秒</span></button>:null}<LocatedSongNotes onEdit={onStop} start={piece.start} end={piece.end} positions={positions} onSeek={playNote} disabled={unavailable||preparing}/></div>;})}
      {!score.chords.length?<p>目前沒有和弦，仍可播放原曲或還原版本。</p>:null}
    </div>
    </>}
    </div>
  </section>;
}
