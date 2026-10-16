import { expect, test, type Page, type Route } from "@playwright/test";
import { notationBars, notationClock, noteGrid, snapNoteTime } from "../src/melodyNotation";
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

test("Contour candidate is explicit, undoable and cannot apply after work changes", async ({ page }) => {
  let held: Route | undefined;
  let delay = false;
  const candidate = { ...score, melody: score.melody.map(n => ({ ...n, midi: 64, note: "E4", fret: 5 })),
    provenance: { ...score.provenance, parameters: { melody_note_processing: "bounded-source-v1" } } };
  await page.route("**/api/v1/jobs/editor/melody-candidate", r => {
    if (delay) { held = r; return; }
    return r.fulfill({ json: candidate });
  });
  await setup(page);
  await expect(page.getByLabel("Editor melody version")).toContainText("其他／較早音符版本（未標記 G）");
  await page.getByText("Contour → 可編輯音符候選（G，實驗性）", { exact: true }).click();
  const generate = page.getByRole("button", { name: "產生 Contour 音符候選", exact: true });
  const apply = page.getByRole("button", { name: "套用候選到工作譜（可 Undo）", exact: true });
  await generate.click();
  await expect(apply).toBeVisible();
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  await apply.click();
  await expect(page.getByLabel("Editor melody version")).toContainText("Contour G 候選");
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.50s", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByLabel("Editor melody version")).toContainText("其他／較早音符版本（未標記 G）");
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  delay = true;
  await generate.click();
  await expect.poll(() => Boolean(held)).toBe(true);
  await page.getByRole("button", { name: "Redo melody edit", exact: true }).click();
  await held!.fulfill({ json: candidate });
  await expect(page.getByText("工作譜或來源已改變，候選已失效，未套用。", { exact: true })).toBeVisible();
  await expect(apply).toHaveCount(0);
});

async function setup(page: Page, empty = false, noteStart = 0, completeBeats = false) {
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score,
      beats: completeBeats ? Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })) : score.beats,
      melody: empty ? [] : score.melody.map((note) => ({ ...note, start: noteStart, end: noteStart + .5 })) },
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

