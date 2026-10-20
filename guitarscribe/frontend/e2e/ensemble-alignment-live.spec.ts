import { expect, test } from "@playwright/test";
import type { SongScore, PlaybackManifest } from "../src/types";

test("real G comparison page uses matching score time and actual ensemble scheduling without persistence writes", async ({ page, request }, testInfo) => {
  const revision = process.env.GUITARSCRIBE_RECOVERY_REVISION;
  test.skip(!revision, "Explicit saved revision and local listening packet required");
  test.setTimeout(90_000);
  const api = process.env.GUITARSCRIBE_API_URL ?? "http://127.0.0.1:8000";
  const ui = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:5173";
  const original: SongScore = await (await request.get(`${api}/revisions/${revision}`)).json();
  const config = await (await request.get(`${ui}/listening/ensemble-2026-10-18/config.json`)).json();
  expect(config.revision).toBe(revision);
  const start = original.beats.find(b => b.measure === 28 && b.beat === 1)!.time;
  const end = original.beats.find(b => b.measure === 36 && b.beat === 1)!.time;
  expect(config).toEqual({ revision, start, end });
  const blocked: string[] = [], errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.route("**/*", route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (!["GET", "HEAD", "OPTIONS"].includes(req.method()) && !["/scores/musicxml", "/scores/playback/manifest"].includes(path)) {
      blocked.push(path); return route.abort();
    }
    return route.continue();
  });
  await page.addInitScript(() => {
    const w = window as any; w.__frequencies = []; w.__plucks = [];
    const oscillator = AudioContext.prototype.createOscillator;
    AudioContext.prototype.createOscillator = function () {
      const node = oscillator.call(this), set = node.frequency.setValueAtTime.bind(node.frequency);
      node.frequency.setValueAtTime = (v, t) => { w.__frequencies.push([v, t]); return set(v, t); };
      return node;
    };
    const bufferSource = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function () {
      const node = bufferSource.call(this), start = node.start.bind(node);
      node.start = (t = 0, offset = 0) => { w.__plucks.push([t, offset]); start(t, offset); };
      return node;
    };
  });
  await page.goto(`${ui}/listening/ensemble-2026-10-18/index.html`);
  await expect(page.locator("#status")).toHaveText("準備完成", { timeout: 25000 });
  const frame = page.frames().find(f => f.url().includes("?revision="))!;
  expect(frame).toBeTruthy();
  await expect(frame.getByLabel("Editor playback speed")).toHaveValue("1");
  await expect(frame.getByLabel("Editor audition mode")).toHaveValue("ensemble");
  await expect(frame.getByLabel("Loop edited bars")).not.toBeChecked();
  await page.getByRole("button", { name: "依序播放原曲與合奏", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("播放中：原曲");
  await expect.poll(() => page.locator("#source").evaluate((a: HTMLAudioElement) => a.duration)).toBeCloseTo(end - start, 3);
  const response = page.waitForResponse(r => new URL(r.url()).pathname === "/scores/playback/manifest");
  // Skip most of the reference, but exercise the real ended-event handoff.
  await page.locator("#source").evaluate((a: HTMLAudioElement) => { a.currentTime = a.duration - .2; });
  const compiled = await response;
  expect(compiled.ok()).toBeTruthy();
  expect(compiled.request().postDataJSON()).toEqual(original);
  const manifest: PlaybackManifest = await compiled.json();
  expect(manifest.events.filter(e => e.track === "melody").map(e => [e.start, e.end, e.pitches[0]]))
    .toEqual(original.melody.map(n => [n.start, n.end, n.midi]));
  await expect(page.locator("#status")).toHaveText("播放中：G 合奏", { timeout: 20000 });
  await expect(page.locator("#status")).toHaveText("播放完成", { timeout: 20000 });
  const capture = await frame.evaluate(() => ({ frequencies: (window as any).__frequencies as number[][], plucks: (window as any).__plucks as number[][] }));
  const notes = original.melody.filter(n => n.end > start && n.start < end);
  capture.frequencies.sort((a, b) => a[1] - b[1]);
  expect(capture.frequencies).toHaveLength(notes.length);
  const origin = capture.frequencies[0][1] - Math.max(0, notes[0].start - start);
  notes.forEach((n, i) => {
    expect(69 + 12 * Math.log2(capture.frequencies[i][0] / 440)).toBeCloseTo(n.midi, 8);
    expect(capture.frequencies[i][1] - origin).toBeCloseTo(Math.max(0, n.start - start), 7);
  });
  const guitar = manifest.events.filter(e => e.track === "guitar" && (e.sustain_end ?? e.end) > start && e.start < end);
  const expectedPlucks = guitar.flatMap(e => e.pitches.map((_, i) => Math.max(0, e.start + (e.pitch_offsets[i] ?? i * .012) - start)))
    .filter(t => t < end - start).sort((a, b) => a - b);
  const actualPlucks = capture.plucks.map(p => p[0] - origin).sort((a, b) => a - b);
  expect(actualPlucks).toHaveLength(expectedPlucks.length);
  expectedPlucks.forEach((t, i) => expect(actualPlucks[i]).toBeCloseTo(t, 7));
  await page.getByRole("button", { name: "播放合奏", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("播放中：G 合奏", { timeout: 20000 });
  await page.getByRole("button", { name: "全部停止", exact: true }).click();
  const stopped = await frame.evaluate(() => (window as any).__plucks.length);
  await page.waitForTimeout(500);
  expect(await frame.evaluate(() => (window as any).__plucks.length)).toBe(stopped);
  expect(blocked).toEqual([]); expect(errors).toEqual([]);
  expect(await (await request.get(`${api}/revisions/${revision}`)).json()).toEqual(original);
  await testInfo.attach("alignment.json", { body: JSON.stringify({ revision, start, end, melodyNotes: notes.length, guitarVoices: actualPlucks.length, sourceOffset: original.song.source_start_seconds, originalUnchanged: true }, null, 2), contentType: "application/json" });
});
