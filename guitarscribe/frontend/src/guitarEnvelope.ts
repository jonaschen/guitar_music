// Keep the note audible through its notated duration; release only at the end.
// All points stay inside the event so a no-chord boundary remains silent.
export function guitarEnvelope(start: number, end: number, peak: number) {
  const duration = end - start;
  return [
    { time: start, value: 0.0001 },
    { time: start + Math.min(0.003, duration * 0.1), value: peak },
    { time: start + Math.min(0.18, duration * 0.35), value: Math.max(0.0001, peak * 0.6) },
    { time: end - Math.min(0.035, duration * 0.2), value: Math.max(0.0001, peak * 0.35) },
    { time: end, value: 0.0001 },
  ];
}
