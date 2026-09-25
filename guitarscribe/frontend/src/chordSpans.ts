import type { SongScore } from "./types";

type Chord = SongScore["chords"][number];
export type ChordSpan = { chord: Chord | null; start: number; end: number; continues: boolean; members: Chord[] };

function shape(chord: Chord) {
  const selected = chord.available_voicings?.find((v) => v.id === chord.voicing_id) ?? chord.available_voicings?.[0];
  return JSON.stringify([chord.shape_symbol ?? chord.symbol, selected?.frets ?? chord.voicing_id ?? null]);
}

// Presentation only: never rewrite detector segments or their editable IDs.
export function mergeChordSpans(spans: ChordSpan[]): ChordSpan[] {
  const result: ChordSpan[] = [];
  for (const span of spans) {
    const previous = result[result.length - 1];
    if (previous?.chord && span.chord && previous.chord.symbol === span.chord.symbol
        && shape(previous.chord) === shape(span.chord) && Math.abs(previous.end - span.start) < 1e-9) {
      previous.end = span.end;
      previous.continues ||= span.continues;
      previous.members.push(...span.members);
    } else result.push({ ...span, members: [...span.members] });
  }
  return result;
}
