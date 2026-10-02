// Sustain through the written duration, with a short release inside the note
// boundary so repeated pitches articulate without lengthening the score.
export function melodyEnvelope(start: number, end: number, peak: number) {
  const duration = Math.max(0.001, end - start);
  return [
    { time: start, value: 0.0001 },
    { time: start + Math.min(0.008, duration * 0.15), value: peak },
    { time: end - Math.min(0.035, duration * 0.2), value: peak * 0.8 },
    { time: end, value: 0.0001 },
  ];
}
