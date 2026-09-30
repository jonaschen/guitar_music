import { useEffect, useRef, useState } from "react";
import type { SongScore } from "./types";

const pitches = Array.from({ length: 128 }, (_, midi) => ({ midi,
  label: `${["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"][midi % 12]}${Math.floor(midi / 12) - 1}` }));

type Props = {
  score: SongScore; jobId?: string; playhead: number; apiBase: string;
  onCommit: (base: SongScore, next: SongScore) => boolean;
  onSeek: (time: number) => void;
  onPitch: (midi: number) => void;
  onAudition: (start: number, end: number) => void;
  onStop: () => void;
  onUndo: () => void; onRedo: () => void; canUndo: boolean; canRedo: boolean;
  revisionId: string; onRevisionId: (id: string) => void;
  onSave: () => void; onLoad: () => void; saving: boolean; saveStatus: string;
};

export function MelodyEditor(props: Props) {
  const { score } = props;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [windowStart, setWindowStart] = useState(0);
  const [midi, setMidi] = useState(60);
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("0.5");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const selected = score.melody.find((n) => n.id === selectedId);
  const left = Math.max(0, Math.min(windowStart, Math.max(0, score.song.duration_seconds - 0.01)));
  const right = Math.min(score.song.duration_seconds, left + 8);
  const visible = score.melody.filter((n) => n.end > left && n.start < right).sort((a, b) => a.start - b.start);
  useEffect(() => {
    if (selected) { setMidi(selected.midi); setStart(String(selected.start)); setEnd(String(selected.end)); }
    else setSelectedId(null);
  }, [selected]);

  function newNote() {
    setSelectedId(null);
    setStart(String(props.playhead));
    const next = score.melody.filter((n) => n.start > props.playhead).sort((a, b) => a.start - b.start)[0];
    setEnd(String(Math.min(score.song.duration_seconds, props.playhead + 0.5, next?.start ?? Infinity)));
    setMessage("設定音高與起迄，再按 Add note。音高是目前譜面 Key 的實際發聲音高；不自動吸附拍點。");
  }

  async function edit(operation: "add" | "update" | "delete" | "split" | "merge_next") {
    if (inFlight.current) return;
    if (["add", "update"].includes(operation) && (!start.trim() || !end.trim() || !Number.isFinite(Number(start)) || !Number.isFinite(Number(end)))) {
      setMessage("請填入有效起點與終點。"); return;
    }
    inFlight.current = true; setBusy(true); setMessage("");
    const base = score;
    try {
      const response = await fetch(`${props.apiBase}/scores/melody/edit`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score: base, operation, note_id: selected?.id ?? null,
          ...(operation === "add" || operation === "update" ? { midi, start: Number(start), end: Number(end) } : {}),
          ...(operation === "split" ? { split_time: props.playhead } : {}), source_job_id: props.jobId ?? null }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Invalid note edit; check pitch and timing.");
      if (!props.onCommit(base, body.score)) {
        setMessage("樂譜已在其他操作中改變，本次較舊的回應未套用。請重新操作。"); return;
      }
      setSelectedId(body.selected_note_id);
      setMessage("已修改工作樂譜，尚未保存。原曲與 Contour 不變；用「試聽修訂片段」聽修改結果。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Edit failed"); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <details className="melody-editor workspace-disclosure">
    <summary>旋律人工編輯 · Melody editor</summary>
    <p>編輯的是音符樂譜，不是人聲輪廓。空白可能是休止或漏抓；可手動補入。先保存版本再離開頁面。</p>
    <div className="editor-actions">
      <label>片段起點（秒）<input aria-label="Melody window start" type="number" min="0" max={score.song.duration_seconds} step="0.1" value={windowStart} onChange={(e) => setWindowStart(Number(e.target.value))} /></label>
      <button type="button" onClick={() => setWindowStart(Math.max(0, left - 8))}>前 8 秒</button>
      <button type="button" onClick={() => setWindowStart(Math.min(Math.max(0, score.song.duration_seconds - 8), left + 8))}>後 8 秒</button>
      <button type="button" onClick={() => setWindowStart(props.playhead)}>定位到播放位置</button>
      <button type="button" onClick={() => props.onSeek(left)}>跳到片段起點</button>
    </div>
    <p>{left.toFixed(2)}–{right.toFixed(2)}s · {visible.length} 音符。點選下方音符後編輯；時間不會自動量化。</p>
    <div className="melody-edit-list" aria-label="Editable melody notes">
      {visible.map((note) => <button type="button" key={note.id} aria-pressed={selectedId === note.id}
        onClick={() => { setSelectedId(note.id); props.onSeek(note.start); setMessage(""); }}>
        {note.note} · {note.start.toFixed(2)}–{note.end.toFixed(2)}s{note.edited ? " · Edited" : ""}
      </button>)}
      {!visible.length ? <span>此片段沒有音符，可用 New at playhead 補入。</span> : null}
    </div>
    <fieldset disabled={busy}>
      <legend>{selected ? `編輯 ${selected.note}` : "新增音符"}</legend>
      <div className="melody-edit-fields">
        <label>音高<select aria-label="Melody pitch" value={midi} onChange={(e) => setMidi(Number(e.target.value))}>{pitches.map((p) => <option key={p.midi} value={p.midi}>{p.label} · {p.midi}</option>)}</select></label>
        <label>起點（秒）<input aria-label="Melody note start" type="number" min="0" step="0.01" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>終點（秒）<input aria-label="Melody note end" type="number" min="0" step="0.01" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      <p>長度：{Number.isFinite(Number(end) - Number(start)) ? (Number(end) - Number(start)).toFixed(3) : "—"} 秒{selected && (selected.string == null || selected.fret == null) ? " · 目前吉他設定無可用指型；音符仍保留，可修改音高／調弦／把位。" : ""}</p>
      <div className="editor-actions">
        <button type="button" onClick={() => props.onPitch(midi)}>預聽音高</button>
        <button type="button" onClick={newNote}>New at playhead</button>
        <button type="button" onClick={() => void edit(selected ? "update" : "add")}>{selected ? "Apply note" : "Add note"}</button>
        <button type="button" disabled={!selected} onClick={() => void edit("delete")}>Delete note</button>
        <button type="button" disabled={!selected || props.playhead <= selected.start || props.playhead >= selected.end} onClick={() => void edit("split")}>Split at playhead</button>
        <button type="button" disabled={!selected} onClick={() => void edit("merge_next")}>Merge next same pitch</button>
      </div>
    </fieldset>
    <div className="editor-actions">
      <button type="button" disabled={!props.canUndo} onClick={props.onUndo}>Undo melody edit</button>
      <button type="button" disabled={!props.canRedo} onClick={props.onRedo}>Redo melody edit</button>
      <button type="button" onClick={() => props.onAudition(left, right)}>試聽修訂片段</button>
      <button type="button" onClick={props.onStop}>停止修訂試聽</button>
    </div>
    <p>片段試聽只播放目前工作樂譜的旋律、原速、不加吉他。Undo／Redo 共用整份樂譜的歷史。</p>
    <div className="editor-actions">
      <label>版本 ID<input aria-label="Melody revision ID" value={props.revisionId} onChange={(e) => props.onRevisionId(e.target.value)} /></label>
      <button type="button" disabled={busy || props.saving} onClick={props.onSave}>Save new revision</button>
      <button type="button" disabled={busy || props.saving || !props.revisionId.trim()} onClick={props.onLoad}>Load melody revision</button>
    </div>
    <p>{props.saveStatus}</p>
    <p role="status">{message}</p>
  </details>;
}
