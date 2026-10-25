import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import type { PlaybackManifest, SongScore } from "../src/types";

const API = process.env.GUITARSCRIBE_API_URL ?? "http://127.0.0.1:8000";
const JOB_ID = "known-events-diagnostic";

const notes: SongScore["melody"] = [
  { id: "repeat-a", start: .25, end: .55, midi: 60, note: "C4", confidence: 1, string: 2, fret: 1, origin: "user", edited: true },
  { id: "repeat-b", start: .55, end: .85, midi: 60, note: "C4", confidence: 1, string: 2, fret: 1, origin: "user", edited: true },
  { id: "after-rest", start: 1.1, end: 1.4, midi: 64, note: "E4", confidence: 1, string: 1, fret: 5, origin: "user", edited: true },
  { id: "cross-bar", start: 1.1, end: 3, midi: 67, note: "G4", confidence: 1, string: 1, fret: 3, origin: "user", edited: true },
];

function knownScore(): SongScore {
  return {
    schema_version: "1.0",
    song: { title: "Known Events Diagnostic", source_type: "local", duration_seconds: 4, source_start_seconds: 0 },
    analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: 1, warnings: [] },
    key_context: {
      source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" },
      shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" },
      transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true,
    },
    guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
    beats: Array.from({ length: 8 }, (_, index) => ({
      time: index * .5, beat: index % 4 + 1, measure: Math.floor(index / 4) + 1, confidence: 1,
    })),
    chords: [],
    melody: notes,
    rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
    provenance: { beat_engine: "diagnostic", chord_engine: "diagnostic", melody_engine: "hand-authored", parameters: {} },
  };
}

function wavFile(): Buffer {
  const sampleRate = 8000, frames = sampleRate;
  const data = Buffer.alloc(44 + frames * 2);
  data.write("RIFF", 0); data.writeUInt32LE(data.length - 8, 4); data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(sampleRate, 24); data.writeUInt32LE(sampleRate * 2, 28);
  data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write("data", 36); data.writeUInt32LE(frames * 2, 40);
  return data;
}

