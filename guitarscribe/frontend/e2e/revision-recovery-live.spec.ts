import { expect, test } from "@playwright/test";
import type { SongScore } from "../src/types";

// Opt-in: reads an existing revision; edits only an isolated browser's working copy.
// All persistence/analysis requests from the page are blocked, even on test failure.
test("saved G restores and Bar 10 edit/Undo reach real ensemble playback without changing the saved revision", async ({ page, request }) => {
  const revision = process.env.GUITARSCRIBE_RECOVERY_REVISION;
  test.skip(!revision, "Requires an explicit saved revision ID and running UI/API");
  test.setTimeout(60_000);
  const api = process.env.GUITARSCRIBE_API_URL ?? "http://127.0.0.1:8000";
  const ui = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:5173";
  const response = await request.get(`${api}/revisions/${encodeURIComponent(revision!)}`);
  expect(response.ok()).toBeTruthy();
  const original: SongScore = await response.json();
  expect(original.provenance.parameters?.melody_note_processing).toBe("bounded-source-v1");
  const blocked: string[] = [];
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
    await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
    const startBar = page.getByLabel("Tab start bar");
    const value = await startBar.locator("option").evaluateAll(options => options.find(option => option.textContent?.startsWith("Bar 10 ·"))?.getAttribute("value"));
    expect(value).toBeTruthy();
    await startBar.selectOption(value!);
    await page.getByLabel("Tab bar count").selectOption("4");
    await page.getByLabel("Editor audition mode").selectOption("ensemble");
    async function compiledMelody() {
      const pending = page.waitForResponse(r => new URL(r.url()).pathname === "/scores/playback/manifest");
      await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
      const result = await pending;
      expect(result.ok()).toBeTruthy();
      const manifest = await result.json();
      await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
      return manifest.events.filter((event: { track: string }) => event.track === "melody")
        .map((event: { start: number; end: number; pitches: number[] }) => [event.start, event.end, event.pitches[0]]);
    }
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
    expect(blocked).toEqual([]);
  } finally {
    const after = await request.get(`${api}/revisions/${encodeURIComponent(revision!)}`);
    expect(after.ok()).toBeTruthy();
    expect(await after.json()).toEqual(original);
  }
});
