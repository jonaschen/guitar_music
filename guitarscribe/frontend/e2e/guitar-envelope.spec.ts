import { expect, test } from "@playwright/test";
import { guitarEnvelope } from "../src/guitarEnvelope";

test("guitar sustain stays audible until the final release within each note", () => {
  for (const duration of [0.01, 0.25, 0.5, 2]) {
    const points = guitarEnvelope(1, 1 + duration, 0.1);
    expect(points[0].time).toBe(1);
    expect(points.at(-1)?.time).toBe(1 + duration);
    expect(points[3].value).toBeCloseTo(0.035);
    expect(points[3].time).toBeGreaterThanOrEqual(1 + duration * 0.8);
    for (let index = 1; index < points.length; index++) {
      expect(points[index].time).toBeGreaterThan(points[index - 1].time);
      expect(points[index].value).toBeGreaterThan(0);
    }
  }
});

test("rendered guitar tone retains energy late in a note and releases at its end", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async (points) => {
    const context = new OfflineAudioContext(1, 44100, 44100);
    const oscillator = context.createOscillator();
    oscillator.type = "triangle";
    oscillator.frequency.value = 220;
    const gain = context.createGain();
    gain.gain.setValueAtTime(points[0].value, points[0].time);
    gain.gain.linearRampToValueAtTime(points[1].value, points[1].time);
    points.slice(2).forEach((point) => gain.gain.exponentialRampToValueAtTime(point.value, point.time));
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(0);
    oscillator.stop(0.5);
    const data = (await context.startRendering()).getChannelData(0);
    const rms = (start: number, end: number) => {
      const samples = data.slice(Math.floor(start * 44100), Math.floor(end * 44100));
      return Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
    };
    return { early: rms(0.02, 0.08), late: rms(0.38, 0.44), after: rms(0.55, 0.65) };
  }, guitarEnvelope(0, 0.5, 0.1));
  expect(result.late).toBeGreaterThan(result.early * 0.25);
  expect(result.after).toBe(0);
});
