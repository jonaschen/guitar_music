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
  await control.getByLabel("Reference chord changes").selectOption("three");
  await expect(control.getByLabel("小節內四拍").locator("strong")).toHaveText(["C", "C", "Am", "G"]);
  const threeRequested = page.waitForRequest("**/scores/playback/reference?chords_per_bar=3");
  await control.getByRole("button", { name: "播放四小節" }).click();
  await threeRequested;
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

test("weak strokes retain earlier resonance without clipping and harmony change damps it", async ({ page }) => {
  await page.goto("/");
  const measured = await page.evaluate(async () => {
    const modulePath = "/src/pluckedTone.ts";
    const { preparePluckedBuffers, createPluckedVoice } = await import(modulePath);
    async function render(ringEnd: number) {
      const context = new OfflineAudioContext(1, 44100 * 3, 44100);
      const buffers = await preparePluckedBuffers(context, [48, 52, 55]);
      for (const [time, velocity] of [[0, 98], [0.625, 27], [0.9375, 15], [1.25, 54], [1.5625, 15], [1.875, 27], [2.1875, 15]]) {
        if (time >= ringEnd) continue;
        [48, 52, 55].forEach((pitch, index) => createPluckedVoice(context, buffers.get(pitch)!, time + index * 0.012, ringEnd, 0.24 * velocity / 127 / Math.sqrt(3)));
      }
      return (await context.startRendering()).getChannelData(0);
    }
    const data = await render(2.5);
    const damped = await render(0.625);
    const rms = (samples: Float32Array, start: number, end: number) => {
      const slice = samples.slice(start * 44100, end * 44100);
      return Math.sqrt(slice.reduce((sum, value) => sum + value * value, 0) / slice.length);
    };
    return { retained: rms(data, 0.95, 1.05), damped: rms(damped, 0.95, 1.05), peak: data.reduce((peak, v) => Math.max(peak, Math.abs(v)), 0), tail: rms(data, 2.85, 2.95) };
  });
  expect(measured.retained).toBeGreaterThan(0.005);
  expect(measured.damped).toBe(0);
  expect(measured.peak).toBeLessThan(1);
  expect(measured.tail).toBe(0);
});
