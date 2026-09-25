import type { SongScore } from "./types";

// Interpolate within the detected beats, not uniformly in seconds: a slower
// third beat must still occupy one beat of notation. No score times are edited.
export function measureLayout(allBeats: SongScore["beats"], start: number, end: number, bpm: number) {
  const beats = allBeats.filter((beat) => beat.time >= start && beat.time < end).sort((a, b) => a.time - b.time);
  const duration = Math.max(end - start, 0.001);
  if (!beats.length) return {
    ticks: [] as Array<{ beat: number; fraction: number }>,
    fraction: (time: number) => Math.max(0, Math.min(1, (time - start) / duration)),
    length: (from: number, to: number) => `${(to - from).toFixed(1)}s`,
  };
  const first = beats[0].beat;
  const last = beats[beats.length - 1];
  const boundaryKnown = allBeats.some((beat) => Math.abs(beat.time - end) < 1e-8);
  const lastInterval = beats.length > 1 ? (last.time - beats[beats.length - 2].time) / Math.max(1, last.beat - beats[beats.length - 2].beat) : 60 / Math.max(bpm, 1);
  const total = Math.max(0.001, last.beat - first + (boundaryKnown ? 1 : (end - last.time) / Math.max(lastInterval, 0.001)));
  const knots = [...beats.map((beat) => ({ time: beat.time, position: beat.beat - first })), { time: end, position: total }];
  const position = (time: number) => {
    if (time <= start) return 0;
    if (time >= end) return total;
    const right = knots.findIndex((knot) => knot.time > time);
    if (right <= 0) return 0;
    const a = knots[right - 1], b = knots[right];
    return a.position + (time - a.time) / (b.time - a.time) * (b.position - a.position);
  };
  return {
    ticks: beats.map((beat) => ({ beat: beat.beat, fraction: position(beat.time) / total })),
    fraction: (time: number) => position(time) / total,
    length: (from: number, to: number) => {
      const count = position(to) - position(from);
      const rounded = Math.round(count * 100) / 100;
      return `${Math.abs(count - rounded) > 0.001 ? "約 " : ""}${rounded} 拍`;
    },
  };
}
