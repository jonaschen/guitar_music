import { expect, test, type Page, type Route } from "@playwright/test";
import { notationBars, notationClock } from "../src/melodyNotation";
import type { SongScore } from "../src/types";

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
  await page.getByText("進階：秒數、音高與音符清單", { exact: true }).click();
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
    confidence: 0.4, origin: "user", edited: true, string: body.string ?? 1, fret: body.fret ?? 0 };
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
  await page.getByText("進階：秒數、音高與音符清單", { exact: true }).click();
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
  await expect(page.getByText(/目前工作樂譜沒有旋律音符。Contour/)).toBeVisible();
  await expect(page.getByRole("button", { name: "跳到第一個有音符的小節", exact: true })).toBeDisabled();
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

test("notation clock preserves rubato, pickup and compound meter without mutating notes", () => {
  const fixture = { ...score, beats: [.25, .75, 1.5, 2, 2.5].map((time, i) => ({ time, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })) } as SongScore;
  const before = JSON.stringify(fixture);
  const clock = notationClock(fixture);
  expect(clock.endAfter(.75, 1)).toBe(1.5);
  expect(clock.endAfter(.5, 1)).toBe(1.125);
  for (const time of [0, .5, 1.7, 3]) expect(clock.timeAtQuarter(clock.quarterAt(time))).toBeCloseTo(time);
  expect(notationBars(fixture)[0]).toEqual({ number: 0, start: 0, end: .25 });
  expect(JSON.stringify(fixture)).toBe(before);
  const compound = { ...fixture, analysis: { ...fixture.analysis, time_signature: "6/8" } };
  expect(notationClock(compound).endAfter(.25, .5)).toBe(.75);
  expect(notationClock(compound).endAfter(.25, 1)).toBe(1.5);
  expect(notationBars({ ...fixture, beats: [] })[0]).toEqual({ number: 1, start: 0, end: 2 });
});

test("tab workflow pauses in place, changes fret and duration, auditions and undoes", async ({ page }) => {
  let request: any;
  await page.route("**/scores/melody/edit", (route) => { request = route.request().postDataJSON(); return route.fulfill({ json: answer(route) }); });
  await setup(page);
  await page.getByText("進階：秒數、音高與音符清單", { exact: true }).click();
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  const position = () => page.getByLabel("Tab transport position").innerText().then((s) => Number(s.match(/位置 ([\d.]+)s/)![1]));
  await expect.poll(position).toBeGreaterThan(.1);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  const paused = await position();
  await page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true }).click();
  expect(await position()).toBeCloseTo(paused, 1);
  await page.getByLabel("Tab fret", { exact: true }).fill("3");
  await page.getByLabel("Tab note length").selectOption("0.5");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 D4 2弦3格", exact: true })).toBeVisible();
  expect(request).toMatchObject({ midi: 62, string: 2, fret: 3, start: 0, end: .25 });
  expect(await position()).toBeCloseTo(paused, 1);
  await page.getByRole("button", { name: "從暫停位置續播", exact: true }).click();
  await expect.poll(position).toBeGreaterThan(paused + .08);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toBeVisible();
  await expect(page.getByLabel("Melody note end")).not.toBeVisible();
});

