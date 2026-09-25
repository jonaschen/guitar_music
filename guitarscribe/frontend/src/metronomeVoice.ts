export function createMetronomeVoice(context: BaseAudioContext, start: number, downbeat: boolean, volume: number) {
  if (volume <= 0) return null;
  const source = context.createOscillator();
  const gain = context.createGain();
  source.type = "sine";
  source.frequency.value = downbeat ? 1440 : 880;
  gain.gain.setValueAtTime(0.00001, start);
  gain.gain.linearRampToValueAtTime(volume * (downbeat ? 0.3 : 0.2), start + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.00001, start + (downbeat ? 0.07 : 0.045));
  source.connect(gain).connect(context.destination);
  source.addEventListener("ended", () => { source.disconnect(); gain.disconnect(); });
  source.start(start); source.stop(start + 0.08);
  return source;
}
