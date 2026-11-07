import {useEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode} from 'react';
import {AccompanimentReview, type ReviewMode} from './AccompanimentReview';
import {readingBars,fullNotePositions} from './songNoteTimeline';
import {SongNotesProvider,LocatedSongNotes} from './SongNotes';
import {LyricsWorksheet} from './LyricsWorksheet';
import {ChordTimelinePage} from './ChordTimelinePage';
import {measureLayout} from './measureLayout';

type Props=ComponentProps<typeof AccompanimentReview> & {
  playbackControls?:ReactNode; keyControls?:ReactNode; secondaryActions?:ReactNode; editPanel?:ReactNode; fingeringGuide?:ReactNode;
  speed?:number; onSpeed?:(rate:number)=>void;
};
export function ChordSongPage(props:Props){
  return <SongNotesProvider score={props.score}>{props.score.analysis.timing_status==='unmetered'||!fullNotePositions(props.score,readingBars(props.score)).length ? <ChordTimelinePage {...props}/> : <MeteredChordSongPage {...props}/>}</SongNotesProvider>;
}
function MeteredChordSongPage({score,sourceAvailable,playing,preparing,playhead,guitarVolume,onVolume,onPlay,onStop,onTools,onEditChord,playbackControls,keyControls,secondaryActions,editPanel,fingeringGuide,speed=1,onSpeed}:Props){
  const bars=useMemo(()=>readingBars(score),[score]);
  const positions=useMemo(()=>fullNotePositions(score,bars),[score,bars]);
  const barName=(number:number)=>number===0?'起始片段':`Bar ${number}`;
  const [mode,setMode]=useState<ReviewMode>('mix'),[loop,setLoop]=useState(false),[editing,setEditing]=useState(false);
  const [follow,setFollow]=useState(true);
  const transportRef=useRef<HTMLDivElement>(null),sheetRef=useRef<HTMLDivElement>(null);
  const current=score.chords.find(c=>playhead>=c.start&&playhead<c.end),next=score.chords.find(c=>c.start>playhead);
  useEffect(()=>{
    if(!playing||editing||!follow||!current)return;
    const element=Array.from(sheetRef.current?.querySelectorAll<HTMLButtonElement>('button[data-chord-id]')??[]).find(el=>el.dataset.chordId===current.id&&playhead>=Number(el.dataset.start)&&playhead<Number(el.dataset.end));
    if(!element)return;const rect=element.getBoundingClientRect(),top=transportRef.current?.getBoundingClientRect().bottom??0;
    if(rect.top<top+16||rect.bottom>innerHeight-24)window.scrollBy({top:rect.top-top-16,behavior:'instant'});
  },[playing,editing,follow,current?.id,playhead]);


  const [startIndex,setStartIndex]=useState(0),[count,setCount]=useState(4);
  const index=Math.min(startIndex,Math.max(0,bars.length-1));
  const start=loop ? bars[index]?.start??0 : 0;
  const end=loop ? bars[Math.min(index+count-1,bars.length-1)]?.end??score.song.duration_seconds : score.song.duration_seconds;
  const unavailable=mode!=='guitar' && !sourceAvailable;
  const change=(action:()=>void)=>{onStop();action();};
  const play=(from?:number)=>onPlay(mode,start,end,loop,from);
  const playNote=(from:number)=>{onStop();const within=loop&&from>=start&&from<end;if(!within)setLoop(false);onPlay(mode,within?start:0,within?end:score.song.duration_seconds,within,from);};
  return <section className="song-sheet" aria-label="和弦核對">
    {score.provenance.parameters?.timing_candidate && score.provenance.parameters?.timing_candidate_confirmed !== true ? <p className="sheet-hint" role="note">拍格試驗稿 · 拍子尚待確認；原稿保留，和弦內容與時間未改。</p> : null}
    <div className="timeline-transport" ref={transportRef}><div className="song-controls">
      <button className="primary-action" type="button" disabled={unavailable && !playing && !preparing} onClick={()=>playing||preparing?onStop():play(playhead>=start&&playhead<end?playhead:undefined)}>{preparing?'取消準備':playing?'暫停':'播放'}</button>
      <label>聲音 <select aria-label="播放聲音" value={mode} onChange={e=>change(()=>setMode(e.target.value as ReviewMode))}><option value="mix">原曲＋吉他</option><option value="source">原曲（原調）</option><option value="guitar">吉他</option></select></label>
    </div>
    {playbackControls}
    {playing?<p className="chord-follow-cue" aria-label="跟彈提示">目前 <strong>{current?.symbol??'休止'}</strong><span>接著 {next?.symbol??'結束'}</span></p>:null}
    </div>
    {keyControls?<div className="song-controls key-controls">{keyControls}</div>:null}
    <p className="playback-status" role="status">{preparing?'正在準備聲音…':playing?'播放中':'已暫停'} · {playhead.toFixed(1)} / {score.song.duration_seconds.toFixed(1)} 秒</p>
    {unavailable?<p role="status">{!sourceAvailable?'原曲暫時無法使用，請選「吉他」播放。':'已移調，與原曲音高不同。請選「吉他」，或回到原調合奏。'}</p>:null}
    {!score.key_context.audio_matches_notation?<p role="status">原曲維持原調；吉他使用目前和弦，可能不同調，供聽感核對。</p>:null}
    {fingeringGuide}
    <LyricsWorksheet onEdit={onStop} positions={positions} playhead={playhead} onSeek={playNote} disabled={unavailable||preparing}/>
    <details className="song-options"><summary>練習與編輯</summary>
      <div className="secondary-controls"><label><input type="checkbox" checked={follow} onChange={e=>setFollow(e.target.checked)}/>跟隨播放</label>
        <label><input type="checkbox" checked={loop} onChange={e=>change(()=>setLoop(e.target.checked))}/>循環選取小節</label>
        {loop?<><label>從 <select aria-label="核對起始小節" value={index} onChange={e=>change(()=>setStartIndex(Number(e.target.value)))}>{bars.map((bar,i)=><option key={i} value={i}>{barName(bar.number)}</option>)}</select></label><label>範圍 <select aria-label="核對小節數" value={count} onChange={e=>change(()=>setCount(Number(e.target.value)))}>{[2,4,8].map(n=><option key={n} value={n}>{n} 小節</option>)}</select></label></>:null}
        <label>吉他練習速度 <select aria-label="吉他練習速度" disabled={mode!=='guitar'} value={mode==='guitar'?speed:1} onChange={e=>change(()=>onSpeed?.(Number(e.target.value)))}>{[.5,.75,1,1.25].map(n=><option key={n} value={n}>{n*100}%</option>)}</select></label>
        <button type="button" onClick={()=>change(()=>setEditing(v=>!v))} aria-pressed={editing}>{editing?'完成編輯':'編輯和弦'}</button>
        <button type="button" onClick={()=>{onStop();play(start);}} disabled={unavailable||preparing}>從頭播放</button>
        {secondaryActions}
      </div>
      <p>原曲合奏維持原速；切換「吉他」可調整練習速度。</p>
    </details>
    {!score.provenance.parameters?.chord_grid_candidate ? <p className="sheet-hint">辨識草稿：和弦邊界尚未整理成拍格；精確時值可點選編輯查看。</p> : <p className="sheet-hint">拍格譜 · 開頭與結尾可能因音訊裁切而不足一小節。</p>}
    <p className="sheet-hint">{editing?'編輯模式：點選和弦修改名稱或刪除片段。':'點和弦即可從該處播放。'}</p>
    {editing?editPanel:null}
    <div className="notation-sheet" aria-label="和弦譜" ref={sheetRef}>
      {bars.map(bar=>{
        const layout=measureLayout(score.beats,bar.start,bar.end,score.analysis.bpm);
        const entries=score.chords.filter(c=>c.end>bar.start&&c.start<bar.end);
        const active=playing&&playhead>=bar.start&&playhead<bar.end;
        return <div className={`notation-measure${active?' current-measure':''}`} key={`${bar.number}-${bar.start}`} aria-label={barName(bar.number)}>
          <span className="measure-number">{bar.number===0?'起始':bar.number}</span>
          <div className="measure-chords">{entries.length?entries.map(c=><button key={c.id} type="button" data-chord-id={c.id} data-start={Math.max(c.start,bar.start)} data-end={Math.min(c.end,bar.end)} className={playing&&playhead>=Math.max(c.start,bar.start)&&playhead<Math.min(c.end,bar.end)?'current-chord':''} disabled={!editing&&unavailable} aria-label={`${editing?'編輯':'播放'} ${barName(bar.number)} 的 ${c.symbol}`} title={`${c.symbol} · ${layout.length(Math.max(c.start,bar.start),Math.min(c.end,bar.end))}`} onClick={()=>{
            if(editing){onStop();onEditChord?.(c.id,{start:bar.start,end:bar.end,bar:bar.number});}
            else {const from=Math.max(c.start,bar.start);onStop();if(loop&&(from<start||from>=end))setLoop(false);onPlay(mode,loop&&from>=start&&from<end?start:0,loop&&from>=start&&from<end?end:score.song.duration_seconds,loop&&from>=start&&from<end,from);}
          }}><span>{c.symbol}{c.start<bar.start?<span className="tie-mark" aria-label="延續"> —</span>:null}</span>{score.provenance.parameters?.chord_grid_candidate && entries.length>1 && /^\d+(?:\.5)? 拍$/.test(layout.length(Math.max(c.start,bar.start),Math.min(c.end,bar.end))) ? <small className="chord-duration">{layout.length(Math.max(c.start,bar.start),Math.min(c.end,bar.end))}</small> : null}</button>):<span className="no-chord">—</span>}</div>
          <LocatedSongNotes onEdit={onStop} start={bar.start} end={bar.end} positions={positions} onSeek={playNote} disabled={unavailable||preparing}/>
        </div>;
      })}
    </div>
    <details className="song-diagnostics"><summary>診斷工具</summary><button type="button" onClick={onTools}>伴奏設定與拍長整理</button></details>
  </section>;
}
