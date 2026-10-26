import { useEffect, useRef, useState } from "react";
import type { SongScore } from "./types";

type Preview = { base: SongScore; next: SongScore; changes: number; protected: number; unresolved: number };

export function ChordGridCandidate({score, apiBase, onCommit}: {
  score: SongScore; apiBase: string; onCommit: (base: SongScore, next: SongScore) => boolean;
}) {
  const current = useRef(score); current.current = score;
  const request = useRef<AbortController | null>(null);
  const [pending, setPending] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    request.current?.abort(); request.current = null;
    setPending(false); setPreview(null); setMessage("");
    return () => request.current?.abort();
  }, [score]);
  async function generate() {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const obsolete = () => controller.signal.aborted || current.current !== score;
    setPending(true); setPreview(null); setMessage("");
    try {
      const response = await fetch(`${apiBase}/scores/chord-grid-candidate`, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(score), signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status === 409 ? "這份譜已整理過；請先 Undo 或載入原版。" : "無法整理這份譜。需要有效的 4/4 拍格及不重疊的和弦區段。");
      const body = await response.json();
      if (!obsolete()) setPreview({base: score, next: body.score, changes: body.report.changes.length,
        protected: body.report.protected.length, unresolved: body.report.unquantized_edges.length});
    } catch (error) {
      if (!obsolete()) setMessage(error instanceof Error ? error.message : "整理失敗");
    } finally { if (!obsolete()) setPending(false); }
  }
  const applied = !!score.provenance.parameters?.chord_grid_candidate;
  const ready = preview?.base === score ? preview : null;
  return <details className="workspace-disclosure">
    <summary>整理伴奏拍長（八分拍格・實驗）</summary>
    <p>依目前 4/4 拍點整理和弦到整拍或半拍位置。保留旋律、和弦名稱、人工邊界與休止；不會重新辨識或校正拍點。</p>
    <button type="button" disabled={pending || applied || score.analysis.time_signature !== "4/4"} onClick={() => void generate()}>{pending ? "拍長整理中…" : "預覽拍長整理"}</button>
    {ready ? <div role="status">
      <p>預計調整 {ready.changes} 段和弦；保留 {ready.protected} 處受保護邊界，另有 {ready.unresolved} 處未落在拍格。尚未改動工作譜。</p>
      {ready.changes ? <button type="button" onClick={() => {
        if (!onCommit(ready.base, ready.next)) setMessage("工作譜已改變，未套用舊預覽；請重新產生。");
      }}>套用拍長整理（可 Undo）</button> : <p>目前沒有可調整的和弦時值。</p>}
    </div> : null}
    {applied ? <p role="status">目前已使用八分拍格伴奏譜。本次操作可用 Undo 還原；若是載入已保存的整理版，請另行載入原修訂。旋律時值沒有整理。</p> : null}
    <p>套用後圖表、播放與 MIDI 使用同一份譜，演奏選項會回到「原版刷奏」。不會自動保存；請試聽後再決定是否保存。</p>
    {message ? <p role="alert">{message}</p> : null}
  </details>;
}
