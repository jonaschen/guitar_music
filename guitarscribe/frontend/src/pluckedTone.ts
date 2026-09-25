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