test("G survives explicit save, refresh, restore and resave with the same playback notes and source", async ({ page }) => {
  const candidate = { ...score, melody: [{ ...score.melody[0], midi: 64, note: "E4", start: .123, end: .456 }],
    provenance: { ...score.provenance, parameters: { melody_note_processing: "bounded-source-v1", candidate_source_job_id: "editor" } } };
  const saved: Record<string, any> = {};
  const compiled: any[] = [];
  let saveCount = 0;
  await page.route("**/jobs/editor/melody-candidate", r => r.fulfill({ json: candidate }));
  await page.route("**/revisions", r => {
    const body = r.request().postDataJSON();
    expect(body.create_new).toBe(true);
    const id = `g-${++saveCount}`; saved[id] = body.score;
    return r.fulfill({ json: { revision_id: id } });
  });
  await page.route("**/revisions/g-*", r => r.fulfill({ json: saved[r.request().url().split("/").at(-1)!] }));
  await page.route("**/scores/playback/manifest", r => {
    const body = r.request().postDataJSON(); compiled.push(body.melody);
    return r.fulfill({ json: { events: body.melody.map((n: any) => ({ track: "melody", start: n.start, end: n.end, pitches: [n.midi], pitch_offsets: [0], pitch_velocities: [96], velocity: 96 })) } });
  });
  await setup(page);
  await page.getByText("Contour → 可編輯音符候選（G，實驗性）", { exact: true }).click();
  await page.getByRole("button", { name: "產生 Contour 音符候選", exact: true }).click();
  await page.getByRole("button", { name: "套用候選到工作譜（可 Undo）", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("有未保存修改");
  await page.getByRole("button", { name: "保存目前工作版本", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g-1");
  await page.reload();
  await expect(page.getByLabel("Current working version")).not.toContainText("Contour G");
  await page.getByRole("button", { name: "恢復上次保存版本", exact: true }).click();
  await expect(page.getByLabel("Current working version")).not.toContainText("Contour G");
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("Contour G");
  await expect(page.locator("audio")).toHaveAttribute("src", /jobs\/editor\/audio$/);
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByLabel("旋律資料狀態")).toContainText("來源分析：editor");
  await page.getByLabel("Editor audition mode").selectOption("ensemble");
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  await expect.poll(() => compiled.length).toBe(1);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  await page.getByText("Compiled score playback", { exact: true }).click();
  await page.getByRole("button", { name: "Play score", exact: true }).click();
  await expect.poll(() => compiled.length).toBe(2);
  expect(compiled).toEqual([candidate.melody, candidate.melody]);
  await page.getByRole("button", { name: "保存目前工作版本", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g-2");
  expect(saved["g-2"]).toEqual(saved["g-1"]);
  expect(await page.evaluate(() => localStorage.getItem("guitarscribe.melodyRevision.editor"))).toBe("g-2");
});

test("revision preview and late responses never replace newer edits; cancel and expired source are safe", async ({ page }) => {
  let held: Route | undefined;
  let delay = false;
  const candidate = { ...score, provenance: { ...score.provenance,
    parameters: { melody_note_processing: "bounded-source-v1", candidate_source_job_id: "expired" } } };
  await page.route("**/revisions/g", r => { if (delay) { held = r; return; } return r.fulfill({ json: candidate }); });
  await page.route("**/jobs/expired", r => r.fulfill({ status: 404, json: { detail: "Expired" } }));
  await page.route("**/scores/melody/edit", r => r.fulfill({ json: answer(r) }));
  await setup(page);
  await page.getByLabel("Melody revision ID").fill("g");
  const load = page.getByRole("button", { name: "Load melody revision", exact: true });
  const confirm = page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true });
  await load.click();
  await expect(confirm).toBeEnabled();
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(confirm).toBeDisabled();
  delay = true;
  await load.click();
  await expect.poll(() => !!held).toBe(true);
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await held!.fulfill({ json: candidate });
  await expect(page.getByLabel("工作版本")).toContainText("讀取期間工作譜已改變");
  await expect(confirm).toHaveCount(0);
  held = undefined;
  await load.click();
  await expect.poll(() => !!held).toBe(true);
  await page.getByRole("button", { name: "取消讀取版本", exact: true }).click();
  await held!.fulfill({ json: candidate });
  await expect(page.getByLabel("工作版本")).toContainText("已取消讀取");
  await expect(confirm).toHaveCount(0);
  delay = false;
  await load.click();
  await confirm.click();
  await expect(page.getByLabel("Editor melody version")).toContainText("Contour G");
  await expect(page.locator("audio")).toHaveCount(0);
  await expect(page.getByLabel("旋律資料狀態")).toContainText("來源分析：expired");
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByLabel("Editor melody version")).not.toContainText("Contour G");
});

for (const operation of ["simplify", "remap", "transpose", "voicings", "lyrics"] as const) {
  test(`late ${operation} result cannot overwrite restored G or add a false Undo entry`, async ({ page }) => {
    let held: Route | undefined;
    const endpoint = { simplify: "melody/simplify", remap: "remap-tab", transpose: "transpose", voicings: "optimize-voicings", lyrics: "lyrics/import-text" }[operation];
    const candidate = { ...score, melody: [{ ...score.melody[0], midi: 64, note: "E4" }],
      provenance: { ...score.provenance, parameters: { melody_note_processing: "bounded-source-v1", candidate_source_job_id: "editor" } } };
    await page.route(`**/scores/${endpoint}`, route => { held = route; });
    await page.route("**/revisions/g", route => route.fulfill({ json: candidate }));
    await setup(page);
    if (operation === "simplify") {
      await page.getByText("Melody & Tab previews · Experimental", { exact: true }).click();
      await page.getByRole("button", { name: "Simplify melody", exact: true }).click();
    } else if (operation === "remap") {
      await page.getByRole("combobox", { name: "Tab mapping", exact: true }).selectOption("low_position");
    } else if (operation === "transpose") {
      await page.getByRole("combobox", { name: "Target key", exact: true }).selectOption("2");
    } else if (operation === "voicings") {
      await page.getByRole("button", { name: "Optimize song voicings", exact: true }).click();
    } else {
      await page.getByText("Lyrics", { exact: true }).click();
      await page.locator(".lyrics-panel textarea").fill("Test lyrics");
      await page.getByRole("button", { name: "Import lyrics", exact: true }).click();
    }
    await expect.poll(() => !!held).toBe(true);
    await page.getByLabel("Melody revision ID").fill("g");
    await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
    await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
    await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
    await held!.fulfill({ json: score });
    await expect(page.getByText("工作譜已改變，較舊的操作結果未套用；目前版本與 Undo 紀錄保持不變。", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g");
    await expect(page.getByRole("button", { name: "E4 · 0.00–0.50s", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
    await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Undo melody edit", exact: true })).toBeDisabled();
  });
}

test("a pending score transform stays stale after editing and Undo return to its original score", async ({ page }) => {
  let held: Route | undefined;
  await page.route("**/scores/optimize-voicings", route => { held = route; });
  await page.route("**/scores/melody/edit", route => route.fulfill({ json: answer(route) }));
  await setup(page);
  await page.getByRole("button", { name: "Optimize song voicings", exact: true }).click();
  await expect.poll(() => !!held).toBe(true);
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await held!.fulfill({ json: { ...score, melody: [] } });
  await expect(page.getByText("工作譜已改變，較舊的操作結果未套用；目前版本與 Undo 紀錄保持不變。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Redo melody edit", exact: true })).toBeEnabled();
});

for (const lateStatus of [200, 404]) {
  test(`late original analysis ${lateStatus} cannot replace an explicitly restored G revision`, async ({ page }) => {
    const held: Route[] = [];
    let restoringRevision = false;
    const candidate = { ...score, melody: [{ ...score.melody[0], midi: 64, note: "E4" }],
      provenance: { ...score.provenance, parameters: { melody_note_processing: "bounded-source-v1", candidate_source_job_id: "editor" } } };
    const job = { id: "editor", status: "completed", progress: 100, artifacts: [], score };
    await page.route("**/api/v1/jobs/editor", route => {
      if (!restoringRevision) { held.push(route); return; }
      return route.fulfill({ json: job });
    });
    await page.route("**/revisions/g", route => route.fulfill({ json: candidate }));
    await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
    await page.goto("/?job=editor");
    // Development StrictMode launches two initial reads; hold both.
    await expect.poll(() => held.length).toBe(2);
    await page.getByLabel("Saved revision ID").fill("g");
    restoringRevision = true;
    await page.getByRole("button", { name: "載入已保存修訂", exact: true }).click();
    await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
    await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
    const lateResponse = page.waitForResponse(r => r.headers()["x-delayed-test"] === "1");
    await Promise.all(held.map(route => route.fulfill({ status: lateStatus, headers: { "x-delayed-test": "1" }, json: lateStatus === 200 ? job : { detail: "Expired" } })));
    await lateResponse;
    await page.waitForTimeout(150);
    await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
    await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g");
    await expect(page.locator("audio")).toHaveAttribute("src", /jobs\/editor\/audio$/);
    await expect(page.getByText("This saved analysis has expired or is no longer available. Start a new analysis below.")).toHaveCount(0);
  });
}

test("restore preview stays invalid after Undo returns to the same score object", async ({ page }) => {
  await page.route("**/revisions/old", route => route.fulfill({ json: score }));
  await page.route("**/scores/melody/edit", route => route.fulfill({ json: answer(route) }));
  await setup(page);
  await page.getByLabel("Melody revision ID").fill("old");
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  const confirm = page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true });
  await expect(confirm).toBeEnabled();
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await expect(confirm).toBeDisabled();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  await expect(confirm).toBeDisabled();
});

test("editor ensemble uses current score, clips both tracks, loops and cancels pending playback", async ({ page }) => {
  let held: Route | undefined;
  let delay = false;
  const requests: any[] = [];
  await page.addInitScript(() => {
    (window as any).__frequencies = [];
    const original = AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime = function(value, time) {
      if (value > 20) (window as any).__frequencies.push(value);
      return original.call(this, value, time);
    };
  });
  const manifest = (body: any) => ({ events: [
    { track: "guitar", start: 0, end: 4, pitches: [48], pitch_offsets: [0], pitch_velocities: [90], velocity: 90 },
    { track: "melody", start: 0, end: 4, pitches: [body.melody[0].midi], pitch_offsets: [0], pitch_velocities: [90], velocity: 90 },
    { track: "melody", start: 2, end: 3, pitches: [84], pitch_offsets: [0], pitch_velocities: [90], velocity: 90 },
  ] });
  await page.route("**/scores/playback/manifest", route => {
    const body = route.request().postDataJSON(); requests.push(body);
    if (delay) { held = route; return; }
    return route.fulfill({ json: manifest(body) });
  });
  await page.route("**/scores/melody/edit", route => route.fulfill({ json: answer(route) }));
  await setup(page, false, 0, true);
  await page.getByText("Compiled score playback", { exact: true }).click();
  await page.getByLabel("Score guitar tone").selectOption("simple");
  await page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true }).click();
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Apply note", exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("1");
  await page.getByLabel("Editor audition mode").selectOption("ensemble");
  const replay = page.getByRole("button", { name: "重播所選小節", exact: true });
  const pause = page.getByRole("button", { name: "暫停，保留位置", exact: true });
  const position = () => page.getByLabel("Tab transport position").innerText().then(s => Number(s.match(/位置 ([\d.]+)s/)![1]));
  await replay.click();
  await expect.poll(position).toBeGreaterThan(.2);
  expect(requests[0].melody[0].midi).toBe(64);
  await expect.poll(() => page.evaluate(() => [130.8128, 329.6276].every(f => (window as any).__frequencies.some((v: number) => Math.abs(v - f) < .01)))).toBe(true);
  await pause.click();
  const paused = await position();
  await page.waitForTimeout(150);
  expect(await position()).toBe(paused);
  await page.getByRole("button", { name: "從暫停位置續播", exact: true }).click();
  await expect.poll(position).toBeGreaterThan(paused + .1);
  await expect.poll(position).toBe(2);
  await page.waitForTimeout(150);
  expect(await position()).toBe(2);
  expect(await page.evaluate(() => (window as any).__frequencies.some((f: number) => Math.abs(f - 1046.5023) < .01))).toBe(false);
  await page.getByLabel("Loop edited bars").check();
  await replay.click();
  await expect.poll(position, { intervals: [30] }).toBeGreaterThan(1.6);
  await expect.poll(position, { intervals: [30] }).toBeLessThan(.5);
  await pause.click();
  delay = true;
  await replay.click();
  await expect.poll(() => Boolean(held)).toBe(true);
  await pause.click();
  const stopped = await position();
  await held!.fulfill({ json: manifest(requests.at(-1)) });
  await page.waitForTimeout(300);
  expect(await position()).toBe(stopped);
});

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
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.00–0.75s · Edited", exact: true })).toBeVisible();
  await page.reload();
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByText("進階：秒數、音高與音符清單", { exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("saved-edit");
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
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
  expect(request.end - request.start).toBeCloseTo(.25);
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

for (const action of ["seek", "track", "pause"] as const) {
  test(`source preview boundary is cancelled by ${action}`, async ({ page }) => {
    // Drive media time explicitly: this tests ownership of the preview boundary,
    // independently of audio hardware or wall-clock playback jitter.
    await page.addInitScript(() => {
      const states = new WeakMap<HTMLMediaElement, { time: number; paused: boolean }>();
      function state(media: HTMLMediaElement) {
        if (!states.has(media)) states.set(media, { time: 0, paused: true });
        return states.get(media)!;
      }
      Object.defineProperty(HTMLMediaElement.prototype, "currentTime", { get() { return state(this).time; }, set(value) { state(this).time = value; } });
      Object.defineProperty(HTMLMediaElement.prototype, "paused", { get() { return state(this).paused; } });
      Object.defineProperty(HTMLMediaElement.prototype, "readyState", { get() { return 4; } });
      HTMLMediaElement.prototype.play = function () { state(this).paused = false; this.dispatchEvent(new Event("play")); return Promise.resolve(); };
      HTMLMediaElement.prototype.pause = function () { state(this).paused = true; this.dispatchEvent(new Event("pause")); };
    });
    await page.route("**/api/v1/jobs/editor", route => route.fulfill({ json: {
      id: "editor", status: "completed", progress: 100, artifacts: ["vocal-stem"],
      score: { ...score, beats: Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })) },
    } }));
    await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
    await page.goto("/?job=editor");
    await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
    await page.getByLabel("Tab bar count").selectOption("1");
    await page.getByRole("button", { name: "對照來源片段", exact: true }).click();
    await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    if (action === "seek") await page.getByLabel("Playback position", { exact: true }).fill("1");
    if (action === "track") await page.getByRole("button", { name: "Vocal stem", exact: true }).click();
    if (action === "pause") await page.getByRole("button", { name: "Pause", exact: true }).click();
    const time = await page.locator("audio").evaluate(async (audio: HTMLAudioElement) => {
      audio.currentTime = 4;
      audio.dispatchEvent(new Event("timeupdate"));
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      return audio.currentTime;
    });
    expect(time).toBe(4); // The cancelled Bar 1 boundary must not pull us back to 2s.
    if (action === "track") {
      await page.getByLabel("Playback position", { exact: true }).fill("1");
      const afterMetadata = await page.locator("audio").evaluate((audio: HTMLAudioElement) => {
        audio.dispatchEvent(new Event("loadedmetadata"));
        return audio.currentTime;
      });
      expect(afterMetadata).toBe(1); // Loading the new track must respect the latest seek.
    }
  });
}

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

test("add into a gap explains overlap and offers an explicit shortening without overwriting existing notes", async ({ page }) => {
  const requests: any[] = [];
  await page.route("**/scores/melody/edit", (route) => { requests.push(route.request().postDataJSON()); return route.fulfill({ json: answer(route) }); });
  await setup(page, false, 1);
  await page.getByLabel("Melody note start").fill("0.75");
  await page.getByLabel("Melody note end").fill("1.25");
  await page.getByLabel("Melody pitch").selectOption("64");
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByLabel("音符重疊提示")).toContainText("C4（1.000–1.500 秒）");
  expect(requests).toHaveLength(0);
  await page.getByRole("button", { name: "將新增音符縮短至下一音符前", exact: true }).click();
  await expect(page.getByLabel("Melody note end")).toHaveValue("1");
  expect(requests).toHaveLength(0);
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByRole("button", { name: "E4 · 0.75–1.00s · Edited", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "C4 · 1.00–1.50s", exact: true })).toBeVisible();
  expect(requests[0]).toMatchObject({ operation: "add", start: .75, end: 1, midi: 64 });
});

