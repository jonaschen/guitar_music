import {useEffect, useRef, useState, type CSSProperties, type PointerEvent} from 'react';
import {ROOT_NAMES, rootStamp, type RootDocument} from './rootPracticeDocument';
import {rootGridBeats, type RootGrid} from './rootPracticeGrid';
import {SPECTRUM_RATE, SPECTRUM_LOW_MIDI, SPECTRUM_HIGH_MIDI, spectrumColor, type SpectrumData} from './rootSpectrum';
import './rootSpectrogram.css';

type Chord = {start: number; end: number; symbol: string};
type Range = {start: number; end: number};
type Props = {
  document: RootDocument; api: string; audioUrl?:string; initialOpen?:boolean; presentation?:boolean; focusRange?:Range; workingChords?:Array<Range&{symbol:string|null}>; position: number; playing: boolean; range: Range; grid: RootGrid | null;
  onSeek: (time: number) => void; onRange: (start: number, end: number) => void;
  onPlay: (start: number, end: number) => void; onPause: () => void;
  onUseSelectedRange: () => void; selectedId: string; playbackControls: boolean;
};
const noteName = (midi: number) => ROOT_NAMES[((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

export function RootSpectrogram({document: doc, api, audioUrl, initialOpen, presentation=false, focusRange, workingChords, position, playing, range, grid, onSeek, onRange, onPlay, onPause, onUseSelectedRange, selectedId, playbackControls}: Props) {
  const minTime=focusRange?.start??0,maxTime=focusRange?.end??doc.source.duration;
  const [dataOffset,setDataOffset]=useState(minTime);
  const [open, setOpen] = useState(() => initialOpen??new URLSearchParams(location.search).get('visual') === '1');
  const [data, setData] = useState<SpectrumData | null>(null), [chords, setChords] = useState<Chord[]>([]);
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle'), [message, setMessage] = useState('');
  const [view, setView] = useState<Range>({start: minTime, end: focusRange?maxTime:Math.min(30, maxTime)});
  const [heightScale, setHeightScale] = useState(() => {try {const value = Number(sessionStorage.getItem('guitarscribe.spectrum-height')); return [1,2,3,4].includes(value) ? value : 2;} catch {return 2;}});
  const [rangeMessage, setRangeMessage] = useState('');
  const [contrast, setContrast] = useState(60), [dragRange, setDragRange] = useState<Range | null>(null);
  const [probe, setProbe] = useState<{time: number; midi: number} | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null), worker = useRef<Worker | null>(null), controller = useRef<AbortController | null>(null);
  const generation = useRef(0), drag = useRef<{time: number; x: number; pointer: number} | null>(null);
  const length = view.end - view.start, left = (t: number) => (t - view.start) / length * 100;
  const rangeValid = Number.isFinite(range.start + range.end) && range.start >= minTime && range.end <= maxTime && range.end - range.start >= .08;
  const shownRange = dragRange ?? (rangeValid ? range : null);
  const percent = (a: number, b: number) => ({left: `${left(Math.max(view.start, a))}%`, width: `${(Math.min(view.end, b) - Math.max(view.start, a)) / length * 100}%`});

  function cancel() {
    generation.current++; controller.current?.abort(); controller.current = null;
    worker.current?.terminate(); worker.current = null;
  }
  useEffect(() => () => cancel(), []);
  useEffect(() => {
    cancel(); setRangeMessage(''); setData(null); setChords([]); setState('idle'); setMessage('');
    setView({start: minTime, end: focusRange?maxTime:Math.min(30, maxTime)});
  }, [doc.source.fingerprint,minTime,maxTime]);
  useEffect(() => {
    const selected = doc.segments.find(s => s.id === selectedId);
    if (!selected) return;
    const focus = position >= selected.start && position < selected.end ? position : selected.start;
    setView(old => {
      if (focus >= old.start && focus < old.end) return old;
      const width = old.end - old.start, start = Math.max(minTime, Math.min(focus, maxTime - width));
      return {start, end: start + width};
    });
  }, [selectedId, doc.source.fingerprint,minTime,maxTime]);

  async function generate() {
    cancel(); const ticket = generation.current, abort = new AbortController(); controller.current = abort;
    setState('loading'); setMessage('正在讀取原曲…');
    const endpoint = `${api}/api/v1/jobs/${encodeURIComponent(doc.source.job_id)}`;
    async function readOriginal() {
      try {
        const response = await fetch(endpoint, {signal: abort.signal});
        if (!response.ok) return null;
        const job = await response.json(), score = job?.score;
        if (job?.id !== doc.source.job_id || !score?.song || !Array.isArray(score.chords) || !score.provenance ||
          !Number.isFinite(score.song.duration_seconds) || !Number.isFinite(score.song.source_start_seconds) ||
          Math.abs(score.song.duration_seconds - doc.source.duration) > .000001 ||
          Math.abs(score.song.source_start_seconds - doc.source.source_start) > .000001) return null;
        return {identity: JSON.stringify([job.id, score.song, score.chords, score.provenance]), chords: score.chords as Chord[]};
      } catch { return null; }
    }
    try {
      if (doc.source.duration > 1200) throw Error('這個視圖支援 20 分鐘內的歌曲；請先分析較短片段，或用 Sonic Visualiser 看長錄音。');
      // Bracket the fingerprint-checked audio request with original-score snapshots.
      // A changed source or unavailable snapshot suppresses the chord layer.
      const original = await readOriginal();
      if (ticket !== generation.current) return;
      const response = await fetch(audioUrl??`${endpoint}/root-practice/audio?fingerprint=${doc.source.fingerprint}`, {signal: abort.signal});
      if (!response.ok) throw Error(response.status === 409 ? '來源已變動，請重新開啟這首歌。' : '原曲音訊目前無法取得；仍可查看下方根音工作稿。');
      if (Number(response.headers.get('Content-Length')) > 160_000_000) throw Error('音檔太大，請先分析較短片段。');
      const bytes = await response.arrayBuffer();
      if (ticket !== generation.current) return;
      if (bytes.byteLength > 160_000_000) throw Error('音檔太大，請先分析較短片段。');
      setMessage('正在準備低頻音訊…');
      const decoder = new OfflineAudioContext(2, 1, SPECTRUM_RATE);
      const buffer = await decoder.decodeAudioData(bytes);
      if (ticket !== generation.current) return;
      if (Math.abs(buffer.duration - doc.source.duration) > .15) throw Error('音訊長度與工作稿不符，請重新載入歌曲。');
      // Fetch the ORIGINAL score. Never label a transposed/edited work score as audio evidence.
      const current = await readOriginal();
      if (ticket !== generation.current) return;
      let chordMessage = '';
      if (original && current && original.identity === current.identity) {
        setChords(current.chords.filter(c => c && typeof c.symbol === 'string' && Number.isFinite(c.start + c.end) && c.start >= 0 && c.end > c.start && c.end <= doc.source.duration + .01));
      } else { setChords([]); chordMessage = ' 原分析來源無法核對，已隱藏和弦層。'; }
      if (ticket !== generation.current) return;
      const first=Math.floor(minTime*buffer.sampleRate),last=Math.min(buffer.length,Math.ceil(maxTime*buffer.sampleRate));
      const channels = Array.from({length: Math.min(2, buffer.numberOfChannels)}, (_, i) => buffer.getChannelData(i).slice(first,last));
      const task = new Worker(new URL('./rootSpectrum.worker.ts', import.meta.url), {type: 'module'}); worker.current = task;
      task.onmessage = event => {
        if (ticket !== generation.current) return;
        if (event.data.error) { setState('error'); setMessage('頻譜計算失敗，請重試。'); task.terminate(); worker.current = null; }
        else if (event.data.result) {
          setDataOffset(first/buffer.sampleRate); setData(event.data.result); setState('ready'); setMessage('低頻圖已就緒。' + chordMessage); task.terminate(); worker.current = null;
        } else setMessage(`正在繪製低頻圖… ${Math.round(event.data.progress * 100)}%`);
      };
      task.onerror = () => { if (ticket === generation.current) { setState('error'); setMessage('頻譜計算中斷，請重試。'); task.terminate(); worker.current = null; } };
      task.postMessage({channels, rate: buffer.sampleRate}, channels.map(c => c.buffer));
    } catch (error) {
      if (ticket !== generation.current) return;
      setState('error'); setMessage(error instanceof Error ? error.message : '無法讀取音訊，請重試。');
    }
  }

  useEffect(() => {
    if (!data || !canvas.current || !open) return;
    const ctx = canvas.current.getContext('2d'); if (!ctx) return;
    const source = window.document.createElement('canvas'); source.width = data.columns; source.height = data.rows;
    const off = source.getContext('2d')!; const bitmap = off.createImageData(data.columns, data.rows);
    for (let x = 0; x < data.columns; x++) for (let y = 0; y < data.rows; y++) {
      const color = spectrumColor(data.values[x * data.rows + y], data.peak, contrast), pixel = (y * data.columns + x) * 4;
      bitmap.data.set([...color, 255], pixel);
    }
    off.putImageData(bitmap, 0, 0);
    ctx.fillStyle = '#142440'; ctx.fillRect(0, 0, 1400, 360);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(source, (view.start-dataOffset) * data.rate / data.hop, 0, length * data.rate / data.hop, data.rows, 0, 0, 1400, 360);
  }, [data, dataOffset, contrast, view.start, view.end, open]);

  function zoom(seconds: number, center = position) {
    const width = Math.min(maxTime-minTime, Math.max(.1, seconds));
    const start = clamp(center - width / 2, minTime, Math.max(minTime, maxTime - width));
    setView({start, end: start + width});
  }
  function markRange(side: 'start' | 'end') {
    if (side === 'start') {
      if (position > maxTime - .08) return;
      const end = rangeValid && range.end - position >= .08 ? range.end : maxTime;
      onRange(position, end);
      setRangeMessage(`已設 A 開始 ${rootStamp(position)}${end !== range.end ? focusRange?'；B 暫設本段結尾，再選結束位置。':'；B 暫設歌曲結尾，再點結束位置設定 B。' : '；接著點圖選結束位置，再設定 B。'}`);
    } else {
      if (position < minTime + .08) return;
      const start = rangeValid && position - range.start >= .08 ? range.start : minTime;
      onRange(start, position);
      setRangeMessage(`已設 B 結束 ${rootStamp(position)}${start !== range.start ? focusRange?'；A 暫設本段開頭，可再設定 A。':'；A 暫設歌曲開頭，可再設定 A。' : '；按「播放原曲範圍」回聽。'}`);
    }
  }
  function point(event: PointerEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    return {time: clamp(view.start + (event.clientX - box.left) / box.width * length, view.start, view.end),
      midi: Math.round(SPECTRUM_HIGH_MIDI - clamp((event.clientY - box.top) / box.height, 0, 1) * (SPECTRUM_HIGH_MIDI - SPECTRUM_LOW_MIDI))};
  }
  const visibleChords = chords.filter(c => c.start < view.end && c.end > view.start);
  const visibleRoots = doc.segments.filter(s => s.start < view.end && s.end > view.start);
  const beats = grid && length < 90 ? rootGridBeats(grid, view.start, view.end) : [];
  const ticks = Array.from({length: 5}, (_, i) => view.start + length * i / 4);
  const currentChord = chords.find(c => position >= c.start && position < c.end);
  const currentRoot = doc.segments.find(s => position >= s.start && position < s.end);
  const cursor = position >= view.start && position <= view.end ? <i className="rs-cursor" style={{left: `${left(position)}%`}}/> : null;

  return <section className="root-spectrum" aria-label="低頻與和聲視覺化" style={{'--rs-height-scale': heightScale} as CSSProperties}>
    <div className="rs-heading"><div><h2>看著音樂抓行進</h2><p>低頻的亮線、和弦的變化，和你自己的判斷。</p></div><button aria-expanded={open} onClick={() => setOpen(!open)}>{open ? '收起視覺化' : '開啟視覺化'}</button></div>
    {open && <>
      <p className="rs-explain">上圖看頻率能量，下圖看和聲判斷。亮線可能是基音、泛音或鼓聲，不會自動變成根音答案。</p>
      <div className="rs-actions">
        {state !== 'loading' ? <button className="root-primary" onClick={() => void generate()}>{data ? '重新產生低頻圖' : '產生低頻圖'}</button> : <button onClick={() => {cancel(); setState(data ? 'ready' : 'idle'); setMessage('已取消，工作稿未變更。');}}>取消產生</button>}
        <span role="status" aria-label="頻譜狀態">{message || '音訊只在此瀏覽器繪圖，不上傳到其他服務。'}</span>
      </div>
      <div className="rs-actions" aria-label="圖表縮放">
        <button onClick={() => zoom(10)}>看 10 秒</button><button onClick={() => zoom(30)}>看 30 秒</button><button onClick={() => zoom(60)}>看 60 秒</button><button onClick={() => zoom(120)}>看 120 秒</button><button onClick={() => setView({start: minTime, end: maxTime})}>{focusRange?'看整段':'看全曲'}</button>
        <button disabled={!rangeValid} onClick={() => setView({start: range.start, end: range.end})}>放大 A–B</button>
        <button disabled={view.start <= minTime} onClick={() => zoom(length, (view.start + view.end) / 2 - length * .8)}>往前看</button><button disabled={view.end >= maxTime} onClick={() => zoom(length, (view.start + view.end) / 2 + length * .8)}>往後看</button>
      </div>
      <label className="rs-size">圖的高度 <select aria-label="頻譜高度" value={heightScale} onChange={e => {const value = Number(e.target.value); setHeightScale(value); try {sessionStorage.setItem('guitarscribe.spectrum-height', String(value));} catch {}}}>
        <option value="1">1 倍（精簡）</option><option value="2">2 倍</option><option value="3">3 倍</option><option value="4">4 倍</option>
      </select></label>
      <div className="rs-range-guide" role="group" aria-label="設定反覆練習範圍">
        <strong>A 是開始，B 是結束：只反覆聽兩點之間。</strong>
        <p>在圖上按住滑鼠，從開始拖到結束再放開。觸控可左右拖曳；也可以點圖移動游標，再用下方按鈕分別設定。</p>
        <div className="rs-range-values"><span>A 開始 <output aria-label="A 開始時間">{rangeValid ? rootStamp(range.start) : '未設定'}</output></span><span>B 結束 <output aria-label="B 結束時間">{rangeValid ? rootStamp(range.end) : '未設定'}</output></span><span>游標 {rootStamp(position)}</span></div>
        <div className="rs-actions">
          <button disabled={position > maxTime - .08} onClick={() => markRange('start')}>游標設為 A（開始）</button>
          <button disabled={position < minTime + .08} onClick={() => markRange('end')}>游標設為 B（結束）</button>
          <button onClick={() => {onUseSelectedRange(); setRangeMessage(focusRange?'已用鎖定段落設定 A–B。':presentation?'已用介紹段落設定 A–B。':'已用右側目前判斷段落設定 A–B。');}}>以目前段落設定 A–B</button>
        </div>
        <p role="status">{rangeMessage || (presentation?'選好範圍後，按「播放目前範圍」。勾選「A–B 循環」就會反覆播放。':'選好範圍後，按上方「播放原曲範圍」。勾選「A–B 循環」就會反覆播放。')}</p>
      </div>
      <div className="rs-time-axis">{ticks.map((t, i) => <span key={i} style={{left: `${i * 25}%`}}>{rootStamp(t)}</span>)}</div>
      <div className="rs-chart-title"><h3>低頻頻譜 · E1–E4</h3><span className="rs-legend">弱 <i/> 強</span></div>
      <div className="rs-plot rs-spectrum-plot" tabIndex={0} role="slider" aria-label="頻譜定位時間" aria-valuemin={minTime} aria-valuemax={maxTime} aria-valuenow={position} aria-valuetext={rootStamp(position)}
        onKeyDown={e => {if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {e.preventDefault(); onSeek(e.key === 'Home' ? view.start : e.key === 'End' ? Math.max(view.start, view.end - .01) : clamp(position + (e.key === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 1 : .1), minTime, maxTime - .01));}}}
        onPointerDown={e => {if (e.button !== 0) return; const p = point(e); drag.current = {time: p.time, x: e.clientX, pointer: e.pointerId}; e.currentTarget.setPointerCapture(e.pointerId); setProbe(p);}}
        onPointerMove={e => {const p = point(e); setProbe(p); if (drag.current?.pointer === e.pointerId && Math.abs(e.clientX - drag.current.x) > 4) setDragRange({start: Math.min(p.time, drag.current.time), end: Math.max(p.time, drag.current.time)});}}
        onPointerUp={e => {const d = drag.current; if (!d || d.pointer !== e.pointerId) return; const p = point(e); drag.current = null; setDragRange(null); if (Math.abs(e.clientX - d.x) > 4 && Math.abs(p.time - d.time) >= .08) {onRange(Math.min(p.time, d.time), Math.max(p.time, d.time)); setRangeMessage(presentation?'已選取 A–B；按「播放目前範圍」回聽。':'已選取圖中 A–B 範圍；按「播放原曲範圍」回聽。');} else onSeek(Math.min(p.time, maxTime - .01));}}
        onPointerCancel={() => {drag.current = null; setDragRange(null);}}>
        <canvas ref={canvas} width="1400" height="360" aria-label="原曲低頻能量圖" data-ready={!!data}/>
        {!data && <div className="rs-empty">{state === 'loading' ? '正在準備低頻圖…' : '按「產生低頻圖」查看原曲'}</div>}
        {[28, 36, 40, 48, 52, 60, 64].map(m => <div className="rs-note-line" key={m} style={{top: `${(64 - m) / 36 * 100}%`}}><span>{noteName(m)}</span></div>)}
        {beats.map(b => <i className={b.strong ? 'rs-beat strong' : 'rs-beat'} key={b.time} style={{left: `${left(b.time)}%`}}/>)}
        {shownRange && shownRange.start < view.end && shownRange.end > view.start && <div className="rs-selection" style={percent(shownRange.start, shownRange.end)}/>}
        {shownRange && <>
          {shownRange.start >= view.start && shownRange.start <= view.end && <span className="rs-boundary rs-boundary-a" style={{left: `clamp(0px, ${left(shownRange.start)}%, calc(100% - 58px))`}}>A 開始</span>}
          {shownRange.end >= view.start && shownRange.end <= view.end && <span className="rs-boundary rs-boundary-b" style={{left: `clamp(58px, ${left(shownRange.end)}%, 100%)`}}>B 結束</span>}
        </>}
        {cursor}
      </div>
      <div className="rs-readout"><span>{probe ? `${rootStamp(probe.time)} · 指向 ${noteName(probe.midi)} 附近（游標刻度）` : '點圖定位；左右拖曳選 A–B。鍵盤左右鍵移動 0.1 秒，Shift 移動 1 秒。'}</span><label>顯示較弱線索 <input aria-label="頻譜顯示範圍" type="range" min="35" max="80" step="5" value={contrast} onChange={e => setContrast(Number(e.target.value))}/></label></div>
      <p>{focusRange?'點圖定位時間；拖曳或用 A、B 按鈕決定右側填寫和弦的範圍。':presentation?'點圖定位時間，拖曳或用 A、B 按鈕調整回聽範圍。':'點圖或用方向鍵移動游標，右側會切到對應段落；拖曳只調整 A–B。'}</p>
      <h3 className="rs-lane-title">原分析和弦 <small>自動辨識，待核對</small></h3>
      <div className="rs-plot rs-chords" aria-label="原分析和弦時間軸">
        {visibleChords.length ? visibleChords.map((c, i) => <button key={i} title={`${c.symbol} ${rootStamp(c.start)}–${rootStamp(c.end)}`} aria-label={`查看和弦 ${c.symbol} ${rootStamp(c.start)}`} style={percent(c.start, c.end)} onClick={() => {onRange(Math.max(c.start,minTime), Math.min(c.end,maxTime)); onSeek(Math.max(c.start,minTime));}}>{c.symbol}</button>) : <span className="rs-no-chords">{data ? '此範圍沒有原分析和弦' : '產生低頻圖時一併讀取'}</span>}
        {cursor}
      </div>
      {workingChords?<><h3 className="rs-lane-title">我的和弦 <small>已採用的聽辨稿；空白仍待聽</small></h3><div className="rs-plot rs-chords rs-working-chords" aria-label="我的和弦時間軸">{workingChords.filter(c=>c.start<view.end&&c.end>view.start&&c.symbol!==null).map((c,i)=><button key={i} style={percent(c.start,c.end)} aria-label={`查看我的和弦 ${c.symbol} ${rootStamp(c.start)}`} onClick={()=>{onRange(Math.max(c.start,minTime),Math.min(c.end,maxTime));onSeek(Math.max(c.start,minTime));}}>{c.symbol}</button>)}{cursor}</div></>:null}
      <h3 className="rs-lane-title">我的根音行進 <small>只畫已採用音級；沒有原曲八度資訊</small></h3>
      <div className="rs-plot rs-roots" aria-label="已採用根音音級圖">
        {[...ROOT_NAMES].reverse().map((name, i) => <div className="rs-root-line" key={name} style={{top: `${i / 12 * 100}%`}}><span>{name}</span></div>)}
        {visibleRoots.map(s => s.status === 'confirmed' && s.root !== null ? <button key={s.id} aria-label={`查看已採用根音 ${ROOT_NAMES[s.root]} ${rootStamp(s.start)}`} title={`${ROOT_NAMES[s.root]} ${rootStamp(s.start)}–${rootStamp(s.end)}`} style={{...percent(s.start, s.end), top: `${(11 - s.root) / 12 * 100}%`}} onClick={() => {onRange(Math.max(s.start,minTime), Math.min(s.end,maxTime)); onSeek(Math.max(s.start,minTime));}}>{ROOT_NAMES[s.root]}</button> : <div className="rs-pending" key={s.id} title={`待聽 ${rootStamp(s.start)}–${rootStamp(s.end)}`} style={percent(s.start, s.end)}/>)}
        {cursor}
      </div>
      <p className="rs-current" aria-live="off">目前 {rootStamp(position)} · 原分析 {currentChord?.symbol ?? '未標示'} · 我的根音 {currentRoot?.status === 'confirmed' && currentRoot.root !== null ? ROOT_NAMES[currentRoot.root] : '待聽'}</p>
      <div className="rs-actions" hidden={!playbackControls}>
        <button className="root-primary" onClick={() => playing ? onPause() : onPlay(rangeValid ? range.start : view.start, rangeValid ? range.end : view.end)}>{playing ? '暫停圖表播放' : presentation?'播放 A–B 原曲':'循環 A–B 原曲'}</button>
        <button onClick={() => {onRange(view.start, view.end); onPlay(view.start, view.end);}}>聽目前圖中範圍</button>
        <span>{rangeValid ? `A ${rootStamp(range.start)} — B ${rootStamp(range.end)}` : '尚未選範圍'}</span>
      </div>
      <p>圖表播放只聽原曲，不加入你已採用的根音或和弦聲音。</p>
      <details className="rs-notes"><summary>怎麼用圖練習</summary><ol><li>先選 10–30 秒，聽原曲，再觀察低頻亮線隨時間移動。</li><li>{presentation||focusRange?'亮線可能是泛音；配合原曲和聲回聽，別只挑最亮或最低的線。':'亮線可能是泛音；用下面的參考音比較，並聽上方和聲，別只挑最亮或最低的線。'}</li><li>{focusRange?'拖曳選 A–B 並循環，在右側填寫並採用和弦後，「我的和弦」圖會同步顯示。':'拖曳選 A–B 並循環。依自己的判斷在原有練習區採用根音，圖中才會顯示。'}</li></ol><p>頻譜採固定約 0.74 秒窗，起音與換音會被展寬；快速變化仍需回聽。左右聲道能量平均，未分離貝斯。根音圖按 C 到 B 排列，只表示音級，不能解讀為真實低音上下行或八度。</p><p>全部圖表使用本片段內秒數{doc.source.source_start > 0 ? `；0 秒對應原錄音 ${rootStamp(doc.source.source_start)}` : ''}。圖表選段與播放不會採用根音或修改原和弦稿。</p></details>
    </>}
  </section>;
}
