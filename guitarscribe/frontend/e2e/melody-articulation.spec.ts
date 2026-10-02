import { expect, test } from "@playwright/test";
import { melodyEnvelope } from "../src/melodyEnvelope";

test("short and long melody envelopes retain duration and ordered automation", () => {
  for (const duration of [.025, .05, .125, .5, 2, 5]) {
    const points = melodyEnvelope(2, 2 + duration, .3);
    expect(points[0].time).toBe(2);
    expect(points[3].time).toBe(2 + duration);
    expect(points[2].value).toBeCloseTo(.24);
    expect(points[2].time).toBeGreaterThanOrEqual(2 + duration * .8);
    expect(points[3].value).toBeLessThan(.001);
    for (let i = 1; i < points.length; i++) expect(points[i].time).toBeGreaterThan(points[i - 1].time);
  }
});

test("rendered repeated melody notes sustain, articulate and stop on time", async ({ page }) => {
  await page.goto("/");
  const measured = await page.evaluate(async () => {
    const path = "/src/melodyEnvelope.ts";
    const { melodyEnvelope } = await import(path);
    const context = new OfflineAudioContext(1, 44100 * 2, 44100);
    for (const start of [0, .5, 1]) {
      const oscillator = context.createOscillator(), gain = context.createGain();
      oscillator.type = "triangle"; oscillator.frequency.value = 440;
      const points = melodyEnvelope(start, start + .5, .3);
      gain.gain.setValueAtTime(points[0].value, points[0].time);
      gain.gain.linearRampToValueAtTime(points[1].value, points[1].time);
      gain.gain.linearRampToValueAtTime(points[2].value, points[2].time);
      gain.gain.exponentialRampToValueAtTime(points[3].value, points[3].time);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(start); oscillator.stop(start + .51);
    }
    const data = (await context.startRendering()).getChannelData(0);
    const rms = (a: number, b: number) => { const slice = data.slice(a * 44100, b * 44100); return Math.sqrt(slice.reduce((s, v) => s + v * v, 0) / slice.length); };
    return { held: rms(.35, .43), attack: rms(.04, .12), boundary: rms(.495, .5), next: rms(.54, .62), silence: rms(1.6, 1.9), peak: data.reduce((p, v) => Math.max(p, Math.abs(v)), 0) };
  });
  expect(measured.held).toBeGreaterThan(measured.attack * .7);
  expect(measured.boundary).toBeLessThan(measured.held * .05);
  expect(measured.next).toBeGreaterThan(measured.held);
  expect(measured.silence).toBe(0);
  expect(measured.peak).toBeLessThan(1);
});

test("up and down pick colours differ without shifting onsets or cutting resonance", async ({ page }) => {
  await page.goto("/");
  const measured = await page.evaluate(async () => {
    const path = "/src/pluckedTone.ts";
    const { preparePluckedBuffers, createPluckedVoice } = await import(path);
    async function render(stroke: string) {
      const context = new OfflineAudioContext(1, 44100 * 2, 44100);
      const buffers = await preparePluckedBuffers(context, [64]);
      createPluckedVoice(context, buffers.get(64)!, .1, 1, .3, 0, stroke);
      const data = (await context.startRendering()).getChannelData(0);
      const rms = (a: number, b: number) => { const slice = data.slice(a * 44100, b * 44100); return Math.sqrt(slice.reduce((s, v) => s + v * v, 0) / slice.length); };
      let energy = 0, difference = 0;
      for (let i = 5000; i < 10000; i++) { energy += data[i] ** 2; difference += (data[i] - data[i - 1]) ** 2; }
      return { brightness: difference / energy, before: rms(0, .09), tail: rms(.8, .9), silence: rms(1.4, 1.8), peak: data.reduce((p, v) => Math.max(p, Math.abs(v)), 0) };
    }
    return { up: await render("U"), down: await render("D") };
  });
  expect(measured.up.brightness).toBeGreaterThan(measured.down.brightness * 1.2);
  for (const result of [measured.up, measured.down]) {
    expect(result.before).toBe(0); expect(result.tail).toBeGreaterThan(.001);
    expect(result.silence).toBe(0); expect(result.peak).toBeLessThan(1);
  }
});
