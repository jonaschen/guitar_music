import { expect, test } from "@playwright/test";
import type { SongScore } from "../src/types";

// Opt-in: reads an existing revision; edits only an isolated browser's working copy.
// All persistence/analysis requests from the page are blocked, even on test failure.
for (const workspace of ["full", "focus"] as const) {
test(`${workspace}: saved G restores, note and bar edits reach real ensemble playback, and Undo preserves the saved revision`, async ({ page, request }) => {
  const revision = process.env.GUITARSCRIBE_RECOVERY_REVISION;
  test.skip(!revision, "Requires an explicit saved revision ID and running UI/API");
  // Two independent edit/Undo round trips now compile the full real song six
  // times; allow time for the final read-only persistence check as well.
  test.setTimeout(120_000);
  const api = process.env.GUITARSCRIBE_API_URL ?? "http://127.0.0.1:8000";
  const ui = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:5173";
  const response = await request.get(`${api}/revisions/${encodeURIComponent(revision!)}`);
  expect(response.ok()).toBeTruthy();
  const original: SongScore = await response.json();
  expect(original.provenance.parameters?.melody_note_processing).toBe("bounded-source-v1");
  const blocked: string[] = [];
  await page.addInitScript(mode => localStorage.setItem("guitarscribe.workspaceMode", mode), workspace);
  await page.route("**/*", route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const safe = ["/scores/playback/manifest", "/scores/melody/edit", "/scores/musicxml"];
    if (!["GET", "HEAD", "OPTIONS"].includes(req.method()) && !safe.includes(path)) {
      blocked.push(`${req.method()} ${path}`);
      return route.abort();
    }
    return route.continue();
  });
  try {
    await page.goto(ui);
    await page.getByLabel("Saved revision ID").fill(revision!);
    await page.getByRole("button", { name: "載入已保存修訂", exact: true }).click();
    await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
    await expect(page.getByLabel("Current working version")).toContainText(`Contour G 候選 · ${original.melody.length} 音符`);
    await expect(page.getByLabel("Current working version")).toContainText(revision!);
    if (workspace === "full") await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
    const startBar = page.getByLabel("Tab start bar");
    const value = await startBar.locator("option").evaluateAll(options => options.find(option => option.textContent?.startsWith("Bar 10 ·"))?.getAttribute("value"));
    expect(value).toBeTruthy();
    await startBar.selectOption(value!);
    await page.getByLabel("Tab bar count").selectOption("4");
    await page.getByLabel("Editor audition mode").selectOption("ensemble");
    if (workspace === "focus") await page.screenshot({ path: test.info().outputPath("saved-g-focus.png"), fullPage: true });
    async function compiledPlayback() {
      const pending = page.waitForResponse(r => new URL(r.url()).pathname === "/scores/playback/manifest");
      await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
      const result = await pending;
      expect(result.ok()).toBeTruthy();
      const manifest = await result.json();
      await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
      return { manifest, score: result.request().postDataJSON() as SongScore };
    }
    type Event = { track: string; start: number; end: number; pitches: number[] };
    function melodyEvents(manifest: { events: Event[] }) {
      return manifest.events.filter(event => event.track === "melody")
        .map((event: { start: number; end: number; pitches: number[] }) => [event.start, event.end, event.pitches[0]]);
    }
    async function compiledMelody() { return melodyEvents((await compiledPlayback()).manifest); }
    const expected = original.melody.map(note => [note.start, note.end, note.midi]);
    expect(await compiledMelody()).toEqual(expected);
    const noteButton = page.getByRole("region", { name: "六線譜 Bar 10", exact: true }).locator(".editable-tab-note").first();
    const label = await noteButton.getAttribute("aria-label");
    const note = original.melody.find(n => label?.startsWith(`Tab ${n.id} `))!;
    expect(note).toBeTruthy();
    await noteButton.click();
    const newFret = note.fret! < original.guitar.max_fret ? note.fret! + 1 : note.fret! - 1;
    await page.getByLabel("Tab fret", { exact: true }).fill(String(newFret));
    const editResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/scores/melody/edit");
    await page.getByRole("button", { name: "Apply note", exact: true }).click();
    const editedResponse = await editResponse;
    expect(editedResponse.ok()).toBeTruthy();
    const edited: SongScore = (await editedResponse.json()).score;
    const changed = edited.melody.find(n => n.id === note.id)!;
    expect(changed.midi).toBe(note.midi + newFret - note.fret!);
    expect([changed.start, changed.end]).toEqual([note.start, note.end]);
    expect(edited.melody.filter(n => n.id !== note.id)).toEqual(original.melody.filter(n => n.id !== note.id));
    expect(await compiledMelody()).toEqual(edited.melody.map(n => [n.start, n.end, n.midi]));
    await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
    expect(await compiledMelody()).toEqual(expected);
    await expect(page.getByLabel("Current working version")).toContainText(`已保存／載入：${revision}`);

    // Exercise the actual saved song's shared grid, without claiming +100ms is
    // musically correct or persisting this deliberately temporary adjustment.
    const bar28 = await startBar.locator("option").evaluateAll(options => options.find(option => option.textContent?.startsWith("Bar 28 ·"))?.getAttribute("value"));
    expect(bar28).toBeTruthy();
    await startBar.selectOption(bar28!);
    await page.getByLabel("Tab bar count").selectOption("8");
    const before = await compiledPlayback();
    await page.getByText("所選小節分界校正（不移動音符）", { exact: true }).click();
    const boundary = page.getByLabel("Bar 31 boundary seconds", { exact: true });
    const oldBoundary = Number(await boundary.inputValue());
    await boundary.fill(String(oldBoundary + .1));
    await page.getByRole("button", { name: "套用小節分界", exact: true }).click();
    const retimed = await compiledPlayback();
    expect(retimed.score.beats.find(beat => beat.measure === 31 && beat.beat === 1)?.time).toBeCloseTo(oldBoundary + .1, 8);
    expect(retimed.score.melody).toEqual(before.score.melody);
    expect(retimed.score.chords).toEqual(before.score.chords);
    expect(retimed.score.lyrics).toEqual(before.score.lyrics);
    expect(retimed.score.beats.filter(beat => beat.measure < 30 || beat.measure > 31))
      .toEqual(before.score.beats.filter(beat => beat.measure < 30 || beat.measure > 31));
    expect(melodyEvents(retimed.manifest)).toEqual(expected);
    expect(retimed.manifest.events.filter((event: Event) => event.track === "guitar"))
      .not.toEqual(before.manifest.events.filter((event: Event) => event.track === "guitar"));
    await page.getByRole("button", { name: "Undo melody edit", exact: true }).click();
    const restored = await compiledPlayback();
    expect(restored.score).toEqual(before.score);
    expect(restored.manifest.events).toEqual(before.manifest.events);
    await expect(page.getByLabel("Current working version")).toContainText(`已保存／載入：${revision}`);
    expect(blocked).toEqual([]);
  } finally {
    const after = await request.get(`${api}/revisions/${encodeURIComponent(revision!)}`);
    expect(after.ok()).toBeTruthy();
    expect(await after.json()).toEqual(original);
  }
});
}
