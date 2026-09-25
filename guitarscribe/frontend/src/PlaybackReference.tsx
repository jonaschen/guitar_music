import { MutableRefObject, useEffect, useRef, useState } from "react";
import type { PlaybackManifest } from "./types";
import { guitarEnvelope } from "./guitarEnvelope";
import { preparePluckedBuffers, createPluckedVoice } from "./pluckedTone";
import { createMetronomeVoice } from "./metronomeVoice";

export function PlaybackReference({ onStart, stopRef }: {
  onStart: () => void; stopRef: MutableRefObject<() => void>;
}) {
  const contextRef = useRef<AudioContext | null>(null);
  const sources = useRef<AudioScheduledSourceNode[]>([]);
  const frame = useRef<number | null>(null);
  const generation = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState("");
  const [tone, setTone] = useState("pluck");
  const [changeMode, setChangeMode] = useState("bar");
  const withinBar = changeMode === "within";
  const [groove, setGroove] = useState("balanced");
  const [click, setClick] = useState(true);
  const [clickVolume, setClickVolume] = useState(0.3);
  const [busy, setBusy] = useState(false);

  function stop() {
    generation.current++;
    sources.current.forEach((source) => { try { source.stop(); } catch { /* already ended */ } });
    sources.current = [];
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    setPlaying(false);
    setBusy(false);
  }
  useEffect(() => {
    stopRef.current = stop;
    return () => { stop(); stopRef.current = () => {}; void contextRef.current?.close(); };
  }, []);

  async function play() {
    stop(); onStart(); setError(""); setBusy(true); setPosition(0);
    const token = generation.current;
    try {
      const context = contextRef.current ?? new AudioContext();
      contextRef.current = context;
      await context.resume();
      const query = [withinBar ? "within_bar=true" : "", changeMode === "three" ? "chords_per_bar=3" : "", groove === "syncopated" ? "groove=syncopated" : ""].filter(Boolean).join("&");
      const response = await fetch("http://localhost:8000/scores/playback/reference" + (query ? "?" + query : ""));
      if (!response.ok) throw new Error("Could not load the listening control. Check the backend.");
      const manifest: PlaybackManifest = await response.json();
      if (token !== generation.current) return;
      const buffers = tone === "pluck" ? await preparePluckedBuffers(context,
        manifest.events.filter((event) => event.track === "guitar").flatMap((event) => event.pitches),
        () => token !== generation.current) : new Map<number, AudioBuffer>();
      if (token !== generation.current) return;
      const origin = context.currentTime + 0.08;
      for (const event of manifest.events) {
        if (event.track !== "guitar" && !(click && event.track === "metronome")) continue;
        if (event.track === "metronome") {
          const source = createMetronomeVoice(context, origin + event.start, event.velocity > 100, clickVolume);
          if (source) sources.current.push(source);
          continue;
        }
        event.pitches.forEach((pitch, index) => {
          const start = origin + event.start + (event.pitch_offsets[index] ?? 0);
          const end = Math.max(start + 0.02, origin + event.end);
          const velocity = event.pitch_velocities[index] ?? event.velocity;
          const peak = event.track === "guitar" ? 0.24 * velocity / 127 / Math.sqrt(event.pitches.length) : 0.018;
          if (tone === "pluck") {
            const source = createPluckedVoice(context, buffers.get(pitch)!, start, end, peak);
            if (source) sources.current.push(source);
            return;
          }
          const gain = context.createGain();
          let source: AudioScheduledSourceNode;
          let releaseEnd: number;
          {
            const oscillator = context.createOscillator();
            oscillator.frequency.value = 440 * 2 ** ((pitch - 69) / 12);
            oscillator.type = event.track === "guitar" ? "triangle" : "sine";
            source = oscillator;
            const points = guitarEnvelope(start, end, peak, event.track === "guitar" ? 0.12 : 0.02);
            gain.gain.setValueAtTime(points[0].value, points[0].time);
            gain.gain.linearRampToValueAtTime(points[1].value, points[1].time);
            points.slice(2).forEach((point) => gain.gain.exponentialRampToValueAtTime(point.value, point.time));
            releaseEnd = points[points.length - 1].time;
          }
          source.connect(gain).connect(context.destination);
          source.onended = () => { source.disconnect(); gain.disconnect(); sources.current = sources.current.filter((item) => item !== source); };
          source.start(start); source.stop(releaseEnd + 0.01); sources.current.push(source);
        });
      }
      setBusy(false); setPlaying(true);
      const update = () => {
        const elapsed = Math.max(0, context.currentTime - origin);
        setPosition(Math.min(9.999, elapsed));
        if (elapsed >= manifest.duration_seconds + 0.35) { stop(); return; }
        frame.current = requestAnimationFrame(update);
      };
      frame.current = requestAnimationFrame(update);
    } catch (failure) {
      if (token === generation.current) { stop(); setError(failure instanceof Error ? failure.message : "Playback failed"); }
    }
  }

  const bar = Math.floor(position / 2.5);
  const beat = Math.floor(position / 0.625) % 4;
  const beatChords = changeMode === "three"
    ? [["C", "C", "Am", "G"], ["F", "F", "Dm", "G"], ["Am", "Am", "F", "G"], ["G", "G", "F", "C"]][bar]
    : withinBar ? [["C", "C", "Am", "Am"], ["F", "F", "G", "G"], ["Am", "Am", "F", "F"], ["G", "G", "C", "C"]][bar]
    : Array(4).fill(["C", "Am", "F", "G"][bar]);
  return <section className="panel playback-reference" aria-label="Four-bar listening control">
    <h2>四小節伴奏試聽 / Playback control</h2>
    <p>96 BPM · 4/4 · Bar 就是小節。{changeMode === "three" ? "三和弦分配：兩拍＋一拍＋一拍。" : withinBar ? "C/Am → F/G → Am/F → G/C" : "C → Am → F → G"} 固定測試段，不改動目前樂譜。新音色是實驗性合成。</p>
    <div className="synth-controls">
      <label>刷奏型 <select aria-label="Reference groove" value={groove} onChange={(event) => { stop(); setGroove(event.target.value); }}><option value="balanced">4/4：強、弱、次強、弱</option><option value="syncopated">對照：原本第 3 拍空刷</option></select></label>
      <label>換和弦 <select aria-label="Reference chord changes" value={changeMode} onChange={(event) => { stop(); setPosition(0); setChangeMode(event.target.value); }}><option value="bar">每小節一個和弦（4 拍）</option><option value="within">每小節兩個和弦（2＋2 拍）</option><option value="three">每小節三個和弦（2＋1＋1 拍）</option></select></label>
      <label>音色 <select aria-label="Reference tone" value={tone} onChange={(event) => { stop(); setTone(event.target.value); }}><option value="pluck">新：逐泛音衰減</option><option value="simple">對照：簡單振盪器</option></select></label>
      <label><input type="checkbox" checked={click} onChange={(event) => { stop(); setClick(event.target.checked); }} />輕聲節拍器</label>
      <label>節拍器音量 <input aria-label="Reference metronome volume" type="range" min="0" max="1" step="0.05" value={clickVolume} onChange={(event) => { stop(); setClickVolume(Number(event.target.value)); }} /></label>
      <button type="button" onClick={() => void play()} disabled={busy || playing}>{busy ? "Preparing…" : "播放四小節"}</button>
      <button type="button" onClick={stop}>停止試聽</button>
    </div>
    <p role="status">{playing ? `Bar ${bar + 1}（小節）· ${beatChords[beat]} · Beat ${beat + 1}` : "Ready · 每次播放皆從第一小節開始"}</p>
    <div className="reference-beat-grid" aria-label="小節內四拍">
      {beatChords.map((chord, index) => <div key={index} className={playing && beat === index ? "reference-beat-active" : ""}><span>第 {index + 1} 拍 · {["強", "弱", "次強", "弱"][index]}</span><strong>{chord}</strong></div>)}
    </div>
    <p>1 ＆ 2 ＆ 3 ＆ 4 ＆ ／ {groove === "syncopated" ? "↓ — ↓ ↑ — ↑ ↓ ↑（切分對照，不採上方標準強弱）" : changeMode === "three" ? "↓ — ↓ ↑ ↓ — ↓ —" : "↓ — ↓ ↑ ↓ ↑ ↓ ↑"}。強弱跟隨拍位，不隨和弦重設；空格延音。三和弦的 2＋1＋1 是此控制組編排，並非所有歌曲的固定規則。</p>
    {error ? <p role="alert">{error}</p> : null}
  </section>;
}
