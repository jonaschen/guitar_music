// Experimental additive pluck, generated locally; no external audio samples.
// Each harmonic decays separately, so brightness falls as a string rings.
export function pluckedSamples(midi: number, sampleRate: number, seconds = 4): Float32Array {
  const samples = new Float32Array(Math.ceil(sampleRate * seconds));
  const fundamental = 440 * 2 ** ((midi - 69) / 12);
  const partials = Math.min(12, Math.floor(sampleRate * 0.45 / fundamental));
  for (let harmonic = 1; harmonic <= partials; harmonic++) {
    const amplitude = 0.55 / harmonic ** 1.5;
    const frequency = fundamental * harmonic;
    const damping = 0.9 + harmonic * 0.24;
    for (let index = 0; index < samples.length; index++) {
      const time = index / sampleRate;
      samples[index] += amplitude * Math.sin(2 * Math.PI * frequency * time)
        * Math.exp(-time * damping) * (1 - Math.exp(-time / 0.006));
    }
  }
  // The buffer itself also ends smoothly, including long sustained notes.
  const fade = Math.min(samples.length, Math.floor(sampleRate * 0.08));
  for (let index = 0; index < fade; index++) samples[samples.length - fade + index] *= 1 - index / fade;
  return samples;
}

const cache = new WeakMap<BaseAudioContext, Map<number, AudioBuffer>>();

export async function preparePluckedBuffers(context: BaseAudioContext, pitches: number[], cancelled: () => boolean = () => false) {
  const buffers = cache.get(context) ?? new Map<number, AudioBuffer>();
  cache.set(context, buffers);
  const prepared = new Map<number, AudioBuffer>();
  for (const pitch of new Set(pitches)) {
    if (cancelled()) break;
    let buffer = buffers.get(pitch);
    if (!buffer) {
      const data = pluckedSamples(pitch, context.sampleRate);
      buffer = context.createBuffer(1, data.length, context.sampleRate);
      buffer.getChannelData(0).set(data);
      if (buffers.size >= 64) buffers.delete(buffers.keys().next().value!);
      buffers.set(pitch, buffer);
      // Let Stop and other UI actions run while preparing a whole song.
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    }
    prepared.set(pitch, buffer);
  }
  return prepared;
}

export function createPluckedVoice(context: BaseAudioContext, buffer: AudioBuffer, start: number, end: number, level: number, offset = 0) {
  if (offset >= buffer.duration || end <= start || level <= 0) return null;
  const source = context.createBufferSource();
  source.buffer = buffer;
  const gain = context.createGain();
  // Resume a decayed string at its age, not a fresh attack when seeking.
  gain.gain.setValueAtTime(offset > 0 ? 0 : level, start);
  if (offset > 0) gain.gain.linearRampToValueAtTime(level, Math.min(end, start + 0.008));
  gain.gain.setValueAtTime(level, end);
  gain.gain.exponentialRampToValueAtTime(0.00001, end + 0.28);
  source.connect(gain).connect(context.destination);
  source.addEventListener("ended", () => { source.disconnect(); gain.disconnect(); });
  source.start(start, offset);
  source.stop(end + 0.29);
  return source;
}
