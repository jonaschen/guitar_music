export type MelodyTone = { start: number; end: number; midi: number; velocity?: number };

// Join only touching, different pitches. Keep rests, overlapping voices and
// explicit repeated-note attacks. No pitch smoothing or duration quantization.
export function melodyPhrases(notes: readonly MelodyTone[]): MelodyTone[][] {
  const phrases: MelodyTone[][] = [];
  for (const note of [...notes].sort((a, b) => a.start - b.start)) {
    if (!Number.isFinite(note.start + note.end + note.midi) || note.end <= note.start) continue;
    const phrase = phrases.at(-1);
    const previous = phrase?.at(-1);
    if (previous && previous.end === note.start && previous.midi !== note.midi) phrase!.push(note);
    else phrases.push([note]);
  }
  return phrases;
}

export function playMelodyPhrase(context: BaseAudioContext, notes: readonly MelodyTone[], options: {
  scoreStart: number; scoreEnd: number; contextStart: number; rate: number; peak: number; type?: OscillatorType;
}): OscillatorNode | null {
  const { scoreStart, scoreEnd, contextStart, rate, peak } = options;
  if (!(rate > 0) || !notes.length) return null;
  const from = Math.max(scoreStart, notes[0].start, scoreStart + (context.currentTime + .005 - contextStart) * rate);
  const until = Math.min(scoreEnd, notes[notes.length - 1].end);
  const audible = notes.filter(note => note.end > from && note.start < until);
  if (!audible.length || until <= from) return null;
  const at = (time: number) => contextStart + (time - scoreStart) / rate;
  const start = at(from), end = at(until);
  // Keep fades inside their boundary notes, even for sub-millisecond edits.
  const edge = Math.min(.005, (end - start) / 4,
    (at(Math.min(until, audible[0].end)) - start) / 2,
    (end - at(Math.max(from, audible[audible.length - 1].start))) / 2);
  const source = context.createOscillator(), gain = context.createGain();
  source.type = options.type ?? "triangle";
  const level = (note: MelodyTone) => peak * (note.velocity ?? 127) / 127;
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(level(audible[0]), start + edge);
  for (let i = 0; i < audible.length; i++) {
    const note = audible[i];
    const time = at(Math.max(from, note.start));
    source.frequency.setValueAtTime(440 * 2 ** ((note.midi - 69) / 12), time);
    // Keep the oscillator phase and nonzero gain across internal boundaries.
    if (i > 0) gain.gain.setValueAtTime(level(note), Math.max(start + edge, time));
  }
  gain.gain.setValueAtTime(level(audible[audible.length - 1]), end - edge);
  gain.gain.linearRampToValueAtTime(0, end);
  source.connect(gain).connect(context.destination);
  source.start(start); source.stop(end);
  return source;
}
