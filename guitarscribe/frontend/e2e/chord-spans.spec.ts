import { expect, test } from "@playwright/test";
import { mergeChordSpans, type ChordSpan } from "../src/chordSpans";

function spans(symbols: string[]): ChordSpan[] {
  return symbols.map((symbol, index) => {
    const chord = { id: String(index), symbol, start: index, end: index + 1, confidence: 1, origin: "model", edited: false };
    return { chord, start: index, end: index + 1, continues: false, members: [chord] };
  });
}

test("repeated labels describe sustained harmony, not additional chord changes", () => {
  for (const [input, expected] of [
    [["C", "C", "C"], ["C"]],
    [["Am", "Em", "Em"], ["Am", "Em"]],
    [["G", "Am", "Am", "Am"], ["G", "Am"]],
    [["C", "G", "C"], ["C", "G", "C"]],
  ]) {
    const raw = spans(input);
    const before = JSON.stringify(raw);
    const merged = mergeChordSpans(raw);
    expect(merged.map((span) => span.chord?.symbol)).toEqual(expected);
    expect(merged.flatMap((span) => span.members.map((chord) => chord.id))).toEqual(raw.map((span) => span.chord!.id));
    expect(merged.at(-1)?.end).toBe(input.length);
    expect(JSON.stringify(raw)).toBe(before);
  }
});

test("do not merge across silence, gaps, or different selected shapes", () => {
  const raw = spans(["C", "C"]);
  raw[1].start += 0.01;
  expect(mergeChordSpans(raw)).toHaveLength(2);
  raw[1].start = 1;
  raw[1].chord!.voicing_id = "barre";
  expect(mergeChordSpans(raw)).toHaveLength(2);
  expect(mergeChordSpans([raw[0], { chord: null, members: [], start: 1, end: 2, continues: false }, raw[1]])).toHaveLength(3);
});
