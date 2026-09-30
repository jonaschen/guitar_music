import type { SongScore } from "./types";

// A reversible coordinate map over the detected pulse grid. Reading the map
// never quantizes the score. Duration edits alone opt into these coordinates.
export function notationClock(score: SongScore) {
  const denominator = Number(score.analysis.time_signature.split("/")[1]) || 4;
  const quarterPerPulse = 4 / denominator;
  const times = [...new Set(score.beats.map((b) => b.time))].sort((a, b) => a - b);
  const fallback = 60 / Math.max(1, score.analysis.bpm) * quarterPerPulse;
  if (!times.length) times.push(0);
  function timeAt(pulse: number): number {
    const i = Math.max(0, Math.min(times.length - 1, Math.floor(pulse)));
    const interval = times[i + 1] !== undefined ? times[i + 1] - times[i] : times.length > 1 ? times.at(-1)! - times.at(-2)! : fallback;
    return times[i] + (pulse - i) * interval;
  }
  function pulseAt(time: number): number {
    let i = times.findIndex((t) => t > time) - 1;
    if (i === -2) i = times.length - 1;
    i = Math.max(0, i);
    return i + (time - times[i]) / (timeAt(i + 1) - times[i]);
  }
  return {
    quarterAt: (time: number) => pulseAt(time) * quarterPerPulse,
    timeAtQuarter: (quarter: number) => timeAt(quarter / quarterPerPulse),
    endAfter: (start: number, quarters: number) => timeAt(pulseAt(start) + quarters / quarterPerPulse),
  };
}

export function notationBars(score: SongScore) {
  const starts = new Map<number, number>();
  for (const beat of score.beats) starts.set(beat.measure, Math.min(starts.get(beat.measure) ?? Infinity, beat.time));
  const ordered = [...starts].map(([number, start]) => ({ number, start })).filter((b) => b.start < score.song.duration_seconds).sort((a, b) => a.start - b.start);
  if (!ordered.length) {
    const [beats, unit] = score.analysis.time_signature.split("/").map(Number);
    const seconds = 60 / Math.max(1, score.analysis.bpm) * (beats || 4) * 4 / (unit || 4);
    for (let start = 0; start < score.song.duration_seconds; start += seconds) ordered.push({ number: ordered.length + 1, start });
  } else if (ordered[0].start > 0) ordered.unshift({ number: ordered[0].number - 1, start: 0 });
  return ordered.map((bar, i) => ({ ...bar, end: ordered[i + 1]?.start ?? score.song.duration_seconds }));
}

export const noteLengths = [
  { value: 4, label: "全音符" }, { value: 3, label: "附點二分" },
  { value: 2, label: "二分音符" }, { value: 1.5, label: "附點四分" },
  { value: 1, label: "四分音符" }, { value: .75, label: "附點八分" },
  { value: .5, label: "八分音符" }, { value: .25, label: "十六分音符" },
];

export function lengthLabel(score: SongScore, start: number, end: number, compact = false) {
  const clock = notationClock(score);
  const quarters = clock.quarterAt(end) - clock.quarterAt(start);
  const match = noteLengths.find((l) => Math.abs(l.value - quarters) < .04);
  const symbols: Record<number, string> = { 4: "1", 3: "½·", 2: "½", 1.5: "¼·", 1: "¼", .75: "⅛·", .5: "⅛", .25: "¹⁄₁₆" };
  return match ? `≈${compact ? symbols[match.value] : match.label}` : `${quarters.toFixed(compact ? 1 : 2)} × ♩`;
}
