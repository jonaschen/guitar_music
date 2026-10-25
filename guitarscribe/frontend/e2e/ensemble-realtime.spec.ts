import { expect, test, type Page } from "@playwright/test";
import type { SongScore } from "../src/types";

type Note = SongScore["melody"][number];

function makeScore(barSeconds: number): SongScore {
  return {
    schema_version: "1.0",
    song: { title: "Realtime ensemble loop", source_type: "local", duration_seconds: barSeconds * 4 },
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
    chords: [{ id: "c1", start: 0, end: barSeconds * 4, symbol: "C", confidence: 1, origin: "model", edited: false, voicing_id: null, available_voicings: [], roman_numeral: "I", harmonic_function: "tonic", theory_confidence: 1 }],
    melody: [{ id: "n1", start: .02, end: .08, midi: 60, note: "C4", confidence: .5, string: 2, fret: 1, origin: "model", edited: false } as Note],
    rhythm: { subdivision: 8, pattern_id: "basic_8th", display: ["D", null, "D", "U"], confidence: 1, label: "Basic pattern" },
    provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test" },
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
    const state: Array<{ frequency: number; starts: number[]; stops: number[]; gains: number[] }> = [];
    (window as any).__ensembleOscillators = state;
    const prototype = AudioContext.prototype;
    const gains = new WeakMap<GainNode, number[]>();
    const createGain = prototype.createGain;
    prototype.createGain = function () {
      const gain = createGain.call(this), values: number[] = [];
      gains.set(gain, values);
      for (const method of ["setValueAtTime", "linearRampToValueAtTime", "exponentialRampToValueAtTime"] as const) {
        const original = gain.gain[method].bind(gain.gain);
        gain.gain[method] = ((value: number, time: number) => {
          values.push(value); return original(value, time);
        }) as typeof original;
      }
      return gain;
    };
    const createOscillator = prototype.createOscillator;
    prototype.createOscillator = function () {
      const context = this;
      const oscillator = createOscillator.call(this);
      const row = { frequency: NaN, starts: [] as number[], stops: [] as number[], gains: [] as number[] };
      const connect = oscillator.connect.bind(oscillator);
      oscillator.connect = ((target: AudioNode) => {
        if (target instanceof GainNode) row.gains = gains.get(target) ?? [];
        return connect(target);
      }) as typeof oscillator.connect;
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

async function setup(page: Page, barSeconds: number) {
  const score = makeScore(barSeconds);
  const manifest = {
    revision: "ensemble-test", duration_seconds: score.song.duration_seconds, bpm: 120, time_signature: "4/4",
    events: [
      { id: "g1", track: "guitar", start: .02, end: .08, sustain_end: .08, pitches: [48], pitch_offsets: [0], pitch_velocities: [100], velocity: 100 },
      { id: "g2", track: "guitar", start: barSeconds * .55, end: barSeconds * .7, sustain_end: barSeconds * .7, pitches: [52], pitch_offsets: [0], pitch_velocities: [96], velocity: 96 },
      { id: "m1", track: "melody", start: .02, end: .08, pitches: [60], pitch_offsets: [0], pitch_velocities: [88], velocity: 88 },
      { id: "click", track: "metronome", start: .03, end: .06, pitches: [84], velocity: 112 },
    ],
  };
  await installAudioProbe(page);
  await page.addInitScript(() => localStorage.setItem("guitarscribe.workspaceMode", "full"));
  await page.route("**/api/v1/jobs/ensemble", route => route.fulfill({ json: {
    id: "ensemble", status: "completed", progress: 100, artifacts: ["source", "vocal-stem"], score,
  } }));
  await page.route("**/api/v1/jobs/ensemble/audio", route => route.fulfill({
    status: 200, contentType: "audio/wav", body: wavFile(),
  }));
  await page.route("**/api/v1/jobs/ensemble/artifacts/vocal-stem", route => route.fulfill({
    status: 200, contentType: "audio/wav", body: wavFile(),
  }));
  await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
  await page.route("**/scores/playback/manifest", route => route.fulfill({ json: manifest }));
  await page.goto("/?job=ensemble");
  await expect(page.getByRole("button", { name: "回到專注修譜", exact: true })).toBeVisible();
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await page.getByLabel("Tab bar count").selectOption("1");
  await page.getByLabel("Editor audition mode").selectOption("ensemble");
  await page.getByText("Compiled score playback", { exact: true }).click();
  await page.getByLabel("Score guitar tone").selectOption("simple");
}

function frequencyFor(midi: number) {
  return 440 * 2 ** ((midi - 69) / 12);
}

test("focus buttons isolate actual guitar events and switch source back to original", async ({page}) => {
  await setup(page, .8);
  await page.getByRole("button", {name:"回到專注修譜",exact:true}).click();
  for (const name of ["聽原曲", "聽旋律", "聽吉他伴奏", "聽合奏"]) {
    await expect(page.getByRole("button",{name,exact:true})).toBeVisible();
  }
  await page.getByRole("button",{name:"聽吉他伴奏",exact:true}).click();
  await expect.poll(async () => (await pitchStarts(page,48)).length).toBeGreaterThan(0);
  expect(await pitchStarts(page,60)).toHaveLength(0);
  expect(await pitchStarts(page,84)).toHaveLength(0);
  await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
  const guitars = (await pitchStarts(page,48)).length;
  await page.getByRole("button",{name:"聽旋律",exact:true}).click();
  await expect.poll(async () => (await pitchStarts(page,60)).length).toBeGreaterThan(0);
  expect(await pitchStarts(page,48)).toHaveLength(guitars);
  await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
  const melodies = (await pitchStarts(page,60)).length;
  await page.getByRole("button",{name:"聽合奏",exact:true}).click();
  await expect.poll(async () => (await pitchStarts(page,48)).length).toBeGreaterThan(guitars);
  await expect.poll(async () => (await pitchStarts(page,60)).length).toBeGreaterThan(melodies);
  await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
  await page.getByLabel("Editor source track").selectOption("vocal-stem");
  await expect(page.locator("audio")).toHaveAttribute("src",/artifacts\/vocal-stem$/);
  await page.getByRole("button",{name:"聽原曲",exact:true}).click();
  await expect(page.locator("audio")).toHaveAttribute("src",/ensemble\/audio$/);
  await expect(page.getByLabel("Editor source track")).toHaveValue("source");
  await expect(page.locator(".melody-editor")).toHaveCount(1);
});

for (const connection of ["connected", "separate"]) {
  test(`editor ensemble scales only melody gain by one quarter: ${connection}`, async ({page}) => {
    await setup(page, .8);
    await page.getByLabel("Melody connection").selectOption(connection);
    const peak = (midi: number) => page.evaluate(frequency => {
      const rows = (window as any).__ensembleOscillators.filter((r: any) => Math.abs(r.frequency-frequency)<.01);
      return Math.max(...rows.at(-1).gains);
    }, frequencyFor(midi));
    await page.getByRole("button",{name:"聽旋律",exact:true}).click();
    await expect.poll(async () => (await pitchStarts(page,60)).length).toBe(1);
    expect(await peak(60)).toBeCloseTo(.16, 8);
    await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
    await page.getByRole("button",{name:"聽合奏",exact:true}).click();
    await expect.poll(async () => (await pitchStarts(page,60)).length).toBe(2);
    const ensemblePeak = await peak(60), guitarPeak = await peak(48);
    expect(ensemblePeak).toBeCloseTo(.45 * 88/127 * .25,8);
    await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
    await page.getByRole("button",{name:"聽吉他伴奏",exact:true}).click();
    await expect.poll(async () => (await pitchStarts(page,48)).length).toBe(2);
    expect(await peak(48)).toBeCloseTo(guitarPeak,8);
    await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
    await page.getByRole("button",{name:"Stop",exact:true}).click();
    await page.getByLabel("melody track",{exact:true}).check();
    await page.getByRole("button",{name:"Play score",exact:true}).click();
    await expect.poll(async () => (await pitchStarts(page,60)).length).toBe(3);
    expect(await peak(60)).toBeCloseTo(ensemblePeak * 4,8);
  });
}

async function pitchStarts(page: Page, midi: number): Promise<number[]> {
  return page.evaluate((frequency) => (window as any).__ensembleOscillators
    .filter((oscillator: { frequency: number }) => Math.abs(oscillator.frequency - frequency) < .01)
    .flatMap((oscillator: { starts: number[] }) => oscillator.starts), frequencyFor(midi));
}

async function stopCalls(page: Page): Promise<number> {
  return page.evaluate(() => (window as any).__ensembleOscillators
    .reduce((count: number, oscillator: { stops: number[] }) => count + oscillator.stops.length, 0));
}

test("ensemble loop holds its bar interval within 15ms for three passes without RAF", async ({ page }) => {
  const barSeconds = .4;
  await setup(page, barSeconds);
  await page.getByLabel("Loop edited bars").check();
  // The loop transport must continue on its look-ahead timer when animation frames are withheld.
  await page.evaluate(() => Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true, value: () => 1,
  }));
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();

  await expect.poll(async () => (await pitchStarts(page, 48)).length, { intervals: [20], timeout: 6000 }).toBeGreaterThanOrEqual(3);
  const starts = await pitchStarts(page, 48);
  const intervals = starts.slice(1, 3).map((time, index) => time - starts[index]);
  for (const interval of intervals) {
    expect(interval).toBeGreaterThan(barSeconds - .02);
    expect(interval).toBeLessThanOrEqual(barSeconds + .015);
  }
  expect(Math.abs(intervals[0] - intervals[1])).toBeLessThan(.01);
});

test("ensemble pause halts scheduling, resume continues, and stop leaves no later starts", async ({ page }) => {
  const barSeconds = .8;
  await setup(page, barSeconds);
  await page.getByLabel("Loop edited bars").check();
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  await expect.poll(async () => (await pitchStarts(page, 48)).length, { intervals: [20], timeout: 4000 }).toBeGreaterThanOrEqual(2);

  await page.getByRole("button", { name: "暫停，保留位置", exact: true }).click();
  const pausedStarts = (await pitchStarts(page, 48)).length;
  await page.waitForTimeout(900);
  expect(await pitchStarts(page, 48)).toHaveLength(pausedStarts);

  await page.getByRole("button", { name: "從暫停位置續播", exact: true }).click();
  await expect.poll(async () => (await pitchStarts(page, 48)).length, { intervals: [20], timeout: 3000 }).toBeGreaterThan(pausedStarts);
  const stopsBefore = await stopCalls(page);
  await page.getByRole("button", { name: "Stop score", exact: true }).click();
  await expect.poll(() => stopCalls(page)).toBeGreaterThan(stopsBefore);
  const startsAfterStop = (await pitchStarts(page, 48)).length;
  await page.waitForTimeout(900);
  expect(await pitchStarts(page, 48)).toHaveLength(startsAfterStop);
});

test("a sustained pluck at a selected bar starts with the melody clock and keeps its string age", async ({ page }) => {
  await setup(page, .8);
  await page.getByLabel("Score guitar tone").selectOption("pluck");
  await page.route("**/scores/playback/manifest", route => route.fulfill({ json: {
    revision: "sustain", duration_seconds: 3.2, bpm: 120, time_signature: "4/4",
    events: [
      { id: "g", track: "guitar", start: 0, end: .4, sustain_end: 2.4, pitches: [48], pitch_offsets: [0], pitch_velocities: [100], velocity: 100 },
      { id: "m", track: "melody", start: .8, end: 1.1, pitches: [60], pitch_offsets: [0], pitch_velocities: [88], velocity: 88 },
    ],
  } }));
  const bar = page.getByLabel("Tab start bar");
  const value = await bar.locator("option").evaluateAll(options => options.find(o => o.textContent?.startsWith("Bar 2 ·"))?.getAttribute("value"));
  await bar.selectOption(value!);
  await page.evaluate(() => {
    (window as any).__pluckStarts = [];
    const start = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (when = 0, offset = 0) {
      (window as any).__pluckStarts.push([when, offset]); return start.call(this, when, offset);
    };
  });
  await page.getByRole("button", { name: "重播所選小節", exact: true }).click();
  await expect.poll(async () => (await pitchStarts(page, 60)).length).toBe(1);
  const melody = (await pitchStarts(page, 60))[0];
  const plucks = await page.evaluate(() => (window as any).__pluckStarts as number[][]);
  expect(plucks).toHaveLength(1);
  expect(plucks[0][0]).toBeCloseTo(melody, 8);
  expect(plucks[0][1]).toBeCloseTo(.8, 8);
});