test("an empty string at an occupied melody time offers selecting the existing note", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "Bar 1 第 1 弦新增音符", exact: true }).click({ position: { x: 45, y: 12 } });
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.getByLabel("音符重疊提示")).toContainText("即使在不同弦也不能同時新增");
  await expect(page.getByRole("button", { name: "將新增音符縮短至下一音符前", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "選取衝突音符來修改", exact: true }).click();
  await expect(page.getByRole("button", { name: "Apply note", exact: true })).toBeVisible();
  await expect(page.getByLabel("Tab fret", { exact: true })).toHaveValue("1");
  await expect(page.getByLabel("Melody note start")).toHaveValue("0");
});

test("missing parent save explains recovery and preserves working score until explicit new save", async ({ page }) => {
  let calls = 0;
  await page.route("**/revisions", (route) => {
    calls++;
    return route.request().postDataJSON().revision_id
      ? route.fulfill({ status: 404, json: { detail: "Revision not found" } })
      : route.fulfill({ json: { revision_id: "new-independent" } });
  });
  await setup(page);
  await page.getByLabel("Melody revision ID").fill("missing");
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.locator(".melody-editor")).toContainText("保存失敗：找不到原版本 ID");
  expect(calls).toBe(1);
  await expect(page.getByRole("button", { name: "C4 · 0.00–0.50s", exact: true })).toBeVisible();
  await page.getByLabel("Melody revision ID").fill("");
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("new-independent");
  expect(calls).toBe(2);
});

