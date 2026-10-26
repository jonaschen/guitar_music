import { useEffect, useRef, useState } from "react";
import type { SongScore } from "./types";

type Issue = {
  right_id: string; measure: number; old_chord: string; new_chord: string;
  downbeat_seconds: number; boundary_lag_seconds: number;
  wait_after_downbeat_seconds: number; previous_beat_seconds: number;
  contains_manual_edit: boolean;
};

export function ChordEntryAudit({score, mode, apiBase, onSeek}: {
  score: SongScore; mode: "original" | "continuous" | "sparse"; apiBase: string;
  onSeek: (time: number) => void;
}) {
  const current = useRef({score, mode}); current.current = {score, mode};
  const request = useRef<AbortController | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{score: SongScore; mode: string; issues: Issue[]} | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    request.current?.abort(); request.current = null;
    setPending(false); setResult(null); setError("");
    return () => request.current?.abort();
  }, [score, mode]);
  async function inspect() {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    const obsolete = () => controller.signal.aborted || current.current.score !== score || current.current.mode !== mode;
    setPending(true); setError(""); setResult(null);
    try {
      const response = await fetch(`${apiBase}/scores/chord-entry-audit`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({score, mode}), signal: controller.signal,
      });
      if (!response.ok) throw new Error("暫時無法檢查換和弦入口，請稍後再試。");
      const body = await response.json();
      if (!obsolete()) setResult({score, mode, issues: body.issues});
    } catch (e) {
      if (!obsolete()) setError(e instanceof Error ? e.message : "檢查失敗");
    } finally { if (!obsolete()) setPending(false); }
  }
  const ready = result?.score === score && result.mode === mode ? result : null;
  return <details className="workspace-disclosure">
    <summary>換和弦入口檢查</summary>
    <p>找出譜面邊界稍晚於第一拍、讓新和弦等到後面才刷出的情況。只檢查目前演奏方案，不改譜；是否需要修正仍以試聽為準。</p>
    <button type="button" disabled={pending} onClick={() => void inspect()}>{pending ? "入口檢查中…" : "檢查目前演奏"}</button>
    {ready ? <div role="status">
      {ready.issues.length ? <ul>{ready.issues.map(issue => <li key={issue.right_id}>
        Bar {issue.measure} · {issue.old_chord} → {issue.new_chord}：第一拍後 {issue.wait_after_downbeat_seconds.toFixed(2)} 秒才首次刷出新和弦（邊界晚 {Math.round(issue.boundary_lag_seconds * 1000)} 毫秒）。
        {issue.contains_manual_edit ? " 含人工修改，可能是刻意安排。" : ""}
        <button type="button" onClick={() => onSeek(issue.previous_beat_seconds)}>定位 Bar {issue.measure} 前一拍</button>
      </li>)}</ul> : <p>未找到這一類入口等待；不代表所有和弦或節奏都正確。</p>}
    </div> : null}
    {error ? <p role="alert">{error}</p> : null}
  </details>;
}
