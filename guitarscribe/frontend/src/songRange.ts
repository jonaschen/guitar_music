import type { SongScore } from "./types";

export function songBounds(score: SongScore | null) {
  return score?.song_range ?? { start: 0, end: score?.song.duration_seconds ?? 0 };
}

export function clipRange(start: number, end: number, score: SongScore) {
  const bounds = songBounds(score);
  return { start: Math.max(bounds.start, start), end: Math.min(bounds.end, end) };
}