test("tab can insert on an empty string and stay inside mobile viewport", async ({ page }) => {
  let request: any;
  await page.route("**/scores/melody/edit", (route) => { request = route.request().postDataJSON(); return route.fulfill({ json: answer(route) }); });
  await setup(page, true);
  await page.getByText("進階：秒數、音高與音符清單", { exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Bar 1 第 1 弦新增音符", exact: true }).click({ position: { x: 70, y: 12 } });
  await page.getByLabel("Tab fret", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab new-note G4 1弦3格", exact: true })).toBeVisible();
  expect(request).toMatchObject({ midi: 67, string: 1, fret: 3, operation: "add" });
  expect(request.end - request.start).toBeCloseTo(.5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("range loop restarts, pause cancels it, and cross-bar notes remain one editable event", async ({ page }) => {
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score, song: { ...score.song, duration_seconds: 1.6 },
      beats: Array.from({ length: 8 }, (_, i) => ({ time: i * .2, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
      melody: [{ ...score.melody[0], start: .4, end: 1.2 }] },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true }).last().click();
  await expect(page.getByLabel("Tab fret", { exact: true })).toHaveValue("1");
  await page.getByLabel("Tab bar count").selectOption("1");
  await page.getByLabel("Loop edited bars").check();
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  const position = () => page.getByLabel("Tab transport position").innerText().then((s) => Number(s.match(/位置 ([\d.]+)s/)![1]));
  await expect.poll(position, { intervals: [20] }).toBeGreaterThan(.5);
  await expect.poll(position, { intervals: [20] }).toBeLessThan(.3);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  const paused = await position();
  await page.waitForTimeout(950);
  expect(await position()).toBeCloseTo(paused, 1);
});

test("source segment plays through media onPlay and stops at its selected bar boundary", async ({ page }) => {
  const wav = Buffer.alloc(44 + 8000 * 2 * 2);
  wav.write("RIFF", 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
  wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
  await page.route("**/api/v1/jobs/editor/audio", (route) => {
    const range = route.request().headers().range?.match(/bytes=(\d+)-(\d*)/);
    if (!range) return route.fulfill({ body: wav, contentType: "audio/wav", headers: { "Accept-Ranges": "bytes" } });
    const start = Number(range[1]), end = range[2] ? Number(range[2]) : wav.length - 1;
    return route.fulfill({ status: 206, body: wav.subarray(start, end + 1), contentType: "audio/wav",
      headers: { "Accept-Ranges": "bytes", "Content-Range": `bytes ${start}-${end}/${wav.length}` } });
  });
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score, song: { ...score.song, duration_seconds: 2 },
      beats: Array.from({ length: 10 }, (_, i) => ({ time: i * .2, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })) },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("1");
  await page.getByRole("button", { name: "對照來源片段", exact: true }).click();
  const audio = page.locator("audio").first();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(.1);
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  expect(await audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeCloseTo(.8, 1);
  await page.getByRole("button", { name: "對照來源片段", exact: true }).click();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(false);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  expect(await audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
});

test("empty opening explains missing notes and can jump to an editable note without modifying it", async ({ page }) => {
  let edits = 0;
  await page.route("**/scores/melody/edit", (route) => { edits++; return route.fulfill({ json: answer(route) }); });
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score,
      beats: Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
      melody: [{ ...score.melody[0], start: 4, end: 4.5 }] },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("2");
  await expect(page.getByText(/所選小節沒有旋律音符可修改/)).toBeVisible();
  await expect(page.getByLabel("旋律資料狀態")).toContainText("工作樂譜共 1 個旋律音符；所選小節有 0 個");
  await expect(page.getByLabel("Tab start bar").locator("option").filter({ hasText: "Bar 3 · 1 音符" })).toHaveCount(1);
  await page.getByRole("button", { name: "跳到第一個有音符的小節", exact: true }).click();
  await expect(page.getByLabel("Tab start bar")).toHaveValue("2");
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Apply note", exact: true })).toBeEnabled();
  await expect(page.getByLabel("Tab fret", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("旋律資料狀態")).toContainText("所選小節有 1 個");
  expect(edits).toBe(0);
});

test("four bars default, eight bars follow within the editor without chord page scrolling", async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__chordScrolls = 0;
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function(options) {
      if (this.classList.contains("chord-block-active")) (window as any).__chordScrolls++;
      original.call(this, options);
    };
  });
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score,
      song: { ...score.song, duration_seconds: 3.2 },
      beats: Array.from({ length: 32 }, (_, i) => ({ time: i * .1, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
      chords: Array.from({ length: 8 }, (_, i) => ({ id: `c${i}`, start: i * .4, end: (i + 1) * .4, symbol: "C", confidence: .5, origin: "model", edited: false })),
    },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByLabel("Tab bar count")).toHaveValue("4");
  await expect(page.locator(".editable-tab-bar")).toHaveCount(4);
  await page.getByLabel("Tab bar count").selectOption("8");
  await expect(page.locator(".editable-tab-bar")).toHaveCount(8);
  await page.getByRole("button", { name: "重播所選小節", exact: true }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await page.evaluate(() => { (window as any).__chordScrolls = 0; });
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  const scrollY = await page.evaluate(() => window.scrollY);
  await expect.poll(() => page.locator(".editable-tab").evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => (window as any).__chordScrolls)).toBe(0);
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scrollY)).toBeLessThan(3);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
});
