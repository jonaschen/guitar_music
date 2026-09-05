import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import type { AccidentalPreference, AnalysisJob, SongScore } from "./types";

const API_BASE = "http://localhost:8000";
const KEY_OPTIONS = [
  { pitch: 0, label: "C" },
  { pitch: 1, label: "C#/Db" },
  { pitch: 2, label: "D" },
  { pitch: 3, label: "D#/Eb" },
  { pitch: 4, label: "E" },
  { pitch: 5, label: "F" },
  { pitch: 6, label: "F#/Gb" },
  { pitch: 7, label: "G" },
  { pitch: 8, label: "G#/Ab" },
  { pitch: 9, label: "A" },
  { pitch: 10, label: "A#/Bb" },
  { pitch: 11, label: "B" },
] as const;
const NOTE_TO_PITCH: Record<string, number> = {
  C: 0,
  "B#": 0,
  "C#": 1,
  Db: 1,
  D: 2,
  "D#": 3,
  Eb: 3,
  E: 4,
  Fb: 4,
  "E#": 5,
  F: 5,
  "F#": 6,
  Gb: 6,
  G: 7,
  "G#": 8,
  Ab: 8,
  A: 9,
  "A#": 10,
  Bb: 10,
  B: 11,
  Cb: 11,
};
const PITCH_TO_FLAT_KEY = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];

type AnalyzeState = "idle" | "queued" | "ready" | "error";
type ScoreChord = SongScore["chords"][number];

const EMPTY_SCORE: SongScore | null = null;

function getPitchClass(key: string): number {
  return NOTE_TO_PITCH[key] ?? 0;
}

function semitoneDelta(from: string, to: string): number {
  const raw = getPitchClass(to) - getPitchClass(from);
  if (raw > 6) return raw - 12;
  if (raw < -6) return raw + 12;
  return raw;
}

