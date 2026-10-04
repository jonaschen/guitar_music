import { useEffect, useState } from "react";
import type { SongScore } from "./types";
import { retimeBars } from "./barTiming";

type Props = { score: SongScore; bars: { number: number; start: number; end: number }[];
  playhead: number; onStop: () => void; onSeek: (time: number) => void;
  onOriginal: (start: number, end: number) => void;
  onCommit: (base: SongScore, next: SongScore) => boolean };

export function BarTimingEditor(props: Props) {
  const { score, bars } = props;
  const [times, setTimes] = useState<string[]>([]);
  const [even, setEven] = useState(false);
  const [message, setMessage] = useState("");
  const [committedScore, setCommittedScore] = useState<SongScore | null>(null);
  const signature = JSON.stringify(bars);
  useEffect(() => { setTimes([...bars.map(b => String(b.start)), String(bars.at(-1)?.end ?? 0)]); setEven(false); }, [signature, score]);
  if (!bars.length) return null;
  const anchors = [...bars.map(b => ({ measure: b.number, time: b.start })), { measure: bars.at(-1)!.number + 1, time: bars.at(-1)!.end }];
  let preview: SongScore | null = null, error = "";
  try {
    if (times.length !== anchors.length || times.some(t => !t.trim())) throw Error("請填入所有時間。");
    preview = retimeBars(score, anchors.map((a, i) => ({ ...a, time: Number(times[i]) })), even);
  } catch (e) { error = e instanceof Error ? e.message : "無法校正"; }
  const changes = preview?.beats.filter((b, i) => Math.abs(b.time - score.beats[i].time) > 1e-9).length ?? 0;
  function setTime(index: number, value: string) { props.onStop(); setTimes(old => old.map((t, i) => i === index ? value : t)); setMessage(""); }
  return <details className="bar-timing-editor">
    <summary>所選小節分界校正（不移動音符）</summary>
    <p>先聽原曲，再填入小節起點。首尾固定，只調整段落內共用拍點。旋律、和弦、歌詞仍保留原秒數，不會自動對齊或修音。</p>
    <div className="bar-timing-scroll"><table><thead><tr><th>分界</th><th>起點秒數</th><th>對照目前分界（非草稿）</th><th>目前和弦位置（本小節時間比例）</th></tr></thead><tbody>
      {anchors.map((a, i) => <tr key={a.measure}><td>Bar {a.measure}{i === anchors.length - 1 ? "（段落終點）" : ""}</td>
        <td><input aria-label={`Bar ${a.measure} boundary seconds`} type="number" step="0.01" value={times[i] ?? ""}
          disabled={i === 0 || i === anchors.length - 1} onChange={e => setTime(i, e.target.value)} /></td>
        <td><button type="button" onClick={() => { props.onStop(); props.onSeek(a.time); }}>定位 Bar {a.measure}</button>
          <button type="button" onClick={() => props.onOriginal(Math.max(0, a.time - .7), Math.min(score.song.duration_seconds, a.time + 1.3))}>原曲 Bar {a.measure}</button>
          {i > 0 && i < anchors.length - 1 ? <button type="button" onClick={() => setTime(i, String(props.playhead))}>以暫停位置設定 Bar {a.measure}</button> : null}</td>
        <td>{i < bars.length ? score.chords.filter(c => c.start < bars[i].end && c.end > bars[i].start).map(c =>
          <button type="button" key={c.id} onClick={() => { props.onStop(); props.onSeek(Math.max(c.start, bars[i].start)); }}>
            {c.symbol} · {Math.round((Math.max(c.start, bars[i].start) - bars[i].start) / (bars[i].end - bars[i].start) * 100)}%{c.start < bars[i].start ? " 延續" : ""}
          </button>) : "—"}</td></tr>)}
    </tbody></table></div>
    <label><input type="checkbox" checked={even} onChange={e => { props.onStop(); setEven(e.target.checked); }} />明確將所選小節內各拍等分（不移動和弦或旋律）</label>
    <p role="status">{error || `預覽：將改動 ${changes} 個拍點；尚未套用。`}</p>
    <button type="button" disabled={!preview || !changes} onClick={() => { props.onStop(); if (preview && props.onCommit(score, preview)) { setCommittedScore(preview); setMessage("已校正工作譜拍點；可用下方 Undo 撤銷，並用 Save new revision 保存。旋律／和弦秒數未改動。"); } }}>套用小節分界</button>
    <button type="button" onClick={() => { setTimes(anchors.map(a => String(a.time))); setEven(false); setMessage(""); }}>取消分界草稿</button>
    {message && committedScore === score ? <p role="status">{message}</p> : null}
  </details>;
}
