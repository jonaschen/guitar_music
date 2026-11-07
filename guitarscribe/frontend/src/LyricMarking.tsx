import {useEffect,useRef,useState,type ReactNode} from 'react';
import type {useWorksheet} from './worksheetState';
import {markLyric,undoLyricMark,type MarkFrame,type MarkUndo} from './lyricMarking';
export function LyricMarking({sheet,frame,selected,select,playing,preparing,sourceAvailable,canMark,readTime,onToggle,onReplay,children,footer}:{sheet:ReturnType<typeof useWorksheet>;frame:MarkFrame;selected:string|null;select:(id:string)=>void;playing:boolean;preparing:boolean;sourceAvailable:boolean;canMark:boolean;readTime:()=>number;onToggle:()=>void;onReplay:(time:number)=>void;children?:ReactNode;footer?:ReactNode}){
  const [history,setHistory]=useState<MarkUndo[]>([]),[message,setMessage]=useState(''),[cooling,setCooling]=useState(false);const lastTap=useRef(-Infinity),timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const lines=sheet.document.lines,index=lines.findIndex(r=>r.id===selected),current=lines[index];
  const next=lines.slice(index+1).find(r=>r.lyric.trim()&&!r.anchor);
  useEffect(()=>{setHistory([]);setMessage('');setCooling(false);lastTap.current=-Infinity;return()=>clearTimeout(timer.current);},[frame.duration_seconds,frame.source_start_seconds]);
  useEffect(()=>{if(index<0){const first=lines.find(r=>r.lyric.trim()&&!r.anchor)??lines.find(r=>r.lyric.trim());if(first)select(first.id);}},[selected,index,lines.length]);
  function mark(){
    if(!playing||preparing||!canMark||!current||sheet.loading||sheet.conflict)return;
    // Wall time only debounces accidental double taps; the anchor uses the audio clock.
    if(performance.now()-lastTap.current<350)return;
    try{
      const result=markLyric(sheet.document,current.id,readTime(),frame);
      if(!sheet.update(result.document))return;
      lastTap.current=performance.now();setCooling(true);timer.current=setTimeout(()=>setCooling(false),350);
      setHistory(stack=>[...stack,result.undo]);if(next)select(next.id);
      setMessage(next?'': '這一輪已到最後一句，可回上一句檢查。');
    }catch(error){setMessage(error instanceof Error?error.message:'這次未標記，文字仍保留。');}
  }
  function undo(){const last=history.at(-1);if(!last)return;try{if(sheet.update(undoLyricMark(sheet.document,last))){setHistory(stack=>stack.slice(0,-1));select(last.id);setMessage('已撤銷這次標記，歌詞與簡譜保留。');}}catch(error){setMessage((error as Error).message);}}
  function previous(){const row=lines.slice(0,index).filter(r=>r.lyric.trim()).at(-1);if(!row)return;select(row.id);if(row.anchor&&row.anchor.duration_seconds===frame.duration_seconds&&row.anchor.source_start_seconds===frame.source_start_seconds)onReplay(row.anchor.time);}
  return <section className="lyric-marking" aria-label="邊聽邊標記" data-selected-note>
    <p className="marking-current" aria-live="polite">這句 {index>=0?`${index+1} / ${lines.length}`:''}：<strong>{current?.lyric||'（空白／非歌詞行，可略過）'}</strong></p>
    {children}
    <div className="marking-primary"><button type="button" disabled={!sourceAvailable} onClick={onToggle}>{preparing?'取消準備原曲':playing&&canMark?'暫停原曲':'播放原曲'}</button>
      <button type="button" className="primary-action" disabled={!playing||preparing||!canMark||!current?.lyric.trim()||!!current.anchor||sheet.loading||!sheet.loaded||sheet.conflict||cooling} onKeyDown={event=>{if(event.repeat)event.preventDefault();}} onClick={mark}>這句從這裡開始</button></div>
    <p className="marking-next">下一句：{next?.lyric??'沒有其他未標記歌詞'}</p>
    <div className="marking-secondary"><button type="button" disabled={!lines.slice(0,index).some(r=>r.lyric.trim())} onClick={previous}>回上一句</button><button type="button" disabled={!next} onClick={()=>{if(next)select(next.id);}}>略過這句</button><button type="button" disabled={!history.length||sheet.loading||sheet.conflict} onClick={undo}>撤銷上次標記</button></div>
    {footer}
    {!sourceAvailable?<p role="status">原曲目前無法使用，仍可直接填簡譜；恢復原曲後再聽歌標記。</p>:current?.anchor?<p role="status">這句已有位置，已保留。可略過或到微調修改。</p>:playing&&!canMark?<p role="status">請播放原曲後標記。</p>:null}
    {message?<p role="status" aria-label="歌詞標記狀態">{message}</p>:null}
  </section>;
}
