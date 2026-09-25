// Notated note-off starts a short release, rather than instantly killing sound.
// Voices overlap naturally; transport stop still cancels all scheduled sources.
export function guitarEnvelope(start: number, end: number, peak: number, release = 0.12) {
  const duration = end - start;
  return [
    { time: start, value: 0.0001 },
    { time: start + Math.min(0.003, duration * 0.1), value: peak },
    { time: start + Math.min(0.18, duration * 0.35), value: Math.max(0.0001, peak * 0.6) },
    { time: end, value: Math.max(0.0001, peak * 0.35) },
    { time: end + release, value: 0.0001 },
  ];
}