async function createAnalysisJob(file: File, melodyMode: string, chordComplexity: string): Promise<AnalysisJob> {
  const formData = new FormData();
  formData.append("audio_file", file);
  formData.append("rights_confirmed", "true");
  formData.append("melody_mode", melodyMode);
  formData.append("chord_complexity", chordComplexity);

  const response = await fetch(`${API_BASE}/api/v1/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function cancelAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/cancel`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function postTranspose(
  score: SongScore,
  semitones: number,
  accidentalPreference: AccidentalPreference,
  capo: number,
): Promise<SongScore> {
  const response = await fetch(`${API_BASE}/scores/transpose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      score,
      semitones,
      accidental_preference: accidentalPreference,
      capo,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

async function postSaveRevision(score: SongScore, revisionId: string | null): Promise<{ revision_id: string }> {
  const response = await fetch(`${API_BASE}/revisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      score,
      revision_id: revisionId,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

async function getRevision(revisionId: string): Promise<SongScore> {
  const response = await fetch(`${API_BASE}/revisions/${revisionId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export function App() {
  const [status, setStatus] = useState<AnalyzeState>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [melodyMode, setMelodyMode] = useState("vocal");
  const [chordComplexity, setChordComplexity] = useState("standard");
  const [score, setScore] = useState<SongScore | null>(EMPTY_SCORE);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [loopRange, setLoopRange] = useState<[number, number] | null>(null);
  const [loopStart, setLoopStart] = useState<number | null>(null);
  const [loopEnd, setLoopEnd] = useState<number | null>(null);
  const [error, setError] = useState<string>("");
  const [accidentalPreference, setAccidentalPreference] = useState<AccidentalPreference>("auto");
  const [capo, setCapo] = useState(0);
  const [isRetuningScore, setIsRetuningScore] = useState(false);
  const [selectedChordId, setSelectedChordId] = useState<string | null>(null);
  const [chordDraft, setChordDraft] = useState("");
  const [revisionId, setRevisionId] = useState("");
  const [saveStatus, setSaveStatus] = useState("No saved revision yet.");
  const [isSavingRevision, setIsSavingRevision] = useState(false);
  const [isLoadingRevision, setIsLoadingRevision] = useState(false);

  useEffect(() => {
    if (!file) {
      setAudioUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setAudioUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  useEffect(() => {
    if (!analysisJob || ["completed", "failed", "cancelled"].includes(analysisJob.status)) return;

    let disposed = false;
    const poll = async () => {
      try {
        const nextJob = await getAnalysisJob(analysisJob.id);
        if (disposed) return;
        setAnalysisJob(nextJob);
        if (nextJob.status === "completed" && nextJob.score) {
          setScore(nextJob.score);
          setRevisionId("");
          setSaveStatus("Analysis loaded. Save to create a revision.");
          setStatus("ready");
        } else if (nextJob.status === "failed" || nextJob.status === "cancelled") {
          setStatus("error");
          setError(nextJob.error ?? nextJob.message);
        }
      } catch (pollError) {
        if (!disposed) {
          setStatus("error");
          setError(pollError instanceof Error ? pollError.message : "Could not read analysis progress.");
        }
      }
    };
    void poll();
    const intervalId = window.setInterval(() => void poll(), 1000);
    return () => {
      disposed = true;
      window.clearInterval(intervalId);
    };
  }, [analysisJob?.id, analysisJob?.status]);

  useEffect(() => {
    if (score) {
      setCapo(score.analysis.capo);
      setAccidentalPreference(score.key_context.accidental_preference);
    }
  }, [score]);

  useEffect(() => {
    if (!score || score.chords.length === 0) {
      setSelectedChordId(null);
      setChordDraft("");
      return;
    }

    const selectedChord = score.chords.find((chord) => chord.id === selectedChordId) ?? score.chords[0];
    setSelectedChordId(selectedChord.id);
    setChordDraft(selectedChord.symbol);
  }, [score, selectedChordId]);

  const groupedChords = new Map<number, ScoreChord[]>();
  score?.chords.forEach((chord) => {
    const measure = score.beats.filter((beat) => beat.time <= chord.start).at(-1)?.measure ?? 1;
    const chords = groupedChords.get(measure) ?? [];
    chords.push(chord);
    groupedChords.set(measure, chords);
  });

  const selectedChord = score?.chords.find((chord) => chord.id === selectedChordId) ?? null;
  const activeChordId = score?.chords.find((chord) => playbackTime >= chord.start && playbackTime < chord.end)?.id ?? null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose an audio file first.");
      return;
    }

    setStatus("queued");
    setError("");
    try {
      const createdJob = await createAnalysisJob(file, melodyMode, chordComplexity);
      setAnalysisJob(createdJob);
    } catch (submitError) {
      setStatus("error");
      setError(submitError instanceof Error ? submitError.message : "Analysis failed.");
    }
  }

  async function cancelCurrentJob() {
    if (!analysisJob) return;
    try {
      setAnalysisJob(await cancelAnalysisJob(analysisJob.id));
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Could not cancel analysis.");
    }
  }

  async function retuneScore(nextKey: string, nextCapo = capo, nextPreference = accidentalPreference) {
    if (!score) return;
    setIsRetuningScore(true);
    setError("");
    try {
      const nextSemitones = semitoneDelta(score.key_context.source.key, nextKey);
      const updated = await postTranspose(score, nextSemitones, nextPreference, nextCapo);
      setScore(updated);
    } catch (transposeError) {
      setError(transposeError instanceof Error ? transposeError.message : "Transposition failed.");
    } finally {
      setIsRetuningScore(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  function downloadScoreJson() {
    if (!score) return;
    const blob = new Blob([JSON.stringify(score, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "guitarscribe-score.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function downloadChordPro() {
    if (!score) return;
    const response = await fetch(`/scores/chordpro`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(score),
    });
    if (!response.ok) throw new Error(await response.text());
    const url = URL.createObjectURL(new Blob([await response.text()], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "guitarscribe-score.chopro";
    link.click();
    URL.revokeObjectURL(url);
  }

  function updateChords(transform: (chords: ScoreChord[]) => ScoreChord[]) {
    setScore((currentScore) => {
      if (!currentScore) return currentScore;
      return {
        ...currentScore,
        chords: transform(currentScore.chords),
      };
    });
  }

  function currentMeasureRange(time: number): [number, number] | null {
    if (!score || score.beats.length === 0) return null;
    const currentBeat = score.beats.filter((beat) => beat.time <= time).at(-1);
    if (!currentBeat) return null;
    const start = score.beats.find((beat) => beat.measure === currentBeat.measure)?.time ?? currentBeat.time;
    const next = score.beats.find((beat) => beat.measure === currentBeat.measure + 1)?.time ?? score.song.duration_seconds;
    return [start, next];
  }

  function handlePlaybackTime(time: number) {
    setPlaybackTime(time);
    const activeLoop = loopStart !== null && loopEnd !== null && loopEnd > loopStart ? [loopStart, loopEnd] : loopRange;
    if (activeLoop && time >= activeLoop[1] - 0.03) seekTo(activeLoop[0]);
  }

  function seekTo(time: number) {
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setPlaybackTime(time);
    }
  }

  function seekMeasure(direction: -1 | 1) {
    if (!score) return;
    const measureStarts = Array.from(new Map(score.beats.map((beat) => [beat.measure, beat.time])).entries());
    const currentIndex = Math.max(0, measureStarts.findIndex(([, time], index) => playbackTime < (measureStarts[index + 1]?.[1] ?? Infinity)));
    const target = measureStarts[Math.max(0, Math.min(measureStarts.length - 1, currentIndex + direction))];
    if (target) seekTo(target[1]);
  }

  function setSpeed(nextRate: number) {
    setPlaybackRate(nextRate);
    if (audioRef.current) audioRef.current.playbackRate = nextRate;
  }

  function selectChord(chord: ScoreChord) {
    setSelectedChordId(chord.id);
    seekTo(chord.start);
    setChordDraft(chord.symbol);
  }

  function renameSelectedChord() {
    if (!selectedChordId) return;
    const nextSymbol = chordDraft.trim();
    if (!nextSymbol) return;

    updateChords((chords) =>
      chords.map((chord) =>
        chord.id === selectedChordId
          ? {
              ...chord,
              symbol: nextSymbol,
              shape_symbol: chord.shape_symbol ?? nextSymbol,
              origin: "user",
              edited: true,
            }
          : chord,
      ),
    );
  }

  function splitSelectedChord() {
    if (!selectedChord) return;
    const duration = selectedChord.end - selectedChord.start;
    if (duration < 0.2) return;

    const midpoint = Number((selectedChord.start + duration / 2).toFixed(3));
    updateChords((chords) =>
      chords.flatMap((chord) => {
        if (chord.id !== selectedChord.id) return [chord];
        const firstHalf: ScoreChord = {
          ...chord,
          end: midpoint,
          origin: "user",
          edited: true,
        };
        const secondHalf: ScoreChord = {
          ...chord,
          id: `${chord.id}-split`,
          start: midpoint,
          origin: "user",
          edited: true,
        };
        return [firstHalf, secondHalf];
      }),
    );
  }

  function deleteSelectedChord() {
    if (!selectedChordId) return;
    updateChords((chords) => chords.filter((chord) => chord.id !== selectedChordId));
    setSelectedChordId(null);
    setChordDraft("");
  }

  async function saveRevision() {
    if (!score) return;
    setIsSavingRevision(true);
    setError("");
    try {
      const response = await postSaveRevision(score, revisionId || null);
      setRevisionId(response.revision_id);
      setSaveStatus(`Saved revision ${response.revision_id}.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Revision save failed.");
    } finally {
      setIsSavingRevision(false);
    }
  }

  async function loadRevision() {
    if (!revisionId.trim()) return;
    setIsLoadingRevision(true);
    setError("");
    try {
      const loadedScore = await getRevision(revisionId.trim());
      setScore(loadedScore);
      setStatus("ready");
      setSaveStatus(`Loaded revision ${revisionId.trim()}.`);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Revision load failed.");
    } finally {
      setIsLoadingRevision(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="aurora aurora-left" />
      <div className="aurora aurora-right" />
      <main className="layout">
        <section className="hero-card">
          <div className="hero-copy">
            <p className="eyebrow">GuitarScribe / September 4, 2026 handoff build</p>
            <h1>Paste less. Listen once. Get a playable draft.</h1>
            <p className="lede">
              Upload a legal audio file, extract chords, meter, and simplified melody, then shift the
              whole chart into a singer-friendly key without re-running analysis.
            </p>
          </div>

          <form className="intake-card" onSubmit={handleSubmit}>
            <label className="field">
              <span>Audio upload</span>
              <input type="file" accept=".wav,.mp3,.flac,.ogg,.m4a,audio/*" onChange={handleFileChange} />
            </label>

            <div className="field-row">
              <label className="field">
                <span>Melody focus</span>
                <select value={melodyMode} onChange={(event) => setMelodyMode(event.target.value)}>
                  <option value="vocal">Vocal</option>
                  <option value="guitar">Guitar</option>
                  <option value="mix">Most prominent</option>
                </select>
              </label>

              <label className="field">
                <span>Chord detail</span>
                <select value={chordComplexity} onChange={(event) => setChordComplexity(event.target.value)}>
                  <option value="simple">Simple</option>
                  <option value="standard">Standard</option>
                  <option value="full">Full</option>
                </select>
              </label>
            </div>

            <div className="rights-box">
              <strong>Rights check</strong>
              <p>You should upload only audio you own, control, or have permission to analyze.</p>
            </div>

            <button className="primary-button" type="submit" disabled={status === "queued"}>
              {status === "queued" ? "Analysis queued..." : "Start analysis"}
            </button>
          </form>
        </section>

        {error ? <p className="error-banner">{error}</p> : null}
        {analysisJob && !["completed", "failed", "cancelled"].includes(analysisJob.status) ? (
          <section className="job-progress" aria-live="polite">
            <div>
              <strong>{analysisJob.message}</strong>
              <span>{analysisJob.progress}%</span>
            </div>
            <progress value={analysisJob.progress} max="100">{analysisJob.progress}%</progress>
            <button className="ghost-button" type="button" onClick={() => void cancelCurrentJob()}>Cancel analysis</button>
          </section>
        ) : null}

        <section className="workspace">
          <div className="panel result-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Result workspace</p>
                <h2>{score ? score.song.title : "No song loaded yet"}</h2>
              </div>
              <div className="status-pill">{status === "ready" ? "Editable draft" : analysisJob ? `${analysisJob.progress}%` : "Waiting for analysis"}</div>
            </div>

            {score ? (
              <>
                <div className="toolbar">
                  <div className="toolbar-block">
                    <span className="toolbar-label">Source</span>
                    <strong>
                      {score.key_context.source.key} {score.key_context.source.mode}
                    </strong>
                  </div>
                  <div className="toolbar-block">
                    <span className="toolbar-label">Arrangement</span>
                    <strong>
                      {score.key_context.target.key} {score.key_context.target.mode}
                    </strong>
                  </div>
                  <div className="toolbar-block toolbar-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() =>
                        retuneScore(PITCH_TO_FLAT_KEY[(getPitchClass(score.key_context.target.key) + 11) % 12])
                      }
                      disabled={isRetuningScore}
                    >
                      -
                    </button>
                    <span className="delta-chip">{score.key_context.transpose_semitones >= 0 ? "+" : ""}{score.key_context.transpose_semitones}</span>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() =>
                        retuneScore(PITCH_TO_FLAT_KEY[(getPitchClass(score.key_context.target.key) + 1) % 12])
                      }
                      disabled={isRetuningScore}
                    >
                      +
                    </button>
                  </div>
                  <div className="toolbar-block">
                    <span className="toolbar-label">Capo</span>
                    <select
                      value={capo}
                      onChange={(event) => {
                        const nextCapo = Number(event.target.value);
                        setCapo(nextCapo);
                        void retuneScore(score.key_context.target.key, nextCapo);
                      }}
                    >
                      {Array.from({ length: 9 }, (_, value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="toolbar-block">
                    <span className="toolbar-label">Shape key</span>
                    <strong>
                      {score.key_context.shape.key} {score.key_context.shape.mode}
                    </strong>
                  </div>
                </div>

                <div className="toolbar secondary-toolbar">
                  <label className="field compact-field">
                    <span>Target key</span>
                    <select
                      value={String(getPitchClass(score.key_context.target.key))}
                      onChange={(event) => void retuneScore(PITCH_TO_FLAT_KEY[Number(event.target.value)])}
                    >
                      {KEY_OPTIONS.map((key) => (
                        <option key={key.pitch} value={key.pitch}>
                          {key.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field compact-field">
                    <span>Spelling</span>
                    <select
                      value={accidentalPreference}
                      onChange={(event) => {
                        const nextPreference = event.target.value as AccidentalPreference;
                        setAccidentalPreference(nextPreference);
                        void retuneScore(score.key_context.target.key, capo, nextPreference);
                      }}
                    >
                      <option value="auto">Auto</option>
                      <option value="sharps">Prefer sharps</option>
                      <option value="flats">Prefer flats</option>
                    </select>
                  </label>

                  <button
                    type="button"
                    className="ghost-button wide-button"
                    onClick={() => void retuneScore(score.key_context.source.key, 0, "auto")}
                  >
                    Back to source key
                  </button>
                </div>

                {!score.key_context.audio_matches_notation ? (
                  <p className="warning-banner">
                    Notation is transposed to {score.key_context.target.key} {score.key_context.target.mode}, but the
                    original uploaded audio still sounds in {score.key_context.source.key} {score.key_context.source.mode}.
                  </p>
                ) : null}

                {audioUrl ? (
                  <section className="transport-bar">
                    <audio
                      ref={audioRef}
                      src={audioUrl}
                      onTimeUpdate={(event) => handlePlaybackTime(event.currentTarget.currentTime)}
                      onPlay={() => setIsPlaying(true)}
                      onPause={() => setIsPlaying(false)}
                      onEnded={() => setIsPlaying(false)}
                    />
                    <button type="button" className="ghost-button" onClick={() => seekMeasure(-1)}>Previous bar</button>
                    <button type="button" className="ghost-button" onClick={() => void (isPlaying ? audioRef.current?.pause() : audioRef.current?.play())}>
                      {isPlaying ? "Pause" : "Play"}
                    </button>
                    <button type="button" className="ghost-button" onClick={() => seekMeasure(1)}>Next bar</button>
                    <button type="button" className="ghost-button" onClick={() => setLoopRange((range) => range ? null : currentMeasureRange(playbackTime))}>{loopRange ? "Looping bar" : "Loop bar"}</button>
                    <button type="button" className="ghost-button" onClick={() => { setLoopStart(playbackTime); setLoopEnd(null); }}>Set A</button>
                    <button type="button" className="ghost-button" disabled={loopStart === null} onClick={() => { if (loopStart !== null && playbackTime > loopStart) setLoopEnd(playbackTime); }}>Set B</button>
                    {loopStart !== null ? <button type="button" className="ghost-button" onClick={() => { setLoopStart(null); setLoopEnd(null); }}>Clear A–B</button> : null}
                    <button type="button" className="ghost-button" onClick={() => seekTo(0)}>Stop</button>
                    <label className="transport-speed">Speed <select value={playbackRate} onChange={(event) => setSpeed(Number(event.target.value))}>{[0.5, 0.6, 0.75, 0.9, 1, 1.1, 1.25, 1.5].map((rate) => <option key={rate} value={rate}>{Math.round(rate * 100)}%</option>)}</select></label>
                    <span>{playbackTime.toFixed(1)}s / {score.song.duration_seconds.toFixed(1)}s</span>
                  </section>
                ) : null}

                <div className="export-actions">
                  <button type="button" className="ghost-button" onClick={downloadScoreJson}>Download JSON</button>
                  <button type="button" className="ghost-button" onClick={() => void downloadChordPro()}>Download ChordPro</button>
                </div>

                <div className="summary-grid">
                  <article className="metric-card">
                    <span>BPM</span>
                    <strong>{Math.round(score.analysis.bpm)}</strong>
                  </article>
                  <article className="metric-card">
                    <span>Meter</span>
                    <strong>{score.analysis.time_signature}</strong>
                  </article>
                  <article className="metric-card">
                    <span>Chords</span>
                    <strong>{score.chords.length}</strong>
                  </article>
                  <article className="metric-card">
                    <span>Melody notes</span>
                    <strong>{score.melody.length}</strong>
                  </article>
                </div>

                <div className="chord-sheet">
                  {Array.from(groupedChords.entries()).map(([measure, group]) => (
                    <div key={`measure-`} className="measure-card">
                      <div className="measure-header">Bar {measure}</div>
                      <div className="measure-chords">
                        {group.map((chord) => (
                          <button
                            key={chord.id}
                            type="button"
                            className={`chord-block${selectedChordId === chord.id ? " chord-block-selected" : ""}${activeChordId === chord.id ? " chord-block-active" : ""}`}
                            onClick={() => selectChord(chord)}
                          >
                            <span className="chord-symbol">{chord.symbol}</span>
                            <span className="chord-meta">
                              {chord.start.toFixed(1)}s - {chord.end.toFixed(1)}s
                            </span>
                            <span className="shape-meta">Shape: {chord.shape_symbol ?? chord.symbol}</span>
                            {chord.edited ? <span className="edit-badge">Edited</span> : null}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="placeholder">
                <p>Upload audio to populate the editable chord grid and key toolbar.</p>
              </div>
            )}
          </div>

          <aside className="panel side-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Session notes</p>
                <h2>{selectedChord ? `Edit ${selectedChord.symbol}` : "Why this shell exists"}</h2>
              </div>
            </div>
            {selectedChord ? (
              <div className="editor-panel">
                <div className="revision-panel">
                  <h3>Revision</h3>
                  <label className="field compact-field">
                    <span>Revision ID</span>
                    <input value={revisionId} onChange={(event) => setRevisionId(event.target.value)} />
                  </label>
                  <div className="editor-actions">
                    <button type="button" className="ghost-button" onClick={saveRevision} disabled={isSavingRevision}>
                      {isSavingRevision ? "Saving..." : "Save revision"}
                    </button>
                    <button type="button" className="ghost-button" onClick={loadRevision} disabled={isLoadingRevision}>
                      {isLoadingRevision ? "Loading..." : "Load revision"}
                    </button>
                  </div>
                  <p className="revision-status">{saveStatus}</p>
                </div>
                <label className="field compact-field">
                  <span>Chord symbol</span>
                  <input value={chordDraft} onChange={(event) => setChordDraft(event.target.value)} />
                </label>
                <div className="editor-actions">
                  <button type="button" className="ghost-button" onClick={renameSelectedChord}>
                    Save rename
                  </button>
                  <button type="button" className="ghost-button" onClick={splitSelectedChord}>
                    Split chord
                  </button>
                  <button type="button" className="ghost-button destructive-button" onClick={deleteSelectedChord}>
                    Delete
                  </button>
                </div>
                <div className="editor-meta">
                  <p>
                    Time: {selectedChord.start.toFixed(2)}s - {selectedChord.end.toFixed(2)}s
                  </p>
                  <p>Origin: {selectedChord.origin}</p>
                  <p>Source symbol: {selectedChord.source_symbol ?? selectedChord.symbol}</p>
                  <p>Shape symbol: {selectedChord.shape_symbol ?? selectedChord.symbol}</p>
                </div>
                <div className="voicing-panel">
                  <h3>Voicing options</h3>
                  {selectedChord.available_voicings && selectedChord.available_voicings.length > 0 ? (
                    selectedChord.available_voicings.map((voicing) => (
                      <div key={voicing.id} className="voicing-card">
                        <strong>{voicing.shape_symbol}</strong>
                        <span>Frets: {voicing.frets.map((fret) => (fret === null ? "x" : fret)).join(" ")}</span>
                      </div>
                    ))
                  ) : (
                    <p className="voicing-empty">No alternate voicings loaded yet for this chord.</p>
                  )}
                </div>
              </div>
            ) : (
              <ul className="notes-list">
                <li>Uses local audio upload, not YouTube download, to stay aligned with the handoff constraints.</li>
                <li>Shows `source`, `target`, and `shape` key states separately.</li>
                <li>Capo changes reuse the existing analysis instead of recomputing DSP output.</li>
                <li>Select any chord card to rename it, split it, or remove it from the current revision.</li>
              </ul>
            )}
          </aside>
        </section>
      </main>
    </div>
  );
}
