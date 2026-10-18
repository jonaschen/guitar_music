import { melodyPhrases, playMelodyPhrase, type MelodyTone } from "./connectedMelody";

export type MelodyAudition = { position: () => number; finished: () => boolean; stop: () => void };

// Audio time owns the transport. Display frames never start the next loop.
export function startMelodyAudition(context: BaseAudioContext, notes: readonly MelodyTone[], options: {
  duration: number; from?: number; loop?: boolean; connection: "connected" | "separate";
  onComplete?: () => void; onError?: (error: unknown) => void;
}): MelodyAudition {
  const { duration, loop = false, connection } = options;
  if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(options.from ?? 0)) throw new Error("Invalid audition range");
  if (loop && duration < .01) throw new Error("Loop range must be at least 10ms");
  const from = Math.max(0, Math.min(options.from ?? 0, duration));
  const phrases = melodyPhrases(notes);
  const origin = context.currentTime + .03;
  if (origin + duration <= origin) throw new Error("Audition range is too small for the audio clock");
  const nodes = new Set<OscillatorNode>();
  let stopped = false, timer: ReturnType<typeof setTimeout> | undefined;
  const stop = () => {
    stopped = true; clearTimeout(timer);
    nodes.forEach(node => { try { node.stop(); } catch { /* Already ended. */ } });
    nodes.clear();
  };
  const track = (node: OscillatorNode | null) => {
    if (!node) return;
    nodes.add(node);
    node.addEventListener("ended", () => nodes.delete(node), { once: true });
  };
  function schedulePass(scoreStart: number, contextStart: number) {
    if (connection === "connected") {
      for (const phrase of phrases) track(playMelodyPhrase(context, phrase, {
        scoreStart, scoreEnd: duration, contextStart, rate: 1, peak: .16, type: "sine",
      }));
    } else for (const note of notes) {
      const start = Math.max(context.currentTime + .005, contextStart + (Math.max(scoreStart, note.start) - scoreStart));
      const end = contextStart + (Math.min(duration, note.end) - scoreStart);
      if (!Number.isFinite(start + end + note.midi) || end <= start) continue;
      const source = context.createOscillator(), gain = context.createGain();
      const edge = Math.min(.005, (end - start) / 4);
      const concurrent = notes.filter(other => other.start < note.end && other.end > note.start).length;
      const peak = .16 / Math.sqrt(Math.max(1, concurrent));
      source.frequency.setValueAtTime(440 * 2 ** ((note.midi - 69) / 12), start);
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(peak, start + edge);
      gain.gain.setValueAtTime(peak, end - edge);
      gain.gain.linearRampToValueAtTime(0, end);
      source.connect(gain).connect(context.destination);
      track(source); source.start(start); source.stop(end);
    }
  }
  let nextOrigin = origin + duration - from;
  function tick(initial = false) {
    if (stopped) return;
    try {
      const now = context.currentTime;
      if (!loop) {
        if (now >= origin + duration - from) { stop(); options.onComplete?.(); return; }
      } else {
        // Skip missed complete passes without moving the audio clock. Clip
        // the current pass; never replay a backlog after a suspended tab.
        if (nextOrigin + duration <= now) {
          nextOrigin += Math.floor((now - nextOrigin) / duration) * duration;
        }
        const horizon = now + .12;
        while (nextOrigin < horizon) {
          schedulePass(0, nextOrigin);
          nextOrigin += duration;
        }
      }
      timer = setTimeout(tick, 25);
    } catch (error) { stop(); if (initial) throw error; options.onError?.(error); }
  }
  try { schedulePass(from, origin); if (loop) tick(true); else timer = setTimeout(tick, 25); }
  catch (error) { stop(); throw error; }
  return {
    position: () => {
      const elapsed = from + Math.max(0, context.currentTime - origin);
      return loop ? elapsed % duration : Math.min(duration, elapsed);
    },
    finished: () => stopped || (!loop && context.currentTime >= origin + duration - from),
    stop,
  };
}
