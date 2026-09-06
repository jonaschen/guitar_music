import { expect, test } from "@playwright/test";

const score = {
  schema_version: "1.0",
  song: { title: "Browser test song", source_type: "local", duration_seconds: 8 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: 1, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner" },
  beats: [{ time: 0, beat: 1, measure: 1, confidence: 1 }, { time: 0.5, beat: 2, measure: 1, confidence: 1 }, { time: 1, beat: 1, measure: 2, confidence: 1 }],
  chords: [{ id: "c1", start: 0, end: 2, symbol: "C", confidence: 1, origin: "model", edited: false, voicing_id: null, available_voicings: [] }],
  melody: [{ id: "n1", start: 0, end: 0.5, midi: 60, note: "C4", confidence: 1, string: 2, fret: 1, origin: "model", edited: false }],
  rhythm: { subdivision: 8, pattern_id: "basic_8th", display: ["D", null, "D", "U"], confidence: 1, label: "Basic pattern" },
  provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
};

test("renders an analyzed score workspace", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("guitarscribe.activeJobId", "demo-job"));
  await page.route("**/api/v1/jobs/demo-job", (route) => route.fulfill({ json: { id: "demo-job", status: "completed", progress: 100, message: "Analysis complete", melody_mode: "vocal", chord_complexity: "standard", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", error: null, score } }));
  await page.route("**/scores/transpose", (route) => route.fulfill({ json: { ...score, analysis: { ...score.analysis, key: "D" }, key_context: { ...score.key_context, target: { key: "D", mode: "major" }, shape: { key: "D", mode: "major" }, sounding: { key: "D", mode: "major" }, transpose_semitones: 2, audio_matches_notation: false }, chords: [{ ...score.chords[0], symbol: "D", shape_symbol: "D", source_symbol: "C" }] } }));
  await page.route("**/chord-voicings?*", (route) => route.fulfill({ json: [{ id: "closed-e-major-c", symbol: "C", shape_symbol: "C", frets: [8, 10, 10, 9, 8, 8], fingers: [1, 3, 4, 2, 1, 1], base_fret: 8, capo: 0, difficulty: 3.5, tags: ["closed", "barre", "e-shape"] }] }));
  const lyricScore = { ...score, lyrics: { id: "lyrics-1", language: "und", source: "manual", timing_level: "none", raw_text: "One", revision: 1, lines: [{ id: "line-1", order: 0, start: null, end: null, text: "One", confidence: 1, origin: "user", edited: true }] } };
  await page.route("**/scores/lyrics/import-text", (route) => route.fulfill({ json: lyricScore }));
  await page.route("**/scores/lyrics/distribute-timing", (route) => route.fulfill({ json: { ...lyricScore, lyrics: { ...lyricScore.lyrics, revision: 2, lines: [{ ...lyricScore.lyrics.lines[0], start: 0, end: 8 }] } } }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Browser test song" })).toBeVisible();
  await expect(page.getByText("Guitar settings")).toBeVisible();
  await expect(page.getByText("Rhythm suggestion")).toBeVisible();
  await expect(page.getByText("Estimated score preview")).toBeVisible();
  await expect(page.getByRole("button", { name: "C4 in bar 1" })).toBeVisible();
  await expect(page.getByText("Playable Tab")).toBeVisible();
  await expect(page.locator(".chord-sheet .measure-header", { hasText: "Bar 2" })).toBeVisible();
  await expect(page.getByText("Continues")).toHaveCount(2);
  await expect(page.locator(".chord-block").first()).toBeVisible();
  await page.locator(".chord-block").first().click();
  await expect(page.getByRole("heading", { name: "Edit C" })).toBeVisible();
  await expect(page.getByText("Start (seconds)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Split chord" })).toBeVisible();
  const timingInputs = page.locator(".timing-fields input");
  await timingInputs.nth(0).fill("0.10");
  await timingInputs.nth(1).fill("1.90");
  await page.getByRole("button", { name: "Save timing" }).click();
  await expect(page.getByRole("button", { name: "Undo" })).toBeEnabled();
  await expect(page.getByText("Position 8 · Difficulty 3.5/5")).toBeVisible();
  await page.getByText("Position 8 · Difficulty 3.5/5").click();
  await expect(page.getByText("Selected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Selected", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(timingInputs.nth(0)).toHaveValue("0.00");
  await page.locator(".toolbar-actions button").last().click();
  await expect(page.locator(".toolbar-block").nth(1)).toContainText("D major");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".toolbar-block").nth(1)).toContainText("C major");
  await page.locator(".lyrics-panel textarea").fill("One");
  await page.getByRole("button", { name: "Import lyrics" }).click();
  await expect(page.getByRole("button", { name: "One", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Distribute timing" }).click();
  await expect(page.getByText("0.0–8.0")).toBeVisible();
});