async function installAudioProbe(page: Page) {
  await page.addInitScript(() => {
    type Automation = { method: string; value: number; time: number };
    type OscillatorRecord = { frequency: number; starts: number[]; stops: number[]; automation: Automation[] };
    const oscillators: OscillatorRecord[] = [];
    const contexts: AudioContext[] = [];
    (window as any).__knownEventsProbe = { oscillators, contexts };

    const prototype = AudioContext.prototype;
    const gainAutomation = new WeakMap<AudioParam, Automation[]>();
    const createGain = prototype.createGain;
    prototype.createGain = function () {
      const gain = createGain.call(this), events: Automation[] = [];
      gainAutomation.set(gain.gain, events);
      return gain;
    };

    const audioParamPrototype = AudioParam.prototype as any;
    for (const method of ["setValueAtTime", "linearRampToValueAtTime", "exponentialRampToValueAtTime"] as const) {
      const descriptor = Object.getOwnPropertyDescriptor(audioParamPrototype, method);
      if (!descriptor || typeof descriptor.value !== "function") continue;
      const original = descriptor.value;
      Object.defineProperty(audioParamPrototype, method, {
        ...descriptor,
        value: function (this: AudioParam, value: number, time: number) {
          gainAutomation.get(this)?.push({ method, value, time });
          return original.call(this, value, time);
        },
      });
    }

    const createOscillator = prototype.createOscillator;
    prototype.createOscillator = function () {
      const context = this;
      if (!contexts.includes(context)) contexts.push(context);
      const oscillator = createOscillator.call(this);
      const row: OscillatorRecord = { frequency: NaN, starts: [], stops: [], automation: [] };
      oscillators.push(row);
      const connect = oscillator.connect.bind(oscillator);
      oscillator.connect = ((target: AudioNode) => {
        if (target instanceof GainNode) row.automation = gainAutomation.get(target.gain) ?? [];
        return connect(target);
      }) as typeof oscillator.connect;
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

function frequencyFor(midi: number) {
  return 440 * 2 ** ((midi - 69) / 12);
}

async function probe(page: Page) {
  return page.evaluate(() => {
    const state = (window as any).__knownEventsProbe;
    return {
      now: Math.max(0, ...state.contexts.map((context: AudioContext) => context.currentTime)),
      oscillators: state.oscillators.map((row: any) => ({
        frequency: row.frequency,
        starts: [...row.starts],
        stops: [...row.stops],
        automation: [...row.automation],
      })),
    };
  });
}

async function prepareDiagnostic(page: Page, request: APIRequestContext) {
  const score = knownScore();
  const compiled = await request.post(`${API}/scores/playback/manifest`, { data: score });
  expect(compiled.status(), "the live playback compiler must be available").toBe(200);
  const manifest = await compiled.json() as PlaybackManifest;

  const expected = notes.map(note => ({ start: note.start, end: note.end, midi: note.midi }));
  const compiledMelody = manifest.events
    .filter(event => event.track === "melody")
    .map(event => ({ start: event.start, end: event.end, midi: event.pitches[0] }));
  expect(compiledMelody).toEqual(expected);

  await installAudioProbe(page);
  await page.addInitScript(() => {
    localStorage.setItem("guitarscribe.workspaceMode", "full");
    localStorage.removeItem("guitarscribe.savedVersion");
  });
  const unexpectedWrites: string[] = [];
  page.on("request", browserRequest => {
    if (browserRequest.method() !== "GET" && browserRequest.method() !== "HEAD"
      && !["/scores/playback/manifest", "/scores/musicxml"].includes(new URL(browserRequest.url()).pathname)) {
      unexpectedWrites.push(`${browserRequest.method()} ${new URL(browserRequest.url()).pathname}`);
    }
  });

  await page.route("**/api/v1/capabilities", route => route.fulfill({ json: {
    beat_engine: "librosa", chord_engine: "chromagram", improved_accompaniment: false,
    youtube_enabled: false, vocal_separation_enabled: false, melody_available: true,
    recommended_analysis_seconds: 45,
  } }));
  await page.route(`**/api/v1/jobs/${JOB_ID}`, route => route.fulfill({ json: {
    id: JOB_ID, status: "completed", progress: 100, message: "Analysis complete",
    source_type: "local", melody_mode: "guitar", separate_vocals: false,
    chord_complexity: "standard", skip_seconds: 0, analysis_seconds: null,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    error: null, artifacts: ["source"], score,
  } }));
  await page.route(`**/api/v1/jobs/${JOB_ID}/audio`, route => route.fulfill({
    contentType: "audio/wav", body: wavFile(),
  }));
  await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
  await page.route("**/scores/playback/manifest", route => route.fulfill({ json: manifest }));
  await page.goto(`/?job=${JOB_ID}`, { waitUntil: "domcontentloaded", timeout: 15_000 });
  await page.getByText("Compiled score playback", { exact: true }).click();
  await page.getByLabel("guitar track", { exact: true }).setChecked(false);
  await page.getByLabel("melody track", { exact: true }).setChecked(true);
  await page.getByLabel("metronome track", { exact: true }).setChecked(false);
  await page.getByLabel("Count-in").selectOption("0");
  return { score, manifest, unexpectedWrites };
}

test("known rest, repeated-note and cross-bar events schedule, pause, resume and loop without hanging", async ({ page, request }) => {
  test.setTimeout(30_000);
  const { manifest, unexpectedWrites } = await prepareDiagnostic(page, request);

  await page.getByRole("button", { name: "Play score", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause score", exact: true })).toBeVisible();
  await expect.poll(async () => (await probe(page)).oscillators.filter(row => row.starts.length).length, {
    intervals: [20], timeout: 5000,
  }).toBe(4);

  const firstPass = await probe(page);
  const melodyRows = firstPass.oscillators
    .filter(row => Math.abs(69 + 12 * Math.log2(row.frequency / 440) - Math.round(69 + 12 * Math.log2(row.frequency / 440))) < .01)
    .filter(row => [60, 64, 67].some(midi => Math.abs(row.frequency - frequencyFor(midi)) < .01))
    .sort((left, right) => left.starts[0] - right.starts[0]);
  expect(melodyRows).toHaveLength(4);

  const origin = melodyRows[0].starts[0] - notes[0].start;
  for (const [index, note] of notes.entries()) {
    const row = melodyRows[index];
    expect(69 + 12 * Math.log2(row.frequency / 440)).toBeCloseTo(note.midi, 7);
    expect(Math.abs(row.starts[0] - origin - note.start)).toBeLessThanOrEqual(.001);
    const gainEnd = row.automation.filter(event => event.value === 0).at(-1);
    expect(gainEnd).toBeDefined();
    expect(Math.abs(gainEnd!.time - origin - note.end)).toBeLessThanOrEqual(.001);
    expect(row.stops[0] - gainEnd!.time).toBeGreaterThanOrEqual(0);
    expect(row.stops[0] - gainEnd!.time).toBeLessThanOrEqual(.001);
    expect(Math.abs(row.stops[0] - origin - note.end)).toBeLessThanOrEqual(.001);
    expect(row.stops).toHaveLength(1);
  }
  expect(Math.abs(melodyRows[0].starts[0] - melodyRows[1].starts[0] + .3)).toBeLessThanOrEqual(.001);
  expect(Math.abs((melodyRows[3].stops[0] - melodyRows[3].starts[0]) - (notes[3].end - notes[3].start))).toBeLessThanOrEqual(.001);
  expect(manifest.events.filter(event => event.track === "melody")).toHaveLength(4);

  const longNoteFrequency = frequencyFor(67);
  const longRowStart = melodyRows[3].starts[0];
  await expect.poll(async () => {
    const state = await probe(page);
    return state.now >= longRowStart + .05;
  }, { intervals: [20], timeout: 1500 }).toBe(true);
  await page.getByRole("button", { name: "Pause score", exact: true }).click();
  const paused = await probe(page);
  const pausedLong = paused.oscillators.find(row => Math.abs(row.frequency - longNoteFrequency) < .01)!;
  expect(pausedLong.stops.length).toBeGreaterThan(1);
  expect(pausedLong.stops.at(-1)).toBeLessThan(pausedLong.stops[0]);
  expect(pausedLong.stops.at(-1)).toBeGreaterThan(longRowStart);
  expect(pausedLong.stops.at(-1)).toBeLessThan(longRowStart + .6);
  expect(paused.now - pausedLong.stops.at(-1)!).toBeGreaterThanOrEqual(0);
  expect(paused.now - pausedLong.stops.at(-1)!).toBeLessThanOrEqual(.05);

  const beforeResume = paused.oscillators.filter(row => Math.abs(row.frequency - longNoteFrequency) < .01).length;
  await page.getByRole("button", { name: "Play score", exact: true }).click();
  await expect.poll(async () => (await probe(page)).oscillators.filter(row => Math.abs(row.frequency - longNoteFrequency) < .01).length, {
    intervals: [20], timeout: 2500,
  }).toBeGreaterThan(beforeResume);
  await page.getByRole("button", { name: "Stop score", exact: true }).click();
  const afterResumeStop = await probe(page);
  const startsAfterResumeStop = afterResumeStop.oscillators.reduce((total, row) => total + row.starts.length, 0);

  await page.getByRole("button", { name: "Loop bar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Looping bar", exact: true })).toBeVisible();
  const beforeLoopLongs = (await probe(page)).oscillators.filter(row => Math.abs(row.frequency - longNoteFrequency) < .01).length;
  await page.getByRole("button", { name: "Play score", exact: true }).click();
  await expect.poll(async () => (await probe(page)).oscillators.filter(row => Math.abs(row.frequency - longNoteFrequency) < .01).length, {
    intervals: [20], timeout: 6000,
  }).toBeGreaterThanOrEqual(beforeLoopLongs + 2);
  const loopState = await probe(page);
  const loopLongs = loopState.oscillators
    .filter(row => Math.abs(row.frequency - longNoteFrequency) < .01)
    .slice(beforeLoopLongs);
  expect(loopLongs[1].starts[0] - loopLongs[0].starts[0]).toBeCloseTo(2, 1);
  await expect.poll(async () => {
    const state = await probe(page);
    return state.now >= loopLongs[1].starts[0] + .05 && state.now < loopLongs[1].stops[0] - .05;
  }, { intervals: [20], timeout: 1500 }).toBe(true);
  const beforeLoopStop = await probe(page);
  expect(beforeLoopStop.now).toBeLessThan(loopLongs[1].stops[0]);
  await page.getByRole("button", { name: "Stop score", exact: true }).click();
  const stopped = await probe(page);
  const stoppedLongs = stopped.oscillators
    .filter(row => Math.abs(row.frequency - longNoteFrequency) < .01)
    .slice(beforeLoopLongs);
  const stoppedLoopTail = stoppedLongs[1].stops.at(-1)!;
  expect(stoppedLongs[1].stops.length, JSON.stringify({ beforeLoopStop, loopLong: loopLongs[1], stopped: stoppedLongs[1] })).toBeGreaterThan(1);
  expect(stoppedLoopTail).toBeLessThan(stoppedLongs[1].stops[0]);
  expect(stoppedLoopTail).toBeGreaterThan(loopLongs[1].starts[0]);
  expect(stopped.now - stoppedLoopTail).toBeGreaterThanOrEqual(0);
  expect(stopped.now - stoppedLoopTail).toBeLessThanOrEqual(.05);
  const startsAtStop = stopped.oscillators.reduce((total, row) => total + row.starts.length, 0);
  await page.waitForTimeout(350);
  const afterStop = await probe(page);
  expect(afterStop.oscillators.reduce((total, row) => total + row.starts.length, 0)).toBe(startsAtStop);
  expect(afterStop.oscillators.every(row => row.starts.length === 0 || row.stops.length > 0)).toBe(true);
  expect(afterStop.oscillators.reduce((total, row) => total + row.starts.length, 0)).toBeGreaterThan(startsAfterResumeStop);
  expect(unexpectedWrites).toEqual([]);
});
