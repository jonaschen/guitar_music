import { useEffect, useState } from "react";
import type { SongScore } from "./types";
import { songBounds } from "./songRange";

export function SongRangeEditor({ score, playhead, onApply, onPreview }: {
  score: SongScore; playhead: number;
  onApply: (range: SongScore["song_range"]) => void;
  onPreview: (start: number, end: number) => void;
}) {
  const bounds = songBounds(score);
  const [start, setStart] = useState(String(bounds.start));
  const [end, setEnd] = useState(String(bounds.end));
  const [message, setMessage] = useState("");
  useEffect(() => { setStart(String(bounds.start)); setEnd(String(bounds.end)); }, [bounds.start, bounds.end]);
  const valid = start.trim() !== "" && end.trim() !== "" && Number.isFinite(Number(start)) && Number.isFinite(Number(end)) && Number(start) >= 0 && Number(start) < Number(end) && Number(end) <= score.song.duration_seconds;
  return <details className="workspace-disclosure song-range-editor">
    <summary>歌曲有效範圍 · 略過 MV 開場（目前 {bounds.start.toFixed(2)}–{bounds.end.toFixed(2)} 秒）</summary>
    <p>例如 MV 前 19 秒非歌曲，可將起點設為約 20 秒。原檔、音符、和弦及時間戳不改，只限定播放與主要譜面範圍。歌曲起點不是重新指定小節第一拍。</p>
    <div className="melody-edit-fields">
      <label>歌曲起點（原檔秒數）<input aria-label="Song range start" type="number" min="0" step="0.01" value={start} onChange={(e) => setStart(e.target.value)} /></label>
      <label>歌曲終點（原檔秒數）<input aria-label="Song range end" type="number" min="0" max={score.song.duration_seconds} step="0.01" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
    </div>
    <div className="toolbar-actions">
      <button type="button" className="ghost-button" onClick={() => setStart(String(playhead))}>用目前位置作起點</button>
      <button type="button" className="ghost-button" disabled={!valid} onClick={() => onPreview(Number(start), Math.min(Number(end), Number(start) + 5))}>試聽起點後 5 秒（來源）</button>
      <button type="button" className="ghost-button" disabled={!valid} onClick={() => { onApply({ start: Number(start), end: Number(end) }); setMessage("已套用歌曲範圍，尚未保存；請 Save new revision。可 Undo 或取消範圍。"); }}>套用歌曲範圍</button>
      <button type="button" className="ghost-button" onClick={() => { onApply(null); setMessage("已恢復全曲範圍，原始資料不變；尚未保存。"); }}>取消範圍，顯示全曲</button>
    </div>
    {!valid ? <p role="alert">起點需小於終點，並且都在原檔時間內。</p> : null}
    <p>{message}</p>
    <p>本版針對已分析樂譜；不裁切檔案、不重編小節。新分析的範圍裁切及範圍專用 MIDI／MusicXML 匯出尚未提供，現有匯出仍包含完整工作樂譜。</p>
  </details>;
}
