import { expect, test, type Page, type Route } from "@playwright/test";

const score = {
  schema_version: "1.0", song: { title: "Editor test", source_type: "local", duration_seconds: 8 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: 0.4, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
  beats: [0, 0.5, 1, 1.5].map((time, i) => ({ time, beat: i + 1, measure: 1, confidence: 1 })),
  chords: [], melody: [{ id: "n1", start: 0, end: 0.5, midi: 60, note: "C4", confidence: 0.4, string: 2, fret: 1, origin: "model", edited: false }],
  rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
  provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
};

async function setup(page: Page, empty = false) {
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score, melody: empty ? [] : score.melody },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
}

function answer(route: Route) {
  const body = route.request().postDataJSON();
  const result = structuredClone(body.score);
  if (body.operation === "delete") {
    result.melody = result.melody.filter((n: any) => n.id !== body.note_id);
    return { score: result, selected_note_id: null };
  }
  const name: Record<number, string> = { 60: "C4", 62: "D4", 64: "E4", 65: "F4", 67: "G4" };
  const note = { id: body.operation === "add" ? "new-note" : body.note_id,
    midi: body.midi, note: name[body.midi], start: body.start, end: body.end,
    confidence: 0.4, origin: "user", edited: true, string: 1, fret: 0 };
  result.melody = body.operation === "add" ? [...result.melody, note] : result.melody.map((n: any) => n.id === note.id ? note : n);
  return { score: result, selected_note_id: note.id };
}

test("edit pitch and duration, audition, undo, save and reload without a selected chord", async ({ page }) => {
  let saved: any;
  await page.addInitScript(() => {
    (window as any).__noteFrequencies = [];
    const original = AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime = function(value, time) {
      if (value > 20) (window as any).__noteFrequencies.push(value);
      return original.call(this, value, time);
    };
  });
  await page.route("**/scores/melody/edit", (route) => route.fulfill({ json: answer(route) }));
  await page.route("**/revisions", (route) => {
    const body = route.request().postDataJSON();
    expect(body.create_new).toBe(true);
    saved = structuredClone(body.score);
    return route.fulfill({ json: { revision_id: "saved-edit" } });
  });
  await page.route("**/revisions/saved-edit", (route) => route.fulfill({ json: saved }));
  await setup(page);
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByLabel("Melody note end").fill("0.75");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.75s · Edited", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "試聽修訂片段", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__noteFrequencies.some((f: number) => Math.abs(f - 329.6276) < 0.01))).toBe(true);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Redo melody edit", exact: true }).click();
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("saved-edit");
  expect(saved.melody[0].midi).toBe(64);
  expect(saved.melody[0].end).toBe(0.75);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.75s · Edited", exact: true })).toBeVisible();
  await page.reload();
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("saved-edit");
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.75s · Edited", exact: true })).toBeVisible();
});

test("empty melody can be filled, deleted and restored; invalid edit preserves notes", async ({ page }) => {
  await page.route("**/scores/melody/edit", (route) => {
    const body = route.request().postDataJSON();
    return body.operation === "update" && body.end <= body.start
      ? route.fulfill({ status: 422, json: { detail: "End must follow start" } })
      : route.fulfill({ json: answer(route) });
  });
  await setup(page, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "New at playhead", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("67");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByRole("button", { name: "G4 · 0.00–0.50s · Edited", exact: true })).toBeVisible();
  await page.getByLabel("Melody note end").fill("0");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(page.getByText("End must follow start", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "G4 · 0.00–0.50s · Edited", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete note", exact: true }).click();
  await expect(page.getByText("此片段沒有音符，可用 New at playhead 補入。")).toBeVisible();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "G4 · 0.00–0.50s · Edited", exact: true })).toBeVisible();
});

test("late edit response cannot overwrite Undo", async ({ page }) => {
  let held: Route | undefined;
  await page.route("**/scores/melody/edit", (route) => {
    if (route.request().postDataJSON().midi === 65) { held = route; return; }
    return route.fulfill({ json: answer(route) });
  });
  await setup(page);
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.50s · Edited", exact: true })).toBeVisible();
  await page.getByLabel("Melody pitch").selectOption("65");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect.poll(() => !!held).toBe(true);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await held!.fulfill({ json: answer(held!) });
  await expect(page.getByText(/本次較舊的回應未套用/)).toBeVisible();
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
});
