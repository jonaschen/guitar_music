import { useEffect, useState } from "react";

export function PlaybackRangeEditor({ start, end, loopStart, loopEnd, onApply, onClear, onInteract }: {
  start: number; end: number; loopStart: number | null; loopEnd: number | null;
  onApply: (a: number, b: number) => void; onClear: () => void; onInteract: () => void;
}) {
  const [a, setA] = useState(String(start));
  const [b, setB] = useState(String(Math.min(end, start + 13)));
  useEffect(() => {
    setA(String(loopStart ?? start));
    setB(String(loopEnd ?? Math.min(end, (loopStart ?? start) + 13)));
  }, [start, end, loopStart, loopEnd]);
  const valid = a.trim() !== "" && b.trim() !== "" && Number.isFinite(Number(a)) && Number.isFinite(Number(b))
    && Number(a) >= start && Number(b) <= end && Number(a) < Number(b);
  return <section className="playback-range-editor" aria-label="Exact playback range" onFocusCapture={onInteract}>
    <div className="melody-edit-fields">
      <label>循環起點 A（秒）<input aria-label="Loop start seconds" type="number" min={start} max={end} step="0.01" value={a} onChange={(e) => setA(e.target.value)} /></label>
      <label>循環終點 B（秒）<input aria-label="Loop end seconds" type="number" min={start} max={end} step="0.01" value={b} onChange={(e) => setB(e.target.value)} /></label>
    </div>
    <button type="button" className="ghost-button" disabled={!valid} onClick={() => onApply(Number(a), Number(b))}>套用 A–B 並定位到 A</button>
    <button type="button" className="ghost-button" disabled={loopStart === null && loopEnd === null} onClick={onClear}>取消秒數循環</button>
    <p role="status">{loopStart !== null && loopEnd !== null ? `目前循環 ${loopStart.toFixed(2)}–${loopEnd.toFixed(2)} 秒` : "尚未設定秒數循環"}。套用後按 Play score；有來源音訊時也可按 Play 對照。使用裁切後的畫面秒數，不修改音符。</p>
    {!valid ? <p role="alert">需符合 {start.toFixed(2)} ≤ A &lt; B ≤ {end.toFixed(2)} 秒。</p> : null}
  </section>;
}
