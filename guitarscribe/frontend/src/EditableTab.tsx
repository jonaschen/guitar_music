import type { SongScore } from "./types";
import { useEffect, useRef } from "react";
import { lengthLabel, notationBars } from "./melodyNotation";

export function EditableTab({ score, bars, selectedId, playhead, onSelect, onInsert }: {
  score: SongScore; bars: ReturnType<typeof notationBars>; selectedId: string | null; playhead: number;
  onSelect: (id: string) => void; onInsert: (time: number, string: number) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const activeBar = bars.find((bar) => playhead >= bar.start && playhead < bar.end)?.start;
  useEffect(() => {
    const container = viewport.current;
    const bar = container?.querySelector<HTMLElement>(`[data-bar-start="${activeBar}"]`);
    if (!container || !bar) return;
    const view = container.getBoundingClientRect(), box = bar.getBoundingClientRect();
    if (box.top < view.top || box.bottom > view.bottom) {
      container.scrollTop += box.top - view.top;
    }
  }, [activeBar]);
  return <div ref={viewport} className="editable-tab" aria-label="可編輯六線譜">
    {bars.map((bar) => {
      const notes = score.melody.filter((n) => n.start < bar.end && n.end > bar.start);
      const width = Math.max(350, notes.length * 45);
      const x = (time: number) => 38 + Math.max(0, Math.min(1, (time - bar.start) / (bar.end - bar.start))) * (width - 66);
      return <section className="editable-tab-bar" data-bar-start={bar.start} key={bar.start} aria-label={`六線譜 Bar ${bar.number}`}>
        <strong>Bar {bar.number} · {bar.start.toFixed(1)}–{bar.end.toFixed(1)}s</strong>
        {!notes.length ? <p className="tab-empty">此小節沒有旋律音符。點弦線可補音。</p> : <p>{notes.length} 音符 · 點品格數字修改{notes.some((n) => n.string == null || n.fret == null) ? "；無指型音符在下方" : ""}</p>}
        <div className="editable-tab-scroll"><div className="editable-tab-staff" style={{ width }}>
          {score.beats.filter((b) => b.time >= bar.start && b.time < bar.end).map((b) => <span key={b.time} className="editable-tab-beat" style={{ left: x(b.time) }}><small>{b.beat}</small></span>)}
          {[1, 2, 3, 4, 5, 6].map((string) => <button type="button" className="editable-tab-string" key={string} style={{ top: 36 + (string - 1) * 32 }} aria-label={`Bar ${bar.number} 第 ${string} 弦新增音符`}
            onClick={(event) => { const rect = event.currentTarget.getBoundingClientRect(); const fraction = Math.max(0, Math.min(.999, (event.clientX - rect.left - 38) / (width - 66))); onInsert(bar.start + fraction * (bar.end - bar.start), string); }}>
            <span>{string}</span>
          </button>)}
          {notes.map((note) => {
            const top = note.string ? 36 + (note.string - 1) * 32 : 244;
            const from = Math.max(bar.start, note.start), to = Math.min(bar.end, note.end);
            return <div key={note.id}>
              <span className="editable-tab-duration" style={{ left: x(from), top, width: Math.max(1, x(to) - x(from)) }} />
              <button type="button" className={"editable-tab-note" + (playhead >= note.start && playhead < note.end ? " sounding" : "")}
                style={{ left: x(from), top }} aria-pressed={selectedId === note.id}
                aria-label={`Tab ${note.id} ${note.note} ${note.string ? `${note.string}弦${note.fret}格` : "無指型"}`}
                title={`${note.note} · ${lengthLabel(score, note.start, note.end)} · ${note.start.toFixed(2)}–${note.end.toFixed(2)}s`}
                onClick={() => onSelect(note.id)}>{note.start < bar.start ? "⌒" : ""}{note.fret ?? note.note}{note.end > bar.end ? "⌒" : ""}<small>{lengthLabel(score, note.start, note.end, true)}</small></button>
            </div>;
          })}
          {playhead >= bar.start && playhead < bar.end ? <span className="editable-tab-cursor" style={{ left: x(playhead) }} /> : null}
        </div></div>
      </section>;
    })}
  </div>;
}
