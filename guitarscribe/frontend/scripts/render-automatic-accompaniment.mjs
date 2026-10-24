// Render a complete preselected excerpt through the product's guitar voice.
import {chromium} from '@playwright/test';
import {readFile, writeFile, mkdir, copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const option = name => {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Required: ${name}`);
  return process.argv[index + 1];
};
const packet = path.resolve(option('--packet'));
const candidate = path.resolve(option('--candidate'));
const baseline = JSON.parse(await readFile(path.resolve(option('--baseline')), 'utf8'));
const revised = JSON.parse(await readFile(path.join(candidate, 'manifest.json'), 'utf8'));
const config = JSON.parse(await readFile(path.join(packet, 'config.json'), 'utf8'));
const candidateReport = JSON.parse(await readFile(path.join(candidate, 'report.json'), 'utf8'));
const slug = option('--slug');
assert.match(slug, /^[a-z0-9-]+$/);
const output = path.join(root, 'public/listening', slug);
await mkdir(output, {recursive: false});
const source = await readFile(path.join(packet, 'audio.wav'));
assert.equal(createHash('sha256').update(source).digest('hex'), config.audio_sha256);
assert.equal(candidateReport.source_sha256, config.audio_sha256);
assert.equal(candidateReport.duration_seconds, config.content_duration);
await writeFile(path.join(output, 'source.wav'), source);
const duration = config.content_duration, rate = 22050;
const frames = Math.ceil((duration + .35) * rate);
const browser = await chromium.launch({executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox']});
const results = [];
try {
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5173/');
  for (const [label, manifest, offset] of [
    ['original', null, 0], ['before', baseline, config.analysis_start], ['candidate', revised, 0],
  ]) {
    const events = (manifest?.events ?? []).filter(e => e.track === 'guitar'
      && (e.sustain_end ?? e.end) > offset && e.start < offset + duration);
    const result = await page.evaluate(async ({events, offset, duration, rate, frames, slug}) => {
      const {preparePluckedBuffers, createPluckedVoice} = await import('/src/pluckedTone.ts');
      const context = new OfflineAudioContext(1, frames, rate);
      const original = context.createBufferSource(), gain = context.createGain();
      original.buffer = await context.decodeAudioData(await (await fetch(`/listening/${slug}/source.wav`)).arrayBuffer());
      gain.gain.value = .45;
      gain.gain.setValueAtTime(.45, duration - .04);
      gain.gain.linearRampToValueAtTime(0, duration);
      original.connect(gain).connect(context.destination);
      original.start(0, 0, duration);
      const buffers = await preparePluckedBuffers(context, events.flatMap(e => e.pitches));
      const timings = [];
      for (const event of events) for (let i = 0; i < event.pitches.length; i++) {
        const onset = event.start + (event.pitch_offsets[i] ?? i * .012) - offset;
        const at = Math.max(0, onset), age = Math.max(0, -onset);
        if (createPluckedVoice(context, buffers.get(event.pitches[i]), at,
          Math.min(duration, (event.sustain_end ?? event.end) - offset),
          .24 * (event.pitch_velocities[i] ?? event.velocity) / 127 / Math.sqrt(event.pitches.length), age, event.stroke)) timings.push(at);
      }
      const rendered = await context.startRendering();
      const samples = Array.from(rendered.getChannelData(0));
      let peak = 0, energy = 0;
      for (const sample of samples) { peak = Math.max(peak, Math.abs(sample)); energy += sample * sample; }
      return {samples, timings, peak, rms: Math.sqrt(energy / samples.length)};
    }, {events, offset, duration, rate, frames, slug});
    const expected = events.flatMap(e => e.pitches.flatMap((_, i) => {
      const onset = e.start + (e.pitch_offsets[i] ?? i * .012) - offset;
      return Math.max(0, -onset) < 4 && Math.min(duration, (e.sustain_end ?? e.end) - offset) > Math.max(0, onset)
        ? [Math.max(0, onset)] : [];
    }));
    assert.deepEqual(result.timings, expected);
    assert.ok(result.peak < 1 && result.rms > .01);
    assert.ok(result.samples.slice(-500).every(value => Math.abs(value) < 1 / 32767));
    const wav = Buffer.alloc(44 + result.samples.length * 2);
    wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
    wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
    wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28); wav.writeUInt16LE(2, 32);
    wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40);
    result.samples.forEach((value, i) => wav.writeInt16LE(Math.round(value * 32767), 44 + i * 2));
    await writeFile(path.join(output, `${label}.wav`), wav);
    results.push({label, peak: result.peak, rms: result.rms, voices: result.timings.length,
      seconds: frames / rate, sha256: createHash('sha256').update(wav).digest('hex')});
  }
  assert.notEqual(results[1].sha256, results[2].sha256);
  await copyFile(path.join(root, 'scripts/automatic-accompaniment.html'), path.join(output, 'index.html'));
  await page.goto(`http://127.0.0.1:5173/listening/${slug}/index.html`);
  await page.waitForFunction(() => [...document.querySelectorAll('audio')].every(a => Number.isFinite(a.duration)));
  await page.locator('audio').nth(0).evaluate(a => a.play());
  await page.waitForFunction(() => document.querySelectorAll('audio')[0].currentTime > 0, null, {timeout: 10000});
  await page.locator('audio').nth(1).evaluate(a => a.play());
  await page.waitForFunction(() => {
    const players = document.querySelectorAll('audio');
    return players[0].paused && !players[1].paused && players[1].currentTime > 0;
  }, null, {timeout: 10000});
  const playback = await page.evaluate(() => {
    const players = [...document.querySelectorAll('audio')];
    const advanced = players[0].currentTime > 0;
    const exclusive = players[0].paused && !players[1].paused;
    players[1].pause();
    return {advanced, exclusive, durations: players.map(a => a.duration)};
  });
  assert.ok(playback.advanced && playback.exclusive);
  assert.ok(playback.durations.every(d => Math.abs(d - frames / rate) < .01));
  await writeFile(path.join(output, 'report.json'), JSON.stringify({
    source_sha256: config.audio_sha256, baseline_revision: baseline.revision,
    candidate_revision: revised.revision, duration, results, playback,
  }, null, 2));
} finally { await browser.close(); }
console.log(JSON.stringify({output, results}));
