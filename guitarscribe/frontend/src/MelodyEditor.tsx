import { useEffect, useMemo, useRef, useState } from "react";
import type { SongScore } from "./types";
import { EditableTab } from "./EditableTab";
import { BarTimingEditor } from "./BarTimingEditor";
import { songBounds } from "./songRange";
import { notationBars, notationClock, noteLengths, lengthLabel, noteGrid } from "./melodyNotation";

const pitches = Array.from({ length: 128 }, (_, midi) => ({ midi,
  label: `${["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"][midi % 12]}${Math.floor(midi / 12) - 1}` }));

type Props = {
  score: SongScore; jobId?: string; playhead: number; apiBase: string;
  onCommit: (base: SongScore, next: SongScore) => boolean;
  onSeek: (time: number) => void;
  onPitch: (midi: number) => void;
  onAudition: (start: number, end: number, loop?: boolean) => void;
  onOriginal: (start: number, end: number) => void;
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
  const [tabString, setTabString] = useState(2);
  const [tabFret, setTabFret] = useState(1);
  const [explicitTab, setExplicitTab] = useState(false);
  const [barCount, setBarCount] = useState(4);
  const [loop, setLoop] = useState(false);
  const [gridQuarters, setGridQuarters] = useState(.5);
  const [targetSlot, setTargetSlot] = useState(0);
  const inFlight = useRef(false);
  const selected = score.melody.find((n) => n.id === selectedId);
  const conflict = score.melody.filter((n) => n.id !== selected?.id && Number(start) < n.end - 1e-8 && n.start < Number(end) - 1e-8).sort((a, b) => a.start - b.start)[0];
  const conflictMessage = conflict ? `與 ${conflict.note}（${conflict.start.toFixed(3)}–${conflict.end.toFixed(3)} 秒）重疊。此編輯器目前是單旋律，即使在不同弦也不能同時新增；可選取該音修改，或調整新增位置／音長。` : "";
  const songRange = songBounds(score);
  const left = Math.max(songRange.start, Math.min(windowStart, Math.max(songRange.start, songRange.end - 0.01)));
  const right = Math.min(songRange.end, left + 8);
  const visible = score.melody.filter((n) => n.end > left && n.start < right).sort((a, b) => a.start - b.start);
  const bars = useMemo(() => notationBars(score), [score]);
  const barNoteCounts = useMemo(() => bars.map((bar) => score.melody.filter((n) => n.start < bar.end && n.end > bar.start).length), [score, bars]);
  const barIndex = Math.max(0, bars.findIndex((bar) => left >= bar.start && left < bar.end));
  const shownBars = bars.slice(barIndex, barIndex + barCount);
  const rangeStart = shownBars[0]?.start ?? left;
  const rangeEnd = shownBars.at(-1)?.end ?? right;
  const rangeNotes = score.melody.filter((n) => n.start < rangeEnd && n.end > rangeStart);
  const phraseNotes = rangeNotes.filter((n) => n.start >= rangeStart).sort((a, b) => a.start - b.start);
  const targetPoints = noteGrid(score, rangeStart, shownBars[0]?.end ?? rangeEnd, gridQuarters || .5);
  const targetTime = targetPoints[targetSlot] ?? rangeStart;
  const phraseDelta = (phraseNotes[0]?.start ?? targetTime) - targetTime;
  const firstNoteBar = bars.find((bar) => phraseNotes[0] && bar.start <= phraseNotes[0].start && phraseNotes[0].start < bar.end);
  const carriedNote = rangeNotes.some((n) => n.start < rangeStart);
  const canShift = !!firstNoteBar && !carriedNote && phraseDelta > 1e-8 && phraseDelta < firstNoteBar.end - firstNoteBar.start - 1e-8;
  useEffect(() => { setTargetSlot(0); }, [rangeStart, rangeEnd, gridQuarters]);
  const firstWithNotes = barNoteCounts.findIndex((count) => count > 0);
  const nextWithNotes = barNoteCounts.findIndex((count, i) => i > barIndex && count > 0);
  function showNotes(index: number) {
    if (index < 0) return;
    props.onStop(); setWindowStart(bars[index].start);
    const note = score.melody.find((n) => n.start < bars[index].end && n.end > bars[index].start);
    if (note) setSelectedId(note.id);
  }
  const clock = notationClock(score);
  useEffect(() => {
    if (selected) { setMidi(selected.midi); setStart(String(selected.start)); setEnd(String(selected.end)); setTabString(selected.string ?? 1); setTabFret(selected.fret ?? 0); setExplicitTab(false); }
    else setSelectedId(null);
  }, [selected]);

  function selectNote(id: string) {
    props.onStop(); setSelectedId(id); setMessage("");
    // Selecting a note does not move the paused transport or restart playback.
  }

  function setPosition(string: number, fret: number) {
    props.onStop(); setTabString(string); setTabFret(fret); setExplicitTab(true);
    setMidi(score.guitar.tuning[6 - string] + score.analysis.capo + fret);
  }

  function insertOnTab(time: number, string: number) {
    props.onStop(); setSelectedId(null); props.onSeek(time);
    setStart(String(time)); setEnd(String(Math.min(score.song.duration_seconds, clock.endAfter(time, gridQuarters || 1))));
    setPosition(string, 0);
    setMessage(gridQuarters ? "新增起點已吸附格線，預設音長一格；可再修改音長後按 Add note。既有音符不變。" : "自由定位：設定品格與音長後按 Add note。空白不自動視為休止。");
  }

  function moveDraft(direction: number) {
    props.onStop();
    const nextStart = clock.endAfter(Number(start), direction * gridQuarters);
    const nextEnd = clock.endAfter(Number(end), direction * gridQuarters);
    if (nextStart < 0 || nextEnd > score.song.duration_seconds) { setMessage("移動後超出歌曲範圍，草稿未變更。"); return; }
    setStart(String(nextStart)); setEnd(String(nextEnd));
    props.onSeek(nextStart);
    setMessage("已移動草稿一格，尚未套用；確認後按 Add note 或 Apply note。");
  }

  function newNote() {
    setExplicitTab(false);
    setSelectedId(null);
    setStart(String(props.playhead));
    const next = score.melody.filter((n) => n.start > props.playhead).sort((a, b) => a.start - b.start)[0];
    setEnd(String(Math.min(score.song.duration_seconds, props.playhead + 0.5, next?.start ?? Infinity)));
    setMessage("設定音高與起迄，再按 Add note。音高是目前譜面 Key 的實際發聲音高；不自動吸附拍點。");
  }

  async function edit(operation: "add" | "update" | "delete" | "split" | "merge_next" | "shift_phrase") {
    if (inFlight.current) return;
    props.onStop();
    if (["add", "update"].includes(operation) && (!start.trim() || !end.trim() || !Number.isFinite(Number(start)) || !Number.isFinite(Number(end)))) {
      setMessage("請填入有效起點與終點。"); return;
    }
    if ((operation === "add" || operation === "update") && conflict) {
      setMessage(`尚未套用：${conflictMessage}`); return;
    }
    inFlight.current = true; setBusy(true); setMessage("");
    const base = score;
    try {
      const response = await fetch(`${props.apiBase}/scores/melody/edit`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score: base, operation, note_id: selected?.id ?? null,
          ...(operation === "add" || operation === "update" ? { midi, start: Number(start), end: Number(end) } : {}),
          ...(explicitTab && (operation === "add" || operation === "update") ? { string: tabString, fret: tabFret } : {}),
          ...(operation === "split" ? { split_time: props.playhead } : {}),
          ...(operation === "shift_phrase" ? { range_start: rangeStart, range_end: rangeEnd, target_start: targetTime } : {}), source_job_id: props.jobId ?? null }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : Array.isArray(body.detail)
        ? body.detail.map((item: { loc?: Array<string | number>; msg?: string }) => `${item.loc?.slice(1).join(".") ?? "欄位"}: ${item.msg ?? "格式不符"}`).join("；")
        : `新增／修改失敗（HTTP ${response.status}），請檢查音高與時間。`);
      if (!props.onCommit(base, body.score)) {
        setMessage("樂譜已在其他操作中改變，本次較舊的回應未套用。請重新操作。"); return;
      }
      setSelectedId(body.selected_note_id);
      if (operation === "shift_phrase") props.onSeek(targetTime);
      setMessage(operation === "shift_phrase" ? `已將 ${phraseNotes.length} 個音符整段前移 ${phraseDelta.toFixed(3)} 秒，可一次 Undo；尚未保存。原曲、和弦及小節線未移動。` : "已修改工作樂譜，尚未保存。原曲與 Contour 不變；用「重播所選小節」聽修改結果。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Edit failed"); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <details className="melody-editor workspace-disclosure">
    <summary>旋律人工編輯 · Melody editor</summary>
    <p>聽一段 → 暫停 → 點六線譜數字修改 → 重播所選小節。上方為第 1 弦，品格相對 Capo {score.analysis.capo}；橫線尾巴表示持續時間，⌒ 表示跨小節延續。</p>
    <p><strong>時間比例六線譜草稿，尚非傳統節奏排版。</strong>弦上的數字是「品格」，不是簡譜音級；例如第 4 弦的 5，就是彈第 4 弦第 5 格。</p>
    <details className="tab-reading-guide"><summary>怎麼讀這張譜？</summary>
      <ul>
        <li>六條橫線由上到下是第 1–6 弦；方框數字 0 表示空弦，其餘是相對 Capo 的品格。</li>
        <li>上方 1、2、3、4 與垂直虛線是推定拍點，Bar 是一個小節。方框的左右位置表示起音時間。</li>
        <li>綠色尾線是音符持續時間；橘色直線是播放位置，發聲中的音符會亮起。</li>
        <li>≈¼、≈⅛、≈½ 分別表示接近四分、八分、二分音符；· 表示附點。這是近似音長標籤，不是品格或拍號。</li>
        <li>⌒ 表示同一個音跨小節延續，不是重新彈一次；空白不保證是休止，也可能是漏抓。</li>
      </ul>
      <p>尚未提供傳統符桿、連桿與完整休止記號，也不是簡譜。這一版先用實際時間保留尚未校正的分析結果。</p>
    </details>
    <div className="editor-actions">
      <label>起始小節<select aria-label="Tab start bar" value={barIndex} onChange={(e) => { props.onStop(); setWindowStart(bars[Number(e.target.value)].start); }}>{bars.map((bar, i) => <option key={bar.start} value={i}>Bar {bar.number} · {barNoteCounts[i]} 音符</option>)}</select></label>
      <label>段落長度<select aria-label="Tab bar count" value={barCount} onChange={(e) => { props.onStop(); setBarCount(Number(e.target.value)); }}>{[1, 2, 4, 8].map((n) => <option key={n} value={n}>{n} 小節</option>)}</select></label>
      <label>滑鼠定位格線<select aria-label="Tab snap grid" value={gridQuarters} onChange={(e) => setGridQuarters(Number(e.target.value))}><option value="1">四分音符</option><option value="0.5">八分音符（預設）</option><option value="0.25">十六分音符</option><option value="0">自由定位（不吸附）</option></select></label>
      <button type="button" onClick={() => setWindowStart(props.playhead)}>顯示暫停位置</button>
      <label><input type="checkbox" aria-label="Loop edited bars" checked={loop} onChange={(e) => { props.onStop(); setLoop(e.target.checked); }} />循環修訂段落</label>
    </div>
    <BarTimingEditor score={score} bars={shownBars} playhead={props.playhead} onStop={props.onStop}
      onSeek={props.onSeek} onOriginal={props.onOriginal} onCommit={props.onCommit} />
    <div className="melody-coverage" aria-label="旋律資料狀態">
      <p>工作樂譜共 {score.melody.length} 個旋律音符；所選小節有 {rangeNotes.length} 個。{props.jobId ? `來源分析：${props.jobId}` : "目前版本未附來源分析 ID。"}</p>
      {!rangeNotes.length ? <p role="status">{score.melody.length ? "所選小節沒有旋律音符可修改。空白可能是未抓到旋律，不代表歌曲沒有旋律，也不會從 Contour 自動產生音符。請跳到有音符的小節，或點空白弦線手動補音。" : "目前工作樂譜沒有旋律音符。Contour 有聲音不代表已產生可編輯音符；可載入先前修訂，或點空白弦線、設定品格及音長，再按 Add note 補入。"}</p> : <p>直接點弦上的品格數字，再到下方改弦／品格或音長，按 Apply note；無指型音符會列在弦線下方。</p>}
      <div className="editor-actions">
        <button type="button" disabled={firstWithNotes < 0} onClick={() => showNotes(firstWithNotes)}>跳到第一個有音符的小節</button>
        <button type="button" disabled={nextWithNotes < 0} onClick={() => showNotes(nextWithNotes)}>下一個有音符的小節</button>
      </div>
    </div>
    <div className="editor-actions">
      <button type="button" onClick={() => props.onAudition(rangeStart, rangeEnd, loop)}>重播所選小節</button>
      <button type="button" onClick={props.onStop}>暫停，保留位置</button>
      <button type="button" onClick={() => props.onAudition(props.playhead >= rangeStart && props.playhead < rangeEnd ? props.playhead : rangeStart, rangeEnd)}>從暫停位置續播</button>
      <button type="button" onClick={() => props.onOriginal(rangeStart, rangeEnd)}>對照來源片段</button>
    </div>
    <p aria-label="Tab transport position">位置 {props.playhead.toFixed(2)}s · 所選 {rangeStart.toFixed(2)}–{rangeEnd.toFixed(2)}s。修訂播放只有旋律；來源使用上方選定的音軌。小節／音長依推定拍點顯示，未自動量化。譜面區內跟隨播放，不跳到和弦區；可選 4 或 8 小節。</p>
    <p>格線只吸附「點空白弦線新增」的位置，不移動既有音符；依目前拍點換算，不是固定毫秒。選錯位置可用下方前／後移一格。音長若碰到原音尾端仍需確認，不自動截短或覆蓋。</p>
    <EditableTab score={score} bars={shownBars} selectedId={selectedId} playhead={props.playhead} onSelect={selectNote} onInsert={insertOnTab} gridQuarters={gridQuarters} />
    <details className="phrase-shift"><summary>移除段落前方空白（整段前移）</summary>
      <p>範圍使用上方所選小節：{rangeStart.toFixed(3)}–{rangeEnd.toFixed(3)} 秒。只移動起音位於這段的 {phraseNotes.length} 個音符；結尾跨小節的音符也完整移動，不截斷。</p>
      <label>第一音移到<select aria-label="Phrase target position" value={Math.min(targetSlot, Math.max(0, targetPoints.length - 1))} onChange={(e) => setTargetSlot(Number(e.target.value))}>{targetPoints.map((time, index) => <option key={time} value={index}>Bar {shownBars[0]?.number} · {index === 0 ? "小節起點" : `第 ${index + 1} 格`}（{time.toFixed(3)}s）</option>)}</select></label>
      <p aria-label="Phrase shift preview">{phraseNotes.length ? `第一音 ${phraseNotes[0].note}：${phraseNotes[0].start.toFixed(3)} → ${targetTime.toFixed(3)} 秒；整段前移 ${Math.max(0, phraseDelta).toFixed(3)} 秒。` : "所選段落沒有音符。"}所有音長、音符間距、音高及弦／格保持不變。</p>
      {!canShift ? <p>{carriedNote ? "段落開頭有延續音，不是空白；請往前擴大選取。" : "需要有前方空白，且移動量小於第一音所在的一個小節；請調整起始小節或目標格點。"}</p> : null}
      <p>這會改變旋律相對原曲／和弦的時間；原音訊、小節線、和弦與段落外音符不動。不會把整首歌曲自動提前。</p>
      <button type="button" disabled={busy || !canShift} onClick={() => void edit("shift_phrase")}>套用整段前移</button>
    </details>
    <fieldset disabled={busy}>
      <legend>{selected ? `譜上選音：${selected.note}` : "點譜上數字修改，或點空白弦線補音"}</legend>
      <div className="melody-edit-fields">
        <label>弦<select aria-label="Tab string" value={tabString} onChange={(e) => setPosition(Number(e.target.value), tabFret)}>{[1,2,3,4,5,6].map((n) => <option key={n} value={n}>第 {n} 弦</option>)}</select></label>
        <label>品格<input aria-label="Tab fret" type="number" min="0" max={score.guitar.max_fret} step="1" value={tabFret} onChange={(e) => setPosition(tabString, Number(e.target.value))} /></label>
        <label>音長<select aria-label="Tab note length" value="" onChange={(e) => { props.onStop(); setEnd(String(clock.endAfter(Number(start), Number(e.target.value)))); }}><option value="">保留目前音長</option>{noteLengths.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select></label>
      </div>
      <p>修改草稿：{pitches[midi]?.label ?? "超出音域"} · {lengthLabel(score, Number(start), Number(end))}（套用前譜面不變）</p>
      <p>{selected ? "修改既有音符：按 Apply note" : "新增音符：按 Add note"} · 位置 {Number(start).toFixed(3)}–{Number(end).toFixed(3)} 秒</p>
      <div className="editor-actions"><button type="button" disabled={!gridQuarters} onClick={() => moveDraft(-1)}>前移一格</button><button type="button" disabled={!gridQuarters} onClick={() => moveDraft(1)}>後移一格</button></div>
      {conflict ? <div className="melody-coverage" aria-label="音符重疊提示">
        <p>{conflictMessage}</p>
        <div className="editor-actions">
          <button type="button" onClick={() => selectNote(conflict.id)}>選取衝突音符來修改</button>
          {!selected && conflict.start - Number(start) >= .01 ? <button type="button" onClick={() => { setEnd(String(conflict.start)); setMessage("已縮短新增草稿到下一音符前，尚未新增；確認後按 Add note。"); }}>將新增音符縮短至下一音符前</button> : null}
        </div>
      </div> : null}
      <div className="editor-actions">
        <button type="button" onClick={() => props.onPitch(midi)}>預聽音高</button>
        <button type="button" onClick={() => void edit(selected ? "update" : "add")}>{selected ? "Apply note" : "Add note"}</button>
        <button type="button" disabled={!selected} onClick={() => void edit("delete")}>Delete note</button>
      </div>
    </fieldset>
    <div className="editor-actions">
      <button type="button" disabled={!props.canUndo} onClick={() => { props.onStop(); props.onUndo(); }}>Undo melody edit</button>
      <button type="button" disabled={!props.canRedo} onClick={() => { props.onStop(); props.onRedo(); }}>Redo melody edit</button>
    </div>
    <p role="status">{message}</p>
    <details><summary>進階：秒數、音高與音符清單</summary>
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
        <label>音高<select aria-label="Melody pitch" value={midi} onChange={(e) => { setMidi(Number(e.target.value)); setExplicitTab(false); }}>{pitches.map((p) => <option key={p.midi} value={p.midi}>{p.label} · {p.midi}</option>)}</select></label>
        <label>起點（秒）<input aria-label="Melody note start" type="number" min="0" step="0.01" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>終點（秒）<input aria-label="Melody note end" type="number" min="0" step="0.01" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      <p>長度：{Number.isFinite(Number(end) - Number(start)) ? (Number(end) - Number(start)).toFixed(3) : "—"} 秒{selected && (selected.string == null || selected.fret == null) ? " · 目前吉他設定無可用指型；音符仍保留，可修改音高／調弦／把位。" : ""}</p>
      <div className="editor-actions">
        <button type="button" onClick={newNote}>New at playhead</button>
        <button type="button" disabled={!selected || props.playhead <= selected.start || props.playhead >= selected.end} onClick={() => void edit("split")}>Split at playhead</button>
        <button type="button" disabled={!selected} onClick={() => void edit("merge_next")}>Merge next same pitch</button>
      </div>
    </fieldset>
    <div className="editor-actions">
      <button type="button" onClick={() => props.onAudition(left, right)}>試聽修訂片段</button>
      <button type="button" onClick={props.onStop}>停止修訂試聽</button>
    </div>
    <p>片段試聽只播放目前工作樂譜的旋律、原速、不加吉他。Undo／Redo 共用整份樂譜的歷史。</p>
    </details>
    <div className="editor-actions">
      <label>版本 ID<input aria-label="Melody revision ID" value={props.revisionId} onChange={(e) => props.onRevisionId(e.target.value)} /></label>
      <button type="button" disabled={busy || props.saving} onClick={props.onSave}>Save new revision</button>
      <button type="button" disabled={busy || props.saving || !props.revisionId.trim()} onClick={props.onLoad}>Load melody revision</button>
    </div>
    <p>{props.saveStatus}</p>
  </details>;
}
