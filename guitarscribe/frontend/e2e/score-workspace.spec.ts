import { expect, test } from "@playwright/test";

const score = {
  schema_version: "1.0",
  song: { title: "Browser test song", source_type: "local", duration_seconds: 8 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: 1, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner" },
  beats: [{ time: 0, beat: 1, measure: 1, confidence: 1 }, { time: 0.5, beat: 2, measure: 1, confidence: 1 }],
  chords: [{ id: "c1", start: 0, end: 2, symbol: "C", confidence: 1, origin: "model", edited: false, voicing_id: null, available_voicings: [] }],
  melody: [{ id: "n1", start: 0, end: 0.5, midi: 60, note: "C4", confidence: 1, string: 2, fret: 1, origin: "model", edited: false }],
  rhythm: { subdivision: 8, pattern_id: "basic_8th", display: ["D", null, "D", "U"], confidence: 1, label: "Basic pattern" },
  provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
};

test("renders an analyzed score workspace", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("guitarscribe.activeJobId", "demo-job"));
  await page.route("**/api/v1/jobs/demo-job", (route) => route.fulfill({ json: { id: "demo-job", status: "completed", progress: 100, message: "Analysis complete", melody_mode: "vocal", chord_complexity: "standard", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", error: null, score } }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Browser test song" })).toBeVisible();
  await expect(page.getByText("Guitar settings")).toBeVisible();
  await expect(page.getByText("Rhythm suggestion")).toBeVisible();
  await expect(page.getByText("Playable Tab")).toBeVisible();
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
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(timingInputs.nth(0)).toHaveValue("0.00");
});
