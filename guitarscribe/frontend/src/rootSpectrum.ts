/** A frequency-energy display, NOT a bass tracker or a root estimator. */
export const SPECTRUM_RATE = 11025;
export const SPECTRUM_SIZE = 8192;
export const SPECTRUM_LOW_MIDI = 28; // E1, including a standard bass's low E.
export const SPECTRUM_HIGH_MIDI = 64; // E4.
export const SPECTRUM_ROWS = 145; // Quarter-semitone sampling of the FFT, not added resolution.
export type SpectrumData = {values: Float32Array; columns: number; rows: number; duration: number; hop: number; rate: number; peak: number};
export const midiHz = (midi: number) => 440 * 2 ** ((midi - 69) / 12);
export const spectrumMidi = (row: number) => SPECTRUM_HIGH_MIDI - row * (SPECTRUM_HIGH_MIDI - SPECTRUM_LOW_MIDI) / (SPECTRUM_ROWS - 1);
export function fft(real: Float64Array, imag: Float64Array) {
  const n = real.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [real[i], real[j]] = [real[j], real[i]]; [imag[i], imag[j]] = [imag[j], imag[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const angle = -2 * Math.PI / len, wr = Math.cos(angle), wi = Math.sin(angle);
    for (let i = 0; i < n; i += len) {
      let ur = 1, ui = 0;
      for (let j = 0; j < len / 2; j++) {
        const a = i + j, b = a + len / 2;
        const vr = real[b] * ur - imag[b] * ui, vi = real[b] * ui + imag[b] * ur;
        real[b] = real[a] - vr; imag[b] = imag[a] - vi;
        real[a] += vr; imag[a] += vi;
        const next = ur * wr - ui * wi; ui = ur * wi + ui * wr; ur = next;
      }
    }
  }
}
export function makeSpectrum(channels: Float32Array[], rate: number, progress?: (fraction: number) => void): SpectrumData {
  if (!channels.length || channels.length > 2 || !Number.isFinite(rate) || rate < 8000 || channels.some(c => c.length !== channels[0].length) || !channels[0].length) throw Error('Invalid spectrum audio');
  const samples = channels[0].length, n = SPECTRUM_SIZE;
  const hop = Math.max(256, Math.ceil(samples / 2200)), columns = Math.ceil(samples / hop), rows = SPECTRUM_ROWS;
  const values = new Float32Array(columns * rows), real = new Float64Array(n), imag = new Float64Array(n);
  const power = new Float64Array(n / 2 + 1), window = Float64Array.from({length: n}, (_, i) => .5 - .5 * Math.cos(2 * Math.PI * i / (n - 1)));
  const bins = Float64Array.from({length: rows}, (_, r) => midiHz(spectrumMidi(r)) * n / rate);
  let peak = -120;
  for (let col = 0; col < columns; col++) {
    power.fill(0);
    // Each column describes its interval midpoint. Pad at edges, never shift source time.
    const start = Math.round(Math.min(samples - 1, (col + .5) * hop)) - n / 2;
    for (const channel of channels) {
      for (let i = 0; i < n; i++) real[i] = (channel[start + i] ?? 0) * window[i];
      imag.fill(0); fft(real, imag);
      for (let k = 0; k < power.length; k++) power[k] += (real[k] ** 2 + imag[k] ** 2) / channels.length / ((n / 2) ** 2);
    }
    for (let row = 0; row < rows; row++) {
      const k = Math.floor(bins[row]), f = bins[row] - k;
      const db = 10 * Math.log10(Math.max(1e-12, power[k] * (1 - f) + power[k + 1] * f));
      values[col * rows + row] = db; peak = Math.max(peak, db);
    }
    if (col % 40 === 0) progress?.(col / columns);
  }
  return {values, columns, rows, duration: samples / rate, hop, rate, peak};
}
export function spectrumColor(db: number, peak: number, range: number): [number, number, number] {
  // Fixed whole-recording reference; silence cannot become a bright normalized column.
  const value = Math.max(0, Math.min(1, (db - Math.max(-100, peak - range)) / range));
  const stops = [[20, 36, 64], [35, 100, 139], [79, 172, 179], [242, 201, 95], [255, 247, 218]];
  const x = value * 4, i = Math.min(3, Math.floor(x)), f = x - i;
  return stops[i].map((a, j) => Math.round(a + (stops[i + 1][j] - a) * f)) as [number, number, number];
}
