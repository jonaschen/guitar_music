import { expect, test, type Page } from "@playwright/test";
import type { SongScore } from "../src/types";

type Note = SongScore["melody"][number];

function shortScore(barSeconds: number, melody: Note[]): SongScore {
  return {
    schema_version: "1.0",
    song: { title: "Realtime melody loop", source_type: "local", duration_seconds: barSeconds * 4 },
    analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: .5, warnings: [] },
    key_context: {
      source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" },
      shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" },
      transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true,
    },
    guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
    beats: Array.from({ length: 16 }, (_, i) => ({
      time: i * barSeconds / 4, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1,
    })),
    chords: [], melody,
    rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
    provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
  };
}

function note(id: string, midi: number, start: number, end: number): Note {
  const names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
  return {
    id, midi, note: `${names[midi % 12]}${Math.floor(midi / 12) - 1}`, start, end,
    confidence: .5, string: 2, fret: Math.max(0, midi - 59), origin: "model", edited: false,
  };
}

function wavFile(): Buffer {
  const sampleRate = 8000, frames = sampleRate * 2;
  const data = Buffer.alloc(44 + frames * 2);
  data.write("RIFF", 0); data.writeUInt32LE(data.length - 8, 4); data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(sampleRate, 24); data.writeUInt32LE(sampleRate * 2, 28);
  data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write("data", 36); data.writeUInt32LE(frames * 2, 40);
  return data;
}

async function installAudioProbe(page: Page) {
  await page.addInitScript(() => {
    const state: Array<{ frequency: number; starts: number[]; stops: number[] }> = [];
    (window as any).__melodyOscillators = state;
    const prototype = AudioContext.prototype;
    const createOscillator = prototype.createOscillator;
    prototype.createOscillator = function () {
      const context = this;
      const oscillator = createOscillator.call(this);
      const row = { frequency: NaN, starts: [] as number[], stops: [] as number[] };
      state.push(row);
      const setFrequency = oscillator.frequency.setValueAtTime.bind(oscillator.frequency);
      oscillator.frequency.setValueAtTime = ((value: number, time: number) => {
        row.frequency = value;
        return setFrequency(value, time);
      }) as typeof oscillator.frequency.setValueAtTime;
      const start = oscillator.start.bind(oscillator);
      oscillator.start = ((time?: number) => {
        row.starts.push(time ?? context.currentTime);
        return time === undefined ? start() : start(time);
      }) as typeof oscillator.start;
      const stop = oscillator.stop.bind(oscillator);
      oscillator.stop = ((time?: number) => {
        row.stops.push(time ?? context.currentTime);
        return time === undefined ? stop() : stop(time);
      }) as typeof oscillator.stop;
      return oscillator;
    };
  });
}

async function setup(page: Page, score: SongScore) {
  await installAudioProbe(page);
  await page.addInitScript(() => localStorage.removeItem("guitarscribe.workspaceMode"));
  await page.route("**/api/v1/jobs/realtime", route => route.fulfill({ json: {
    id: "realtime", status: "completed", progress: 100, artifacts: ["source"], score,
  } }));
  await page.route("**/api/v1/jobs/realtime/audio", route => route.fulfill({
    status: 200, contentType: "audio/wav", body: wavFile(),
  }));
  await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
  await page.goto("/?job=realtime");
  await expect(page.getByRole("button", { name: "顯示完整工具", exact: true })).toBeVisible();
  await page.getByLabel("Tab bar count").selectOption("1");
  await page.getByLabel("Editor audition mode").selectOption("melody");
  await page.getByLabel("Melody connection").selectOption("separate");
}

function frequencyFor(midi: number) {
  return 440 * 2 ** ((midi - 69) / 12);
}

async function noteStarts(page: Page, midi: number): Promise<number[]> {
  return page.evaluate((frequency) => (window as any).__melodyOscillators
    .filter((oscillator: { frequency: number }) => Math.abs(oscillator.frequency - frequency) < .01)
    .flatMap((oscillator: { starts: number[] }) => oscillator.starts), frequencyFor(midi));
}

