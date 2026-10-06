import { useEffect, useState } from "react";
import type { SongScore } from "./types";

export function ContourCandidate({ score, jobId, apiBase, onCommit }: {
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
      const response = await fetch(`${apiBase}/api/v1/jobs/${encodeURIComponent(jobId)}/melody-candidate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score),
      });
      const body = await response.json();
      if (!response.ok) throw Error(typeof body.detail === "string" ? body.detail : "無法建立候選");
      setResult({ base: score, job: jobId, next: body });
    } catch (e) { setMessage(e instanceof Error ? e.message : "無法建立候選"); }
    finally { setPending(false); }
  }
  const ready = result && result.base === score && result.job === jobId ? result : null;
  return <details className="workspace-disclosure">
    <summary>Contour → 可編輯音符候選（G，實驗性）</summary>
    <p>若 Contour 比 Play score 準，可用保存的人聲音高產生 G 音符候選，不重新分析。不處理器樂前奏／尾奏，不保證整曲正確。</p>
    <p>先 Save new revision 備份。只能從本次未修改的原始旋律建立候選；有人工旋律修改或移調時會拒絕。產生不等於套用，也不會自動保存。</p>
    <button type="button" disabled={!jobId || pending} onClick={() => void generate()}>{pending ? "產生中…" : "產生 Contour 音符候選"}</button>
    {ready ? <div>
      <p>原旋律 {score.melody.length} 音符 → 候選 {ready.next.melody.length} 音符。音符增加不等於準確率提高；和弦／拍點保持工作譜內容。</p>
      <button type="button" onClick={() => {
        if (!onCommit(ready.base, ready.next)) setMessage("工作譜已改變，未套用。請重新產生候選。");
      }}>套用候選到工作譜（可 Undo）</button>
    </div> : null}
    {result && !ready ? <p role="status">工作譜或來源已改變，候選已失效，未套用。</p> : null}
    <p>套用後：Compiled score playback → 只聽旋律 → Play score；Undo 可回原版。確認後再 Save new revision。MIDI／Tab 會使用目前工作譜，Contour 音訊不變。</p>
    {score.provenance.parameters?.melody_note_processing === "bounded-source-v1" ? <p role="status">目前工作譜使用 Contour G 音符候選；尚須聽感驗收。</p> : null}
    {message ? <p role="status">{message}</p> : null}
  </details>;
}
