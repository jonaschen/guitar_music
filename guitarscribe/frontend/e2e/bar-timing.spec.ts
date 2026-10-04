import { expect, test } from "@playwright/test";
import { retimeBars } from "../src/barTiming";
import type { SongScore } from "../src/types";

const score: SongScore = {
  schema_version: "1.0", song: { title: "Timing test", source_type: "local", duration_seconds: 20 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: .4, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40,45,50,55,59,64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
  beats: Array.from({ length: 40 }, (_, i) => ({ time: i / 2, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
  chords: [{ id: "c1", start: 0, end: 16, symbol: "C", confidence: .5, origin: "model", edited: false }],
  melody: [{ id: "n1", start: 0, end: .5, midi: 60, note: "C4", confidence: .4, string: 2, fret: 1, origin: "model", edited: false }],
  rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
  provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
};
const anchors = Array.from({ length: 9 }, (_, i) => ({ measure: i + 1, time: i * 2 }));

test("retiming changes only shared beats and records provenance without mutating source", () => {
  const before = structuredClone(score);
  const result = retimeBars(score, anchors.map(a => a.measure === 2 ? { ...a, time: 2.4 } : a));
  expect(result.beats[4].time).toBe(2.4);
  expect(result.beats[5].time).toBeCloseTo(2.8);
  expect(result.beats.slice(32)).toEqual(score.beats.slice(32));
  expect(result.melody).toBe(score.melody);
  expect(result.chords).toBe(score.chords);
  expect(result.provenance.parameters?.timing_origin).toBe("user");
  expect(score).toEqual(before);
});

test("rejects crossing, nonfinite, missing beats, outer shifts and tiny beat gaps", () => {
  for (const time of [4, NaN, Infinity, .01]) {
    expect(() => retimeBars(score, anchors.map(a => a.measure === 2 ? { ...a, time } : a))).toThrow();
  }
  expect(() => retimeBars(score, anchors.map(a => a.measure === 1 ? { ...a, time: .1 } : a))).toThrow();
  expect(() => retimeBars({ ...score, beats: score.beats.filter((_, i) => i !== 5) }, anchors)).toThrow();
  expect(() => retimeBars(score, anchors.slice(0, 2))).toThrow();
});

test("preserves uneven pulse fractions unless evenly spaced explicitly", () => {
  const uneven = { ...score, beats: score.beats.map((b, i) => i === 1 ? { ...b, time: .6 } : b) };
  expect(retimeBars(uneven, anchors).beats[1].time).toBe(.6);
  expect(retimeBars(uneven, anchors, true).beats[1].time).toBe(.5);
});

test("eight-bar boundaries support validation, undo, redo and revision reload", async ({ page }) => {
  let saved: SongScore | undefined;
  await page.route("**/api/v1/jobs/timing", r => r.fulfill({ json: { id: "timing", status: "completed", progress: 100, artifacts: [], score } }));
  await page.route("**/rhythm-patterns?*", r => r.fulfill({ json: [] }));
  await page.route("**/revisions", r => {
    expect(r.request().postDataJSON().create_new).toBe(true);
    saved = r.request().postDataJSON().score;
    return r.fulfill({ json: { revision_id: "timing-edit" } });
  });
  await page.route("**/revisions/timing-edit", r => r.fulfill({ json: saved }));
  await page.goto("/?job=timing");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("8");
  await page.getByText("所選小節分界校正（不移動音符）", { exact: true }).click();
  const boundary = page.getByLabel("Bar 2 boundary seconds", { exact: true });
  const apply = page.getByRole("button", { name: "套用小節分界", exact: true });
  await boundary.fill("4");
  await expect(apply).toBeDisabled();
  await boundary.fill("2.4");
  await apply.click();
  await expect(page.getByText("已校正工作譜拍點", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(boundary).toHaveValue("2");
  await page.getByRole("button", { name: "Redo melody edit", exact: true }).click();
  await expect(boundary).toHaveValue("2.4");
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("timing-edit");
  expect(saved?.beats[4].time).toBe(2.4);
  expect(saved?.melody).toEqual(score.melody);
  expect(saved?.chords).toEqual(score.chords);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  await expect(boundary).toHaveValue("2.4");
});