async function oscillatorStopCalls(page: Page): Promise<number> {
  return page.evaluate(() => (window as any).__melodyOscillators
    .reduce((count: number, oscillator: { stops: number[] }) => count + oscillator.stops.length, 0));
}

const fastLoopScore = shortScore(.4, [note("a", 60, .02, .08), note("b", 64, .22, .28)]);
const resumeLoopScore = shortScore(1.2, [note("a", 60, .05, .13), note("b", 64, .85, .95)]);

test("solo loop keeps a steady onset interval over three passes without adding 30ms per pass", async ({ page }) => {
  await setup(page, fastLoopScore);
  await page.getByLabel("Loop edited bars").check();
  // Keep rendering alive but withhold RAF callbacks; loop scheduling must use its timer look-ahead.
  await page.evaluate(() => Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true, value: () => 1,
  }));
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();

  await expect.poll(async () => (await noteStarts(page, 60)).length, { intervals: [20], timeout: 6000 }).toBeGreaterThanOrEqual(3);
  const starts = await noteStarts(page, 60);
  const loopPeriod = .4;
  const intervals = starts.slice(1, 3).map((time, index) => time - starts[index]);
  expect(intervals[0]).toBeGreaterThan(loopPeriod - .02);
  expect(intervals[0]).toBeLessThan(loopPeriod + .02);
  expect(intervals[1]).toBeGreaterThan(loopPeriod - .02);
  expect(intervals[1]).toBeLessThan(loopPeriod + .02);
  expect(Math.abs(intervals[0] - intervals[1])).toBeLessThan(.01);
});

test("pause and resume preserve the original complete solo loop range", async ({ page }) => {
  await setup(page, resumeLoopScore);
  await page.getByLabel("Loop edited bars").check();
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  const position = () => page.getByLabel("Tab transport position").innerText()
    .then(text => Number(text.match(/位置 ([\d.]+)s/)?.[1]));
  await expect.poll(position, { intervals: [20], timeout: 4000 }).toBeGreaterThan(.35);
  await expect.poll(position, { intervals: [20] }).toBeLessThan(.8);

  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  const pitchAStartsBeforeResume = (await noteStarts(page, 60)).length;
  const pitchBStartsBeforeResume = (await noteStarts(page, 64)).length;
  await page.getByRole("button", { name: "從暫停位置續播", exact: true }).click();

  await expect.poll(async () => (await noteStarts(page, 64)).length, { intervals: [20], timeout: 3000 }).toBeGreaterThan(pitchBStartsBeforeResume);
  await expect.poll(async () => (await noteStarts(page, 60)).length, { intervals: [20], timeout: 5000 })
    .toBeGreaterThanOrEqual(pitchAStartsBeforeResume + 2);
  const resumedPassStarts = (await noteStarts(page, 60)).slice(pitchAStartsBeforeResume);
  const loopPeriod = 1.2;
  const resumedIntervals = resumedPassStarts.slice(1).map((time, index) => time - resumedPassStarts[index]);
  expect(resumedIntervals.length).toBeGreaterThanOrEqual(1);
  expect(resumedIntervals[0]).toBeGreaterThan(loopPeriod - .025);
  expect(resumedIntervals[0]).toBeLessThan(loopPeriod + .025);
});

test("stopping a solo loop prevents any later oscillator scheduling", async ({ page }) => {
  await setup(page, fastLoopScore);
  await page.getByLabel("Loop edited bars").check();
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  await expect.poll(async () => (await noteStarts(page, 60)).length, { intervals: [20], timeout: 4000 }).toBeGreaterThanOrEqual(2);

  const stopCallsBefore = await oscillatorStopCalls(page);
  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  await expect.poll(() => oscillatorStopCalls(page)).toBeGreaterThan(stopCallsBefore);
  const startsAfterStop = (await noteStarts(page, 60)).length;
  await page.waitForTimeout(750);
  expect(await noteStarts(page, 60)).toHaveLength(startsAfterStop);
});
