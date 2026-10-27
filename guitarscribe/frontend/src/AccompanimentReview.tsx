import { useMemo, useState } from "react";
import type { SongScore } from "./types";
import { measureLayout } from "./measureLayout";
import { notationBars } from "./melodyNotation";

export type ReviewMode = "source" | "guitar" | "mix";
export function AccompanimentReview({ score, sourceAvailable, playing, preparing, playhead, guitarVolume, performanceLabel, onVolume, onPlay, onStop, onTools, onEditChord }: {
  score: SongScore; sourceAvailable: boolean; playing: boolean; preparing: boolean; playhead: number;
  guitarVolume: number; performanceLabel: string; onVolume: (value: number) => void;
  onPlay: (mode: ReviewMode, start: number, end: number, loop: boolean, from?: number) => void;
  onStop: () => void; onTools: () => void; onEditChord?: (id: string, scope?: {start:number;end:number;bar:number}) => void;
}) {
  const bars = useMemo(() => notationBars(score), [score]);
  const [index, setIndex] = useState(0), [count, setCount] = useState(4);
  const [mode, setMode] = useState<ReviewMode>("mix"), [loop, setLoop] = useState(false);
  const activeIndex = Math.min(index, Math.max(0, bars.length - 1));
  const selected = bars.slice(activeIndex, activeIndex + count);
  const start = selected[0]?.start ?? 0, end = selected.at(-1)?.end ?? score.song.duration_seconds;
  const chords = score.chords.filter(c => c.end > start && c.start < end);
  const current = score.chords.find(c => c.start <= playhead && playhead < c.end);
  const disabled = end <= start || (mode !== "guitar" && !sourceAvailable) || (mode === "mix" && !score.key_context.audio_matches_notation);
  function change(action: () => void) { onStop(); action(); }
  return <section className="accompaniment-review" aria-label="和弦核對">
    <h3>聽一段，確認和弦</h3>
    <p>先選範圍，再播放原曲＋吉他。需要修改時，點下方的和弦。</p>
    <div className="review-controls review-range">
      <label>起始小節 <select aria-label="核對起始小節" value={Math.min(index, Math.max(0, bars.length - 1))} onChange={e => change(() => setIndex(Number(e.target.value)))}>{bars.map((b, i) => <option key={i} value={i}>Bar {b.number}</option>)}</select></label>
      <label>範圍 <select aria-label="核對小節數" value={count} onChange={e => change(() => setCount(Number(e.target.value)))}>{[2,4,8].map(n => <option key={n} value={n}>{n} 小節</option>)}</select></label>
      <label><input type="checkbox" checked={loop} onChange={e => change(() => setLoop(e.target.checked))} />循環這一段</label>
    </div>
    <div className="review-controls review-modes" role="group" aria-label="核對聲音">
      {([["source", "只聽原曲"], ["guitar", "只聽吉他"], ["mix", "原曲＋系統吉他"]] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => change(() => setMode(value))}>{label}</button>)}
    </div>
    <p>吉他演奏：{performanceLabel}</p>
    <label>吉他音量 <input aria-label="核對吉他音量" type="range" min="0" max="1" step="0.01" value={guitarVolume} onChange={e => change(() => onVolume(Number(e.target.value)))} /></label>
    {mode !== "source" && guitarVolume === 0 ? <p role="status">吉他音量目前為零，請調高後再核對。</p> : null}
    {!sourceAvailable && mode !== "guitar" ? <p role="status">此版本目前沒有可用原曲，仍可選「只聽吉他」。</p> : null}
    {mode === "mix" && !score.key_context.audio_matches_notation ? <p role="status">工作譜已移調，與原曲音高不同。請先回到原調，或分開試聽。</p> : null}
    <div className="review-controls review-transport">
      <button type="button" className="review-primary" disabled={disabled || preparing} onClick={() => onPlay(mode, start, end, loop)}>從這段開頭播放</button>
      <button type="button" disabled={disabled || preparing || playing || playhead <= start || playhead >= end} onClick={() => onPlay(mode, start, end, loop, playhead)}>續播這段核對</button>
      <button type="button" disabled={!playing && !preparing} onClick={onStop}>{preparing ? "取消準備" : "暫停核對"}</button>
      <button type="button" onClick={onTools}>伴奏設定與拍長整理</button>
    </div>
    <p aria-live="polite">{preparing ? "正在準備聲音…" : playing ? "播放中" : "已暫停"} · 樂譜 {start.toFixed(1)}–{end.toFixed(1)} 秒 · 譜面和弦：{playhead >= start && playhead < end ? current?.symbol ?? "—" : "—"}</p>
    <div className="review-stepper">
      <button type="button" disabled={activeIndex <= 0} onClick={() => change(() => setIndex(Math.max(0,activeIndex-count)))}>上一段</button>
      <span>Bar {selected[0]?.number ?? "—"}–{selected.at(-1)?.number ?? "—"}</span>
      <button type="button" disabled={activeIndex+count >= bars.length} onClick={() => change(() => setIndex(activeIndex+count))}>下一段</button>
    </div>
    <p className="review-chords" aria-label="本段和弦">{chords.length ? chords.map(c => c.symbol).join(" → ") : "這段沒有和弦事件"}</p>
    <div className="review-bar-list" aria-label="本段小節和弦">
      {selected.map(bar => {
        const layout = measureLayout(score.beats,bar.start,bar.end,score.analysis.bpm);
        const entries = score.chords.filter(c => c.end > bar.start && c.start < bar.end);
        return <article key={`${bar.number}-${bar.start}`} className={playhead >= bar.start && playhead < bar.end && playing ? "review-bar is-playing" : "review-bar"}>
          <header><strong>Bar {bar.number}</strong><small>{bar.start.toFixed(1)}–{bar.end.toFixed(1)} 秒</small></header>
          <div>{entries.length ? entries.map(c => <button type="button" key={c.id} aria-label={`編輯 Bar ${bar.number} 的 ${c.symbol}`} onClick={() => { onStop(); onEditChord?.(c.id); }} disabled={!onEditChord}>
            <strong>{c.symbol}</strong><small>{layout.length(Math.max(c.start,bar.start),Math.min(c.end,bar.end))}{c.start < bar.start ? " · 延續" : ""}</small>
          </button>) : <span className="review-gap">尚未指定和弦</span>}</div>
        </article>;
      })}
    </div>
  </section>;
}
