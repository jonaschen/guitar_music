import { expect, test } from "@playwright/test";
import { pluckedSamples } from "../src/pluckedTone";

test("additive pluck starts smoothly, decays, and remains bounded", () => {
  const data = pluckedSamples(57, 22050, 2);
  const rms = (start: number, end: number) => {
    const segment = data.slice(start * 22050, end * 22050);
    return Math.sqrt(segment.reduce((sum, value) => sum + value ** 2, 0) / segment.length);
  };
  expect(data[0]).toBe(0);
  expect(Math.max(...data.map(Math.abs))).toBeLessThan(1);
  expect(rms(0.5, 0.6)).toBeLessThan(rms(0.05, 0.15));
  expect(rms(0.5, 0.6)).toBeGreaterThan(0.03);
  expect(rms(1.98, 2)).toBeLessThan(rms(1.8, 1.9));
});

test("reference can play, switch tone, and stop without loading or replacing a song", async ({ page }) => {
  await page.route("**/scores/playback/reference*", (route) => route.fulfill({ json: {
    revision: "reference", duration_seconds: 10, bpm: 96, time_signature: "4/4",
    events: [{ id: "c", track: "guitar", start: 0, end: 1, pitches: [48, 52, 55], pitch_offsets: [0, 0.012, 0.024], pitch_velocities: [98, 96, 94], velocity: 98 }],
  } }));
  await page.goto("/");
  const control = page.getByRole("region", { name: "Four-bar listening control" });
  await control.getByRole("button", { name: "播放四小節" }).click();
  await expect(control.getByRole("status")).toContainText("Bar 1");
  await control.getByRole("button", { name: "停止試聽" }).click();
  await expect(control.getByRole("status")).toContainText("Ready");
  await control.getByLabel("Reference chord changes").selectOption("within");
  await expect(control).toContainText("C/Am → F/G");
  const requested = page.waitForRequest("**/scores/playback/reference?within_bar=true");
  await control.getByLabel("Reference tone").selectOption("simple");
  await control.getByRole("button", { name: "播放四小節" }).click();
  await requested;
  await expect(control.getByRole("status")).toContainText("Bar 1");
  await control.getByRole("button", { name: "停止試聽" }).click();
  await expect(page.getByRole("button", { name: "Start analysis" })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("guitarscribe.activeJobId"))).toBeNull();
});

test("metronome volume and downbeat produce measurable differences", async ({ page }) => {
  await page.goto("/");
  const measured = await page.evaluate(async () => {
    const modulePath = "/src/metronomeVoice.ts";
    const { createMetronomeVoice } = await import(modulePath);
    async function render(volume: number, strong: boolean) {
      const context = new OfflineAudioContext(1, 4410, 44100);
      createMetronomeVoice(context, 0, strong, volume);
      const data = (await context.startRendering()).getChannelData(0);
      return Math.sqrt(data.reduce((sum, sample) => sum + sample * sample, 0) / data.length);
    }
    return { silent: await render(0, true), quiet: await render(0.2, true), loud: await render(0.4, true), weak: await render(0.4, false) };
  });
  expect(measured.silent).toBe(0);
  expect(measured.loud).toBeGreaterThan(measured.quiet * 1.8);
  expect(measured.loud).toBeGreaterThan(measured.weak * 1.4);
});
