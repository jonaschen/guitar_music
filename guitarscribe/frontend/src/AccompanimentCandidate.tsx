import { useEffect, useState } from "react";
import type { SongScore } from "./types";

export function AccompanimentCandidate({ score, jobId, apiBase, onCommit }: {
  score: SongScore; jobId: string | null | undefined; apiBase: string;
  onCommit: (base: SongScore, next: SongScore) => boolean;
}) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ base: SongScore; job: string; next: SongScore } | null>(null);
  const [message, setMessage] = useState("");
  useEffect(() => { setResult(null); setMessage(""); }, [score, jobId]);
  async function generate() {
    if (!jobId || pending) return;
    setPending(true); setResult(null); setMessage("");
    try {
      const response = await fetch(`${apiBase}/api/v1/jobs/${encodeURIComponent(jobId)}/accompaniment-candidate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score),
      });
      const body = await response.json();
      if (!response.ok) throw Error(typeof body.detail === "string" ? body.detail : "無法產生和弦候選");
      setResult({ base: score, job: jobId, next: body });
    } catch (error) { setMessage(error instanceof Error ? error.message : "無法產生和弦候選"); }
    finally { setPending(false); }
  }
  const ready = result && result.base === score && result.job === jobId ? result : null;
  const applied = score.provenance.parameters?.chord_input_source === "existing-accompaniment-stem-v1";
  return <details className="workspace-disclosure">
    <summary>從伴奏重新辨識和弦（實驗性）</summary>
    <p>使用已保存的伴奏音軌，保留目前旋律與拍點。需要原分析和弦、未移調及 Capo 0；沒有伴奏音軌時不會重新分離。</p>
    <button type="button" disabled={!jobId || pending || applied} onClick={() => void generate()}>{pending ? "和弦辨識中…" : "產生伴奏和弦候選"}</button>
    {ready ? <div>
      <p>原和弦 {score.chords.length} 段 → 候選 {ready.next.chords.length} 段。段數減少不代表更正確；產生尚未改動工作譜。</p>
      <button type="button" onClick={() => {
        if (!onCommit(ready.base, ready.next)) setMessage("工作譜已變更，未套用。請重新產生候選。");
      }}>套用伴奏和弦（可 Undo）</button>
    </div> : null}
    {result && !ready ? <p role="status">工作譜或來源已變更，未套用舊和弦候選。</p> : null}
    {applied ? <p role="status">目前使用伴奏音軌和弦候選；確認後可 Save new revision，Undo 可回原版。</p> : null}
    <p>套用後播放與匯出使用目前工作譜。不會自動保存或覆寫原分析。</p>
    {message ? <p role="status">{message}</p> : null}
  </details>;
}