test("snap grid respects variable beat times and stays inside the clicked bar", () => {
  const fixture = { ...score, beats: [.25, .75, 1.5, 2, 2.5].map((time, i) => ({ time, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })) } as SongScore;
  const before = JSON.stringify(fixture);
  expect(noteGrid(fixture, .25, 2.5, .5)).toEqual([.25, .5, .75, 1.125, 1.5, 1.75, 2, 2.25]);
  expect(snapNoteTime(fixture, 1.1, .25, 2.5, .5)).toBe(1.125);
  expect(snapNoteTime(fixture, 2.499, .25, 2.5, .5)).toBe(2.25);
  expect(snapNoteTime(fixture, 1.1, .25, 2.5, 0)).toBe(1.1);
  expect(JSON.stringify(fixture)).toBe(before);
});

test("nearby clicks select the same eighth grid point, arrows move the draft, free mode remains available", async ({ page }) => {
  await setup(page, true);
  await expect(page.getByLabel("Tab snap grid")).toHaveValue("0.5");
  const string = page.getByRole("button", { name: "Bar 1 第 1 弦新增音符", exact: true });
  await string.click({ position: { x: 65, y: 12 } });
  await expect(page.getByLabel("Melody note start")).toHaveValue("0.75");
  await expect(page.getByLabel("Melody note end")).toHaveValue("1");
  await string.click({ position: { x: 67, y: 12 } });
  await expect(page.getByLabel("Melody note start")).toHaveValue("0.75");
  await page.getByRole("button", { name: "後移一格", exact: true }).click();
  await expect(page.getByLabel("Melody note start")).toHaveValue("1");
  await expect(page.getByLabel("Melody note end")).toHaveValue("1.25");
  await page.getByRole("button", { name: "前移一格", exact: true }).click();
  await expect(page.getByLabel("Melody note start")).toHaveValue("0.75");
  await page.getByLabel("Tab snap grid").selectOption("0");
  await expect(page.getByLabel("Melody note start")).toHaveValue("0.75");
  await string.click({ position: { x: 80, y: 12 } });
  const freeTime = Number(await page.getByLabel("Melody note start").inputValue());
  expect(freeTime).toBeGreaterThan(1.1);
  expect(freeTime).toBeLessThan(1.3);
  expect(Math.abs(freeTime - 1.25)).toBeGreaterThan(.01);
  await expect(page.getByRole("button", { name: "後移一格", exact: true })).toBeDisabled();
});

