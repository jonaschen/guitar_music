import {useEffect,useRef,useState} from 'react';
import type {SongScore} from './types';
import {useSongNotes} from './SongNotes';
import {MelodyNotes} from './MelodyNotes';
import {SongNotePositionEditor} from './SongNotePositionEditor';
import {anchorStatus,type NotePosition} from './songNoteTimeline';
import type {useWorksheet} from './worksheetState';
import {newLine,pastedDocument,encodeDocument,type WorksheetDocument} from './worksheetDocument';

type Track={id:string;language:string;kind:'manual'|'automatic';name:string};
type CaptionPreview={job_id:string;track:Track;lines:Array<{lyric:string;start:number|null;end:number|null}>;message:string};
const languageNames:Record<string,string>={es:'西班牙文',ko:'韓文',zh:'中文',en:'英文',ja:'日文',fr:'法文',de:'德文',pt:'葡萄牙文',it:'義大利文',ru:'俄文',ar:'阿拉伯文',th:'泰文',vi:'越南文',id:'印尼文'};
const trackLabel=(t:Track)=>`${languageNames[t.language.split('-')[0]]??t.language} (${t.language}) · ${t.kind==='manual'?'人工字幕':'自動字幕'} · ${t.name}`;
type EditorProps={positions:NotePosition[];playhead:number;onSeek:(time:number)=>void;disabled:boolean;onEdit:()=>void};
export function LyricsWorksheet(props:EditorProps){
  const notes=useSongNotes();return notes?<WorksheetEditor {...props} {...notes} select={id=>{props.onEdit();notes.select(id);}}/>:null;
}
function WorksheetEditor({job,api,score,sheet,selected,select,editRequest,positions,playhead,onSeek,disabled}:{job:string;api:string;score:SongScore;sheet:ReturnType<typeof useWorksheet>;selected:string|null;editRequest:number;select:(id:string|null)=>void}&EditorProps){
  const [paste,setPaste]=useState(''),[format,setFormat]=useState<'text'|'lrc'>('text');
  const [draft,setDraft]=useState<WorksheetDocument|null>(null),[tracks,setTracks]=useState<Track[]>([]),[selectedTrack,setSelectedTrack]=useState('');
  const [fetching,setFetching]=useState(false),[message,setMessage]=useState('');const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>{request.current?.abort();},[job]);
  const empty=sheet.document.lines.length===0;
  const panel=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{if(selected&&panel.current){panel.current.open=true;requestAnimationFrame(()=>{const element=panel.current?.querySelector<HTMLElement>('[data-selected-note]');element?.scrollIntoView({block:'nearest'});});}},[selected,editRequest]);
  function append(after?:string,notation=''){const row={...newLine(),notation};if(sheet.update({...sheet.document,lines:after?sheet.document.lines.flatMap(line=>line.id===after?[line,row]:[line]):[...sheet.document.lines,row]}))select(row.id);}

  function cancelCaption(){request.current?.abort();setFetching(false);}
  function previewPaste(){cancelCaption();try{setDraft(pastedDocument(paste,format==='lrc'));setMessage('請預覽後加入；不會覆寫已有歌詞或簡譜。');}catch{setMessage('初稿太長或格式不完整，請縮短內容再試。');}}
  function importExisting(){
    cancelCaption();
    const lines=score.lyrics?.lines??[];
    const doc={source:'既有匯入歌詞；時間尚未核對',lines:lines.map(row=>newLine(row.text,row.start??null,row.end??null))};
    try{encodeDocument(doc);setDraft(doc);}catch{setMessage('既有歌詞格式不完整或過長，請貼上所需內容。');return;}
    setMessage('這是既有匯入的歌詞副本；原樂譜及筆記不會改動。');
  }
  async function captions(preview=false){
    request.current?.abort();const controller=new AbortController();request.current=controller;setFetching(true);setMessage('');
    try{
      const response=await fetch(`${api}/api/v1/jobs/${encodeURIComponent(job)}/${preview?'lyric-caption-preview':'lyric-caption-tracks'}`,{
        method:preview?'POST':'GET',headers:preview?{'Content-Type':'application/json'}:undefined,
        body:preview?JSON.stringify({track_id:selectedTrack}):undefined,signal:controller.signal});
      if(!response.ok)throw Error('字幕目前無法取得，可貼上歌詞或匯入LRC。');
      const data=await response.json();if(controller.signal.aborted||data.job_id!==job)return;
      if(preview){
        const result=data as CaptionPreview;
        if(!Array.isArray(result.lines)||result.track?.id!==selectedTrack)throw Error('字幕預覽資料不完整。');
        const doc={source:`影片字幕初稿：${trackLabel(result.track)}；尚未校對`,lines:result.lines.map(row=>newLine(row.lyric,row.start,row.end))};encodeDocument(doc);
        setDraft(doc);setMessage(result.lines.length?'字幕可能不是歌詞，請核對語言與內容後再加入。':'所選字幕在這段歌曲中沒有可用文字，可貼上歌詞。');
      }else{setTracks(Array.isArray(data.tracks)?data.tracks:[]);setSelectedTrack('');setMessage(data.message||'請選擇字幕語言後預覽。');}
    }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:'字幕取得失敗，可改貼上歌詞。');}
    finally{if(request.current===controller)setFetching(false);}
  }
  function applyDraft(){
    if(!draft||!empty||sheet.loading)return;
    if(!sheet.update(draft))return;select(draft.lines[0]?.id??null);setDraft(null);setPaste('');setMessage('已加入工作頁，會自動保存。');
  }
  function viewOnScore(id:string){
    const element=document.querySelector<HTMLElement>(`[data-note-id="${id}"]`);
    if(!element){setMessage('此位置不在目前顯示的譜面範圍；請核對歌曲範圍與來源，再確認定位。');return;}
    if(panel.current)panel.current.open=false;
    requestAnimationFrame(()=>{element.scrollIntoView({block:'center'});element.querySelector<HTMLButtonElement>('.note-text')?.focus({preventScroll:true});});
  }
  function edit(id:string,field:'lyric'|'notation',text:string){sheet.update({...sheet.document,lines:sheet.document.lines.map(row=>row.id===id?{...row,[field]:text}:row)});}
  function remove(id:string){const row=sheet.document.lines.find(r=>r.id===id);if(row&&(row.lyric||row.notation)&&!window.confirm('移除此行及下方簡譜？需要保留時請先下載工作頁備份。'))return;sheet.update({...sheet.document,lines:sheet.document.lines.filter(row=>row.id!==id)});}
  function backup(){const blob=new Blob([sheet.rawDraft],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`lyric-worksheet-${job}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return <details className="lyric-worksheet" ref={panel}><summary>歌曲筆記（歌詞與簡譜）</summary>
    <p>選一組歌詞與簡譜，確認小節或秒數位置後，會顯示在和弦譜下方。點譜面文字可回到同一組編輯。簡譜保留原文字，不會自動演奏或移調；此邀請空間共用。</p>
    {sheet.document.source?<p className="worksheet-source">初稿來源：{sheet.document.source}</p>:null}
    <p role="status" aria-label="歌詞工作頁保存狀態">{sheet.status}</p>
    {empty?<div className="worksheet-import">
      {score.song.source_type==='youtube'?<button type="button" disabled={fetching} onClick={()=>void captions()}>取得影片字幕初稿</button>:null}
      {tracks.length?<><label>字幕語言<select aria-label="字幕語言" value={selectedTrack} onChange={e=>{request.current?.abort();setFetching(false);setSelectedTrack(e.target.value);setDraft(null);}}><option value="">請選擇語言與來源</option>{tracks.map(t=><option key={t.id} value={t.id}>{trackLabel(t)}</option>)}</select></label><button type="button" disabled={!selectedTrack||fetching} onClick={()=>void captions(true)}>預覽所選字幕</button></>:null}
      {score.lyrics?.lines.length?<button type="button" onClick={importExisting}>預覽已匯入歌詞</button>:null}
      <label>貼上歌詞<textarea aria-label="貼上歌詞初稿" rows={5} maxLength={120000} value={paste} onChange={e=>setPaste(e.target.value)}/></label>
      <label>格式<select aria-label="歌詞匯入格式" value={format} onChange={e=>setFormat(e.target.value as 'text'|'lrc')}><option value="text">純文字，每行一句</option><option value="lrc">LRC</option></select></label>
      <label>或匯入文字／LRC檔<input aria-label="匯入歌詞檔" type="file" accept=".txt,.lrc,text/plain" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>512000){setMessage('檔案太大，請貼上所需段落。');return;}const text=await file.text();setPaste(text);setFormat(file.name.toLowerCase().endsWith('.lrc')?'lrc':'text');}}/></label>
      <button type="button" disabled={!paste.trim()} onClick={previewPaste}>預覽貼上內容</button>
    </div>:<p>已有歌詞與簡譜，不會自動套入其他初稿；可逐行修改或新增。</p>}
    {message?<p role="status" aria-label="歌詞初稿狀態">{fetching?'正在取得字幕…':message}</p>:fetching?<p role="status">正在取得字幕…</p>:null}
    {draft?<div className="worksheet-preview" aria-label="歌詞初稿預覽"><p>{draft.source}</p><ol>{draft.lines.map(row=><li key={row.id}>{row.lyric||'（空白行）'}</li>)}</ol>
      <button type="button" disabled={!empty||sheet.loading||!draft.lines.length} onClick={applyDraft}>加入空白工作頁</button><button type="button" onClick={()=>setDraft(null)}>取消初稿</button></div>:null}
    <div className="note-arrangement" aria-label="歌曲筆記安排"><p>未定位／待重新確認 {sheet.document.lines.filter(row=>!row.anchor||anchorStatus(row.anchor,score,positions)).length} 組</p>{sheet.document.lines.map((row,index)=><button type="button" key={row.id} aria-pressed={selected===row.id} onClick={()=>select(row.id)}>{index+1}. {row.lyric||row.notation||'空白組'} · {!row.anchor?'未定位':anchorStatus(row.anchor,score,positions)?'位置待確認':`${row.anchor.time.toFixed(2)} 秒`}</button>)}</div>
    <div className="worksheet-lines">{sheet.document.lines.map((row,index)=>selected===row.id?<section key={row.id} className="worksheet-line" data-line-id={row.id} data-selected-note>
      <label>歌詞 {index+1}<textarea aria-label={`歌詞第${index+1}行`} rows={2} maxLength={2000} disabled={sheet.loading} value={row.lyric} onChange={e=>edit(row.id,'lyric',e.target.value)}/></label>
      <label>手填簡譜<textarea aria-label={`簡譜第${index+1}行`} rows={2} maxLength={2000} disabled={sheet.loading} placeholder="例如：5 6 1' - 0" value={row.notation} onChange={e=>edit(row.id,'notation',e.target.value)}/></label>
      <SongNotePositionEditor key={JSON.stringify(row.anchor)} row={row} score={score} positions={positions} playhead={playhead} onSeek={onSeek} disabled={sheet.loading} playbackDisabled={disabled} onChange={anchor=>sheet.update({...sheet.document,lines:sheet.document.lines.map(line=>line.id===row.id?{...line,anchor}:line)})}/>
      {row.anchor?<button type="button" onClick={()=>viewOnScore(row.id)}>查看譜上位置</button>:null}
      {row.start!==null?<small>來源參考時間 {row.start.toFixed(2)} 秒；未作播放對齊</small>:null}
      <button type="button" disabled={sheet.loading||sheet.document.lines.length>=400} onClick={()=>append(row.id)}>在第{index+1}行下方新增</button>
      <button type="button" disabled={sheet.loading} onClick={()=>remove(row.id)}>移除第{index+1}行</button>
    </section>:null)}</div>
    <button type="button" disabled={sheet.loading||sheet.document.lines.length>=400} onClick={()=>append()}>新增空白行</button>
    <button type="button" disabled={!sheet.dirty||sheet.loading||sheet.saving||!sheet.loaded||sheet.conflict} onClick={()=>void sheet.save()}>立即保存工作頁</button>
    <button type="button" onClick={backup}>下載工作頁備份</button>
    {(!sheet.loaded||sheet.conflict||sheet.invalidDraft)&&!sheet.loading?<button type="button" onClick={()=>{if(!(sheet.conflict||sheet.invalidDraft)||window.confirm('載入最新版本會取代目前草稿，請先下載工作頁備份。'))void sheet.reload();}}>載入最新歌詞工作頁</button>:null}
    <MelodyNotes job={job} api={api} onCopy={text=>{if(!text.trim())return;if(text.length>2000){setMessage('請在舊筆記內選取不超過2000字的一段，再複製到簡譜列。');return;}append(undefined,text);}}/>
  </details>;
}