test("phrase shift previews the selected range and moves all notes once with undo and save", async ({ page }) => {
  let saved: any;
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: {
    id: "editor", status: "completed", progress: 100, artifacts: [], score: { ...score,
      beats: Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
      melody: [{ ...score.melody[0], start: .5, end: 1 }, { ...score.melody[0], id: "n2", start: 3.5, end: 4.5 }, { ...score.melody[0], id: "outside", start: 5, end: 6 }],
    },
  } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/scores/melody/edit", (route) => {
    const body = route.request().postDataJSON();
    expect(body).toMatchObject({ operation: "shift_phrase", range_start: 0, range_end: 4, target_start: 0 });
    const result = structuredClone(body.score);
    result.melody = result.melody.map((n: any) => n.start < 4 ? { ...n, start: n.start - .5, end: n.end - .5, edited: true } : n);
    return route.fulfill({ json: { score: result, selected_note_id: "n1" } });
  });
  await page.route("**/revisions", (route) => { saved = route.request().postDataJSON().score; return route.fulfill({ json: { revision_id: "shifted" } }); });
  await page.goto("/?job=editor");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("2");
  await page.getByText("移除段落前方空白（整段前移）", { exact: true }).click();
  await expect(page.getByLabel("Phrase shift preview")).toContainText("0.500 → 0.000 秒");
  await page.getByRole("button", { name: "套用整段前移", exact: true }).click();
  await expect(page.getByText(/已將 2 個音符整段前移 0.500 秒/)).toBeVisible();
  await expect(page.getByRole("button", { name: "套用整段前移", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
  await expect(page.getByLabel("Phrase shift preview")).toContainText("0.500 → 0.000 秒");
  await page.getByRole("button", { name: "Redo melody edit", exact: true }).click();
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("shifted");
  expect(saved.melody.map((n: any) => [n.id, n.start, n.end])).toEqual([["n1", 0, .5], ["n2", 3, 4], ["outside", 5, 6]]);
});

test("cropped analysis explains source offset without skipping the opening twice", async ({ page }) => {
  const cropped = { ...score, song: { ...score.song, source_start_seconds: 19 } };
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: { id: "editor", status: "completed", progress: 100, artifacts: [], score: cropped } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await expect(page.getByText("分析前已略過 19 秒；樂譜／播放 0 秒 = 原檔 19 秒。請勿再次略過同一段開場。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("min", "0");
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("max", "8");
  await page.locator(".song-range-editor > summary").click();
  await expect(page.getByLabel("Song range start")).toHaveValue("0");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toBeVisible();
});

test("saved revision can be recovered without a surviving analysis job", async ({ page }) => {
  await page.route("**/revisions/recovered", (route) => route.fulfill({ json: score }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await page.getByLabel("Saved revision ID").fill("recovered");
  await page.getByRole("button", { name: "載入已保存修訂", exact: true }).click();
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect(page.getByText("旋律人工編輯 · Melody editor", { exact: true })).toBeVisible();
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toBeVisible();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("recovered");
  await expect(page.locator("audio")).toHaveCount(0);
});

test("song range bounds original audio and permits previewing a replacement start outside the range", async ({ page }) => {
  const wav = Buffer.alloc(44 + 8000 * 2 * 8);
  wav.write("RIFF", 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
  wav.write("data", 36); wav.writeUInt32LE(wav.length - 44, 40);
  await page.route("**/api/v1/jobs/editor/audio", (route) => {
    const range = route.request().headers().range?.match(/bytes=(\d+)-(\d*)/);
    if (!range) return route.fulfill({ body: wav, contentType: "audio/wav" });
    const start = Number(range[1]), end = range[2] ? Number(range[2]) : wav.length - 1;
    return route.fulfill({ status: 206, body: wav.subarray(start, end + 1), contentType: "audio/wav",
      headers: { "Accept-Ranges": "bytes", "Content-Range": `bytes ${start}-${end}/${wav.length}` } });
  });
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: { id: "editor", status: "completed", progress: 100, artifacts: [], score } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.goto("/?job=editor");
  await page.locator(".song-range-editor > summary").click();
  await page.getByLabel("Song range start").fill("2");
  await page.getByLabel("Song range end").fill("3");
  await page.getByRole("button", { name: "套用歌曲範圍", exact: true }).click();
  const audio = page.locator("audio").first();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(2);
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  expect(await audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeCloseTo(3, 1);
  await page.getByLabel("Song range start").fill("0");
  await page.getByLabel("Song range end").fill("1");
  await page.getByRole("button", { name: "試聽起點後 5 秒（來源）", exact: true }).click();
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => !a.paused && a.currentTime > 0 && a.currentTime < 1)).toBe(true);
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.paused)).toBe(true);
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("min", "2");
});

test("song range preserves timestamps, filters notation, bounds score playback and persists in revisions", async ({ page }) => {
  const fullScore = { ...score,
    beats: Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
    melody: [...score.melody, { ...score.melody[0], id: "song", start: 2, end: 2.5 }],
  };
  let saved: any;
  await page.route("**/api/v1/jobs/editor", (route) => route.fulfill({ json: { id: "editor", status: "completed", progress: 100, artifacts: [], score: fullScore } }));
  await page.route("**/rhythm-patterns?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/scores/playback/manifest", (route) => route.fulfill({ json: { revision: "test", duration_seconds: 8, bpm: 120, time_signature: "4/4", events: [] } }));
  await page.route("**/revisions", (route) => { saved = route.request().postDataJSON().score; return route.fulfill({ json: { revision_id: "range" } }); });
  await page.route("**/revisions/range", (route) => route.fulfill({ json: saved }));
  await page.goto("/?job=editor");
  await page.locator(".song-range-editor > summary").click();
  await page.getByLabel("Song range start").fill("2");
  await page.getByLabel("Song range end").fill("3");
  await page.getByRole("button", { name: "套用歌曲範圍", exact: true }).click();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("min", "2");
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("max", "3");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 C4 2弦1格", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Tab song C4 2弦1格", exact: true })).toBeVisible();
  await expect(page.locator(".editable-tab-bar")).toHaveCount(1);
  await page.getByRole("button", { name: "Save new revision", exact: true }).click();
  await expect(page.getByLabel("Melody revision ID")).toHaveValue("range");
  expect(saved.song_range).toEqual({ start: 2, end: 3 });
  expect(saved.melody).toEqual(fullScore.melody);
  expect(saved.beats).toEqual(fullScore.beats);
  await page.getByText("Compiled score playback", { exact: true }).click();
  await page.getByRole("button", { name: "Play score", exact: true }).click();
  await expect.poll(async () => Number(await page.getByLabel("Playback position", { exact: true }).inputValue())).toBeGreaterThan(2);
  await expect(page.getByRole("button", { name: "Play score", exact: true })).toBeVisible();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveValue("3");
  await page.getByRole("button", { name: "Stop score", exact: true }).click();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveValue("2");
  await page.getByRole("button", { name: "取消範圍，顯示全曲", exact: true }).click();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("min", "0");
  await page.getByRole("button", { name: "Load melody revision", exact: true }).click();
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect(page.getByLabel("Playback position", { exact: true })).toHaveAttribute("min", "2");
  await page.getByLabel("Song range start").fill("4");
  await expect(page.getByRole("button", { name: "套用歌曲範圍", exact: true })).toBeDisabled();
});
