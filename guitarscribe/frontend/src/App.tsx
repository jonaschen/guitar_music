import {editChordSlice, removeChordSlice, type ChordEditScope} from "./chordSlice";
import {beatCoordinate, shiftByBeats, retimeChord} from "./chordTiming";
import { ChordSongPage } from "./ChordSongPage";
import { AccompanimentReview, type ReviewMode } from "./AccompanimentReview";
import { ChangeEvent, FormEvent, lazy, Suspense, useEffect, useRef, useState } from "react";
import { ChordEntryAudit } from "./ChordEntryAudit";
import { ChordGridCandidate } from "./ChordGridCandidate";
import type { AccidentalPreference, AnalysisJob, PlaybackManifest, PlaybackTrack, SongScore } from "./types";
import { ChordDiagram } from "./ChordDiagram";
import { createMediaTransportClock } from "./transportClock";
import { DiagnosticTimeline } from "./DiagnosticTimeline";
import { guitarEnvelope } from "./guitarEnvelope";
import { melodyEnvelope } from "./melodyEnvelope";
import { PlaybackReference } from "./PlaybackReference";
import { preparePluckedBuffers, createPluckedVoice } from "./pluckedTone";
import { createMetronomeVoice } from "./metronomeVoice";
import { mergeChordSpans, type ChordSpan } from "./chordSpans";
import { measureLayout } from "./measureLayout";
import { MelodyEditor } from "./MelodyEditor";
import { melodyVersion, sourceJobId, scoreFromJob, readSavedVersion, type SavedVersion } from "./scoreVersion";
import { ContourCandidate } from "./ContourCandidate";
import { AccompanimentCandidate } from "./AccompanimentCandidate";
import { SongRangeEditor } from "./SongRangeEditor";
import { PlaybackRangeEditor } from "./PlaybackRangeEditor";
import { songBounds, clipRange } from "./songRange";
import { notationBars } from "./melodyNotation";
import { waitForMediaMetadata } from "./mediaReady";
import { melodyPhrases, playMelodyPhrase } from "./connectedMelody";
import { startMelodyAudition, type MelodyAudition } from "./melodyAudition";

const AlphaTabScore = lazy(() => import("./AlphaTabScore"));

const API_BASE = new URL("/backend", window.location.origin).href;
// Archived melody tools are available only in an explicitly opted-in development build.
const MELODY_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ARCHIVED_MELODY === "true";
function analysisErrorMessage(message: string) {
  if (/Inconsistent meter|missing beats|unobserved downbeat|Downbeat must|beats requires/.test(message))
    return "這段音訊的拍點或小節位置尚無法可靠確認，因此沒有產生和弦譜。音訊已保留，目前工作版本不受影響。可以改選片段，或先繼續編輯已保存的歌曲。";
  return message;
}
function shiftedChordName(symbol: string, semitones: number): string {
  if (semitones % 12 === 0) return symbol;
  const names = symbol.includes("b") ? ["C","Db","D","Eb","E","F","Gb","G","Ab","A","Bb","B"] : ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
  return symbol.replace(/^[A-G][#b]?|(?<=\/)[A-G][#b]?$/g, note => names[((NOTE_TO_PITCH[note] ?? 0) + semitones % 12 + 12) % 12]);
}
const ReviewComponent = MELODY_ENABLED ? AccompanimentReview : ChordSongPage;
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
const SYNTH_SCHEDULE_AHEAD_SECONDS = 0.35;
const SYNTH_SCHEDULER_INTERVAL_MS = 50;

type AnalyzeState = "idle" | "queued" | "ready" | "error";
type ScoreChord = SongScore["chords"][number];
type DiagnosticAudioTrack = "source" | "vocal-stem" | "accompaniment-stem" | "raw-melody" | "final-melody" | "melody-contour";

const EMPTY_SCORE: SongScore | null = null;

class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function getPitchClass(key: string): number {
  return NOTE_TO_PITCH[key] ?? 0;
}

function semitoneDelta(from: string, to: string): number {
  const raw = getPitchClass(to) - getPitchClass(from);
  if (raw > 6) return raw - 12;
  if (raw < -6) return raw + 12;
  return raw;
}

async function createAnalysisJob(file: File, melodyMode: string, separateVocals: boolean, chordComplexity: string, skipSeconds: number, analysisSeconds: number | null): Promise<AnalysisJob> {
  const formData = new FormData();
  formData.append("audio_file", file);
  formData.append("rights_confirmed", "true");
  formData.append("melody_mode", melodyMode);
  formData.append("separate_vocals", String(separateVocals));
  formData.append("chord_complexity", chordComplexity);
  if (analysisSeconds !== null) formData.append("analysis_seconds", String(analysisSeconds));
  formData.append("skip_seconds", String(skipSeconds));

  const response = await fetch(`${API_BASE}/api/v1/jobs`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json();
}

async function createYouTubeAnalysisJob(url: string, melodyMode: string, separateVocals: boolean, chordComplexity: string, skipSeconds: number, analysisSeconds: number | null): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/api/v1/youtube-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, rights_confirmed: true, melody_mode: melodyMode, separate_vocals: separateVocals, chord_complexity: chordComplexity, skip_seconds: skipSeconds, analysis_seconds: analysisSeconds }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function getAnalysisJob(jobId: string): Promise<AnalysisJob> {
  const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
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

async function importLyrics(score: SongScore, content: string, format: "text" | "lrc" = "text"): Promise<SongScore> {
  const response = await fetch(`${API_BASE}/scores/lyrics/import-${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ score, content, language: "und" }),
  });
  if (!response.ok) throw new Error(await response.text());
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

async function postSaveRevision(score: SongScore, revisionId: string | null, createNew = false): Promise<{ revision_id: string }> {
  const response = await fetch(`${API_BASE}/revisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      score,
      revision_id: revisionId,
      create_new: createNew,
    }),
  });

  if (!response.ok) {
    if (response.status === 404 && createNew && revisionId) {
      throw new Error("保存失敗：找不到原版本 ID。工作樂譜仍在，請勿重新整理。可先 Download JSON 備份；若要獨立保存新版本，清空版本 ID 欄再按 Save new revision（不連接舊版本）。");
    }
    throw new Error(await response.text());
  }

  return response.json();
}

type ChordPerformanceMode = "original" | "continuous" | "sparse";

async function compilePlayback(score: SongScore, mode: ChordPerformanceMode): Promise<{ manifest: PlaybackManifest; notice: string }> {
  if (score.analysis.timing_status === "unmetered") mode = "original";
  const response = await fetch(API_BASE + (mode === "original" ? "/scores/playback/manifest" : "/scores/chord-entry-performance"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mode === "original" ? score : { score, mode, output: "preview" }),
  });
  if (!response.ok) throw new Error(await response.text());
  const body = await response.json();
  return mode === "original" ? { manifest: body, notice: "" } : {
    manifest: body.candidate,
    notice: `本次處理 ${body.changes.length} 段和弦；${body.skipped.length} 段保留原演奏（例如人工修改、短和弦或刷弦空間不足）。`,
  };
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
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [melodyMode, setMelodyMode] = useState(MELODY_ENABLED ? "vocal" : "off");
  const [separateVocals, setSeparateVocals] = useState(true);
  const [showRawChordSegments, setShowRawChordSegments] = useState(false);
  const [chordComplexity, setChordComplexity] = useState("full");
  const [analysisSeconds, setAnalysisSeconds] = useState(MELODY_ENABLED ? "45" : "full");
  const [showNewSong, setShowNewSong] = useState(false);
  const [capabilities, setCapabilities] = useState<{
    youtube_enabled: boolean; vocal_separation_enabled: boolean; improved_accompaniment: boolean;
    melody_available: boolean; beat_engine: string; chord_engine: string;
  } | null>(null);
  const [capabilitiesFailed, setCapabilitiesFailed] = useState(false);
  const pendingAnalysisBase = useRef<SongScore | null | undefined>(undefined);
  const submitInFlight = useRef(false);
  const pendingAnalysisOrigin = useRef<{ score: SongScore; job: AnalysisJob | null; revision: string | null } | null>(null);
  useEffect(() => {
    let disposed = false;
    void fetch(`${API_BASE}/api/v1/capabilities`).then(response => {
      if (!response.ok) throw new Error("Capabilities unavailable");
      return response.json();
    }).then(value => { if (!disposed) setCapabilities(value); })
      .catch(() => { if (!disposed) setCapabilitiesFailed(true); });
    return () => { disposed = true; };
  }, []);
  const [skipSeconds, setSkipSeconds] = useState("0");
  const [score, setScore] = useState<SongScore | null>(EMPTY_SCORE);
  const scoreRef = useRef(score);
  scoreRef.current = score;
  const [workingJobId, setWorkingJobId] = useState<string | undefined>();
  const bounds = songBounds(score);
  const [rhythmOptions, setRhythmOptions] = useState<SongScore["rhythm"][]>([]);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const sourceSegmentRef = useRef(false);
  const sourceLoadAbortRef = useRef<AbortController | null>(null);
  const [isSourcePreparing, setIsSourcePreparing] = useState(false);
  const pendingAudioTrackSeekRef = useRef<number | null>(null);
  const metronomeContextRef = useRef<AudioContext | null>(null);
  const synthContextRef = useRef<AudioContext | null>(null);
  const reviewSourceCacheRef = useRef<{url: string; buffer: AudioBuffer} | null>(null);
  const [activeReview, setActiveReview] = useState<ReviewMode | null>(null);
  const melodyAuditionRef = useRef<MelodyAudition | null>(null);
  useEffect(() => () => { melodyAuditionRef.current?.stop(); }, []);
  const synthGenerationRef = useRef(0);
  const referenceStopRef = useRef<() => void>(() => {});
  const synthSourcesRef = useRef<AudioScheduledSourceNode[]>([]);
  const synthAnimationRef = useRef<number | null>(null);
  const synthSchedulerRef = useRef<number | null>(null);
  const mediaAnimationRef = useRef<number | null>(null);
  const synthCountInTimerRef = useRef<number | null>(null);
  const lastMetronomeBeatRef = useRef<number | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [diagnosticAudioTrack, setDiagnosticAudioTrack] = useState<DiagnosticAudioTrack>("source");
  const [playbackTime, setPlaybackTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSynthPlaying, setIsSynthPlaying] = useState(false);
  const [synthSnapshot, setSynthSnapshot] = useState<{ manifest: PlaybackManifest; chords: ScoreChord[] } | null>(null);
  const [isSynthPreparing, setIsSynthPreparing] = useState(false);
  const [guitarTone, setGuitarTone] = useState("pluck");
  const [chordPerformance, setChordPerformance] = useState<ChordPerformanceMode>("original");
  const performanceGenerationRef = useRef(0);
  const [performanceNotice, setPerformanceNotice] = useState("");
  const [midiPending, setMidiPending] = useState(false);
  const midiRequestRef = useRef(0);
  const [synthTracks, setSynthTracks] = useState<Record<PlaybackTrack, boolean>>({ guitar: true, melody: false, metronome: false });
  const [synthVolumes, setSynthVolumes] = useState<Record<PlaybackTrack, number>>({ guitar: 0.24, melody: 0.45, metronome: 0.18 });
  const [melodyConnection, setMelodyConnection] = useState<"connected" | "separate">("connected");
  const [synthSoloTrack, setSynthSoloTrack] = useState<PlaybackTrack | null>(null);
  const [metronomeEnabled, setMetronomeEnabled] = useState(false);
  const [countInMeasures, setCountInMeasures] = useState(0);
  const [isCountingIn, setIsCountingIn] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [loopRange, setLoopRange] = useState<[number, number] | null>(null);
  const [loopStart, setLoopStart] = useState<number | null>(null);
  const [loopEnd, setLoopEnd] = useState<number | null>(null);
  const [followPlayhead, setFollowPlayhead] = useState(true);
  const [beatTimingDraft, setBeatTimingDraft] = useState<{ index: number; time: number } | null>(null);
  const [beatNudgeMeasures, setBeatNudgeMeasures] = useState(1);
  const [error, setError] = useState<string>("");
  const [lyricsDraft, setLyricsDraft] = useState("");
  const [editingLyricLineId, setEditingLyricLineId] = useState<string | null>(null);
  const [editingLyricText, setEditingLyricText] = useState("");
  const [lyricTimingDrafts, setLyricTimingDrafts] = useState<Record<string, { start: number; end: number }>>({});
  const [snapLyricTiming, setSnapLyricTiming] = useState(false);
  const [isImportingLyrics, setIsImportingLyrics] = useState(false);
  const [accidentalPreference, setAccidentalPreference] = useState<AccidentalPreference>("auto");
  const [capo, setCapo] = useState(0);
  const [isRetuningScore, setIsRetuningScore] = useState(false);
  const [capoRecommendations, setCapoRecommendations] = useState<Array<{ capo: number; shape_key: string; difficulty: number; open_chords: number; barre_chords: number; covered_chords: number }>>([]);
  const [selectedChordId, setSelectedChordId] = useState<string | null>(null);
  const [chordEditScope, setChordEditScope] = useState<ChordEditScope | null>(null);
  const [compactEditOpen, setCompactEditOpen] = useState(false);
  const [chordDraft, setChordDraft] = useState("");
  const [chordStartDraft, setChordStartDraft] = useState("");
  const [chordEndDraft, setChordEndDraft] = useState("");
  const [candidateVoicings, setCandidateVoicings] = useState<ScoreChord["available_voicings"]>([]);
  const [versionHistory, setVersionHistory] = useState<Array<{id:string;created_at:string}>>([]);
  const [revisionId, setRevisionId] = useState("");
  const [accompanimentView, setAccompanimentView] = useState(() => {
    if (!MELODY_ENABLED) return true;
    const view = new URLSearchParams(window.location.search).get("view");
    if (view === "accompaniment" || view === "melody") return view === "accompaniment";
    try { return localStorage.getItem("guitarscribe.editorView") !== "melody"; } catch { return true; }
  });
  const [focusedWorkspace, setFocusedWorkspace] = useState(() => {
    if (!MELODY_ENABLED) return true;
    if (["accompaniment", "melody"].includes(new URLSearchParams(window.location.search).get("view") ?? "")) return true;
    try { return localStorage.getItem("guitarscribe.workspaceMode") !== "full"; } catch { return true; }
  });
  const focusMode = !!score && focusedWorkspace;
  const youtubeUrlValid = !youtubeUrl.trim() || (()=>{try {const u=new URL(youtubeUrl.trim());return u.protocol==="https:" && ((["youtube.com","www.youtube.com","m.youtube.com"].includes(u.hostname) && u.pathname==="/watch" && /^[\w-]{11}$/.test(u.searchParams.get("v")??"")) || u.hostname==="youtu.be" && /^\/[\w-]{11}$/.test(u.pathname));}catch{return false;}})();
  const analysisBusy = !!analysisJob && !["completed","failed","cancelled"].includes(analysisJob.status);
  const productScreen = analysisBusy ? "analyzing" : !score || showNewSong ? "home" : "song";
  function switchWorkspace() {
    audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
    setFocusedWorkspace(value => !value);
    try { localStorage.setItem("guitarscribe.workspaceMode", focusedWorkspace ? "full" : "focus"); } catch { /* UI remains usable without storage. */ }
  }
  function switchEditorView() {
    audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
    const view = accompanimentView ? "melody" : "accompaniment";
    setFocusedWorkspace(true); setAccompanimentView(!accompanimentView);
    try { localStorage.setItem("guitarscribe.editorView", view); localStorage.setItem("guitarscribe.workspaceMode", "focus"); } catch { /* Optional preference. */ }
    const url = new URL(window.location.href); url.searchParams.set("view", view);
    window.history.replaceState(null, "", url);
  }
  function openPerformanceControls() {
    audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
    setFocusedWorkspace(false);
    window.requestAnimationFrame(() => {
      const panel = document.querySelector<HTMLDetailsElement>(".synth-panel");
      if (!panel) return;
      panel.open = true; panel.scrollIntoView({ block: "start" });
      panel.querySelector<HTMLSelectElement>('select[aria-label="吉他演奏方案"]')?.focus({ preventScroll: true });
    });
  }
  const [saveStatus, setSaveStatus] = useState("No saved revision yet.");
  const [isSavingRevision, setIsSavingRevision] = useState(false);
  const [isLoadingRevision, setIsLoadingRevision] = useState(false);
  const [undoHistory, setUndoHistory] = useState<SongScore[]>([]);
  const [redoHistory, setRedoHistory] = useState<SongScore[]>([]);
  const [rememberedVersion, setRememberedVersion] = useState<SavedVersion | null>(readSavedVersion);
  const [savedSnapshot, setSavedSnapshot] = useState<{ id: string; score: SongScore } | null>(null);
  const [restorePreview, setRestorePreview] = useState<{ id: string; base: SongScore | null; generation: number; next: SongScore; job: AnalysisJob | null } | null>(null);
  const cleanScoreRef = useRef(score);
  const workGenerationRef = useRef(0);
  const revisionRequestRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const hasUnsavedChanges = !!score && score !== cleanScoreRef.current;
  // Every handler captures the score generation of its render, including across await.
  const renderedWorkGeneration = workGenerationRef.current;
  const isCurrentWork = () => scoreRef.current === score && workGenerationRef.current === renderedWorkGeneration;

  useEffect(() => {
    if (!score) return;
    const source = sourceJobId(score);
    setWorkingJobId(source);
    if (analysisJob && source !== analysisJob.id && pendingAnalysisBase.current === undefined) {
      audioRef.current?.pause();
      setAudioUrl(null); setAnalysisJob(null);
    }
  }, [score]);

  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasUnsavedChanges]);

  function replaceScore(nextScore: SongScore) {
    workGenerationRef.current++;
    scoreRef.current = nextScore;
    cleanScoreRef.current = nextScore;
    setSavedSnapshot(null);
    setRestorePreview(null);
    setScore(nextScore);
    setBeatTimingDraft(null);
    setUndoHistory([]);
    setRedoHistory([]);
  }

  function restoreWorkingJob(id: string) {
    setWorkingJobId(id);
    const saved = window.localStorage.getItem(`guitarscribe.melodyRevision.${id}`) ?? "";
    setRevisionId(saved);
    setRememberedVersion(saved ? { id: saved, label: readSavedVersion()?.id === saved ? readSavedVersion()!.label : "已保存修訂", jobId: id } : null);
    setSaveStatus(saved ? `Saved draft ${saved} found. Use Load melody revision to open it; the original analysis is currently shown.` : "No saved revision yet.");
  }

  function recordScoreChange(nextScore: SongScore) {
    if (!isCurrentWork()) {
      setError("工作譜已改變，較舊的操作結果未套用；目前版本與 Undo 紀錄保持不變。");
      return false;
    }
    workGenerationRef.current++;
    if (score) setUndoHistory((history) => [...history, score].slice(-50));
    setRedoHistory([]);
    scoreRef.current = nextScore;
    setScore(nextScore);
    return true;
  }

  function undoScoreChange() {
    if (!score || undoHistory.length === 0) return;
    workGenerationRef.current++;
    const previous = undoHistory[undoHistory.length - 1];
    scoreRef.current = previous;
    setUndoHistory((history) => history.slice(0, -1));
    setRedoHistory((history) => [score, ...history].slice(0, 50));
    setScore(previous);
  }

  function redoScoreChange() {
    if (!score || redoHistory.length === 0) return;
    workGenerationRef.current++;
    const next = redoHistory[0];
    scoreRef.current = next;
    setRedoHistory((history) => history.slice(1));
    setUndoHistory((history) => [...history, score].slice(-50));
    setScore(next);
  }

  useEffect(() => {
    const linkedRevision = new URLSearchParams(window.location.search).get("revision");
    if (!linkedRevision) return;
    let disposed = false;
    const request = ++revisionRequestRef.current;
    const generation = workGenerationRef.current;
    const obsolete = () => disposed || request !== revisionRequestRef.current || generation !== workGenerationRef.current;
    setIsLoadingRevision(true); setRevisionId(linkedRevision);
    void (async () => {
      try {
        const next = await getRevision(linkedRevision);
        const source = sourceJobId(next);
        let job: AnalysisJob | null = null;
        if (source) { try { job = await getAnalysisJob(source); } catch { /* Notes work without source audio. */ } }
        if (obsolete()) return;
        replaceScore(next);
        finishRevisionRestore(linkedRevision, next, job);
      } catch (error) {
        if (!obsolete()) {
          setStatus("idle");
          setError(`無法載入指定保存版本 ${linkedRevision}；未改播原分析。${error instanceof Error ? error.message : ""}`);
        }
      } finally { if (!disposed && request === revisionRequestRef.current) setIsLoadingRevision(false); }
    })();
    return () => { disposed = true; };
  }, []);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("revision")) return;
    const linkedJobId = new URLSearchParams(window.location.search).get("job");
    const savedJobId = linkedJobId ?? window.localStorage.getItem("guitarscribe.activeJobId");
    if (!savedJobId) return;
    setStatus("queued");
    let disposed = false;
    const generation = workGenerationRef.current;
    const obsolete = () => disposed || generation !== workGenerationRef.current;
    let retryTimer: number | undefined;
    const restore = async () => {
      if (obsolete()) return;
      try {
        const job = await getAnalysisJob(savedJobId);
        if (obsolete()) return;
        window.localStorage.setItem("guitarscribe.activeJobId", savedJobId);
        setAnalysisJob(job);
        setError("");
        if (job.status === "completed" && job.score) {
          replaceScore(scoreFromJob(job));
          restoreWorkingJob(job.id);
          setAudioUrl(`${API_BASE}/api/v1/jobs/${job.id}/audio`);
          setStatus("ready");
        } else if (job.status === "completed") {
          setStatus("error");
          setError("This analysis completed without a recoverable score. Please run it again.");
        } else if (job.status === "failed" || job.status === "cancelled") {
          setStatus("error");
          setError(analysisErrorMessage(job.error ?? job.message));
        }
      } catch (restoreError) {
        if (obsolete()) return;
        if (restoreError instanceof ApiError && restoreError.status === 404) {
          if (window.localStorage.getItem("guitarscribe.activeJobId") === savedJobId) {
            window.localStorage.removeItem("guitarscribe.activeJobId");
          }
          if (linkedJobId === savedJobId) {
            const url = new URL(window.location.href);
            url.searchParams.delete("job");
            window.history.replaceState({}, "", url);
          }
          setAnalysisJob(null);
          setStatus("idle");
          setError("This saved analysis has expired or is no longer available. Start a new analysis below.");
          return;
        }
        setError("The backend is temporarily unavailable. Reconnecting automatically...");
        retryTimer = window.setTimeout(() => void restore(), 2000);
      }
    };
    void restore();
    return () => {
      disposed = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, []);

  useEffect(() => {
    if (scoreRef.current) return;
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
        setError("");
        if (nextJob.status === "completed" && nextJob.score) {
          if (pendingAnalysisBase.current !== undefined && pendingAnalysisBase.current !== scoreRef.current) {
            setRestorePreview({ id: "", base: scoreRef.current, generation: workGenerationRef.current,
              next: scoreFromJob(nextJob), job: nextJob });
            setStatus("ready");
            setSaveStatus("新曲目已完成；目前工作譜在分析期間改變，請先保存，再確認載入新結果。");
            pendingAnalysisBase.current = undefined;
            pendingAnalysisOrigin.current = null;
            return;
          }
          pendingAnalysisBase.current = undefined;
          pendingAnalysisOrigin.current = null;
          audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
          replaceScore(scoreFromJob(nextJob));
          restoreWorkingJob(nextJob.id);
          setAudioUrl(`${API_BASE}/api/v1/jobs/${nextJob.id}/audio`);
          setRevisionId("");
          setSaveStatus("Analysis loaded. Save to create a revision.");
          setStatus("ready");
          setShowNewSong(false); setFocusedWorkspace(true);
        } else if (nextJob.status === "failed" || nextJob.status === "cancelled") {
          recoverFailedAnalysis(nextJob);
        }
      } catch (pollError) {
        if (!disposed) {
          setError("The backend is temporarily busy; progress will reconnect automatically.");
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
    const chord = score?.chords.find((item) => item.id === selectedChordId);
    if (!chord) {
      setCandidateVoicings([]);
      return;
    }
    const symbol = chord.shape_symbol ?? chord.symbol;
    void fetch(API_BASE + "/chord-voicings?symbol=" + encodeURIComponent(symbol) + "&capo=" + capo + "&max_fret=" + (score?.guitar.max_fret ?? 15))
      .then((response) => response.ok ? response.json() : [])
      .then((voicings) => setCandidateVoicings(voicings))
      .catch(() => setCandidateVoicings([]));
  }, [score, selectedChordId, capo]);

  useEffect(() => {
    if (score) {
      setCapo(score.analysis.capo);
      setAccidentalPreference(score.key_context.accidental_preference);
    }
  }, [score]);

  useEffect(() => {
    if (!score) {
      setRhythmOptions([]);
      return;
    }
    let disposed = false;
    void fetch(`${API_BASE}/rhythm-patterns?time_signature=${encodeURIComponent(score.analysis.time_signature)}`)
      .then((response) => response.ok ? response.json() : [])
      .then((patterns: SongScore["rhythm"][]) => { if (!disposed) setRhythmOptions(patterns); })
      .catch(() => { if (!disposed) setRhythmOptions([]); });
    return () => { disposed = true; };
  }, [score?.analysis.time_signature]);

  // A compiled sequence belongs to one immutable score snapshot. Never let
  // newly edited notation run alongside old audio (including pending fetches).
  useEffect(() => {
    stopSynth(false);
    performanceGenerationRef.current++;
    setChordPerformance("original"); setPerformanceNotice("");
  }, [score]);

  function selectChordPerformance(mode: ChordPerformanceMode) {
    referenceStopRef.current(); stopSynth(false);
    performanceGenerationRef.current++;
    setChordPerformance(mode); setPerformanceNotice("");
  }
  useEffect(() => {
    audioRef.current?.pause(); stopSynth(false);
    setLoopRange(null); setLoopStart(null); setLoopEnd(null);
    setPlaybackTime((time) => time < bounds.start || time >= bounds.end ? bounds.start : time);
    if (audioRef.current && (audioRef.current.currentTime < bounds.start || audioRef.current.currentTime >= bounds.end)) audioRef.current.currentTime = bounds.start;
  }, [bounds.start, bounds.end]);

  useEffect(() => {
    if (!score || score.chords.length === 0) {
      setSelectedChordId(null);
      setChordDraft("");
      setChordStartDraft("");
      setChordEndDraft("");
      return;
    }

    const selectedChord = score.chords.find((chord) => chord.id === selectedChordId) ?? score.chords[0];
    setSelectedChordId(selectedChord.id);
    setChordDraft(selectedChord.symbol);
    setChordStartDraft(selectedChord.start.toFixed(2));
    setChordEndDraft(selectedChord.end.toFixed(2));
  }, [score, selectedChordId]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z") return;
      const target = event.target;
      if (target instanceof HTMLElement && (target.closest("input, textarea, select") || target.isContentEditable)) return;
      event.preventDefault();
      if (event.shiftKey) redoScoreChange();
      else undoScoreChange();
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [score, undoHistory, redoHistory]);

  useEffect(() => {
    const resumeSynthAfterVisibilityChange = () => {
      if (document.visibilityState !== "visible" || !isSynthPlaying) return;
      // A browser may suspend an AudioContext while the tab is hidden. The
      // look-ahead scheduler will skip expired events and resume from its
      // AudioContext-derived playhead once this promise resolves.
      void synthContextRef.current?.resume().catch(() => undefined);
    };
    document.addEventListener("visibilitychange", resumeSynthAfterVisibilityChange);
    return () => document.removeEventListener("visibilitychange", resumeSynthAfterVisibilityChange);
  }, [isSynthPlaying]);

  useEffect(() => {
    if (!isPlaying) return;
    const syncMediaPlayhead = () => {
      const audio = audioRef.current;
      if (audio && !audio.paused) handlePlaybackTime(createMediaTransportClock(audio).now());
      mediaAnimationRef.current = window.requestAnimationFrame(syncMediaPlayhead);
    };
    mediaAnimationRef.current = window.requestAnimationFrame(syncMediaPlayhead);
    return () => {
      if (mediaAnimationRef.current !== null) window.cancelAnimationFrame(mediaAnimationRef.current);
      mediaAnimationRef.current = null;
    };
  }, [isPlaying, bounds.start, bounds.end, loopStart, loopEnd, loopRange, metronomeEnabled, score]);

  const measureGroups = score ? (() => {
    const ranges = notationBars(score).map((bar) => ({ measure: bar.number, start: bar.start, end: bar.end }));
    return ranges.map((range) => {
      const chords = score.chords.filter((chord) => chord.start < range.end && chord.end > range.start).map((chord) => ({
        chord,
        start: Math.max(chord.start, range.start),
        end: Math.min(chord.end, range.end),
        continues: chord.start < range.start || chord.end > range.end,
        members: [chord],
      })).sort((left, right) => left.start - right.start);
      const spans: ChordSpan[] = [];
      let cursor = range.start;
      for (const chord of chords) {
        if (chord.start > cursor + 0.001) spans.push({ chord: null, start: cursor, end: chord.start, continues: false, members: [] });
        spans.push(chord);
        cursor = Math.max(cursor, chord.end);
      }
      if (cursor < range.end - 0.001) spans.push({ chord: null, start: cursor, end: range.end, continues: false, members: [] });
      return { ...range, chords, layout: measureLayout(score.beats, range.start, range.end, score.analysis.bpm), spans: showRawChordSegments ? spans : mergeChordSpans(spans) };
    });
  })() : [];

  const selectedChord = score?.chords.find((chord) => chord.id === selectedChordId) ?? null;
  const selectedChordTimingBounds = (() => {
    if (!score || !selectedChord) return null;
    const ordered = [...score.chords].sort((left, right) => left.start - right.start);
    const index = ordered.findIndex((chord) => chord.id === selectedChord.id);
    if (index < 0) return null;
    const draftStart = Number(chordStartDraft);
    const draftEnd = Number(chordEndDraft);
    return {
      start: Number.isFinite(draftStart) ? draftStart : selectedChord.start,
      end: Number.isFinite(draftEnd) ? draftEnd : selectedChord.end,
      startMin: ordered[index - 1] && Math.abs(ordered[index - 1].end-selectedChord.start)<1e-6 ? ordered[index - 1].start + .1 : ordered[index - 1]?.end ?? 0,
      startMax: selectedChord.end - 0.1,
      endMin: selectedChord.start + 0.1,
      endMax: ordered[index + 1] && Math.abs(ordered[index + 1].start-selectedChord.end)<1e-6 ? ordered[index + 1].end - .1 : ordered[index + 1]?.start ?? score.song.duration_seconds,
    };
  })();
  const activeChordId = score?.chords.find((chord) => playbackTime >= chord.start && playbackTime < chord.end)?.id ?? null;
  const soundingEvent = synthSnapshot?.manifest.events.filter((event) => event.track === "guitar"
    && event.start <= playbackTime && (guitarTone === "pluck" ? event.sustain_end ?? event.end : event.end) > playbackTime).at(-1);
  const soundingChord = synthSnapshot?.chords.find((chord) => chord.id === soundingEvent?.source_id);
  const activeBeatIndex = score?.beats.findIndex((beat, index) => playbackTime >= beat.time && playbackTime < (score.beats[index + 1]?.time ?? Infinity)) ?? -1;
  const activeBeatTimingBounds = (() => {
    if (!score || activeBeatIndex < 0) return null;
    const current = score.beats[activeBeatIndex];
    return {
      min: (score.beats[activeBeatIndex - 1]?.time ?? 0) + 0.02,
      max: (score.beats[activeBeatIndex + 1]?.time ?? score.song.duration_seconds) - 0.02,
      value: beatTimingDraft?.index === activeBeatIndex ? beatTimingDraft.time : current.time,
    };
  })();
  const scoreMeasures = measureGroups.map((group) => group.measure);
  const activeMeasureGroup = measureGroups.find((group) => playbackTime >= group.start && playbackTime < group.end) ?? measureGroups[0];
  const activeMeasureNotes = score && activeMeasureGroup ? score.melody.filter((note) => note.start >= activeMeasureGroup.start && note.start < activeMeasureGroup.end && note.string !== null && note.string !== undefined && note.fret !== null && note.fret !== undefined) : [];
  const activeMelodyNoteId = score?.melody.find((note) => playbackTime >= note.start && playbackTime < note.end)?.id ?? null;
  const melodyTimelineLabelIds = new Set<string>();
  if (score) {
    const minimumLabelGap = Math.max(score.song.duration_seconds / 12, 0.75);
    let lastLabelStart = -Infinity;
    for (const note of score.melody) {
      if (note.id === activeMelodyNoteId || note.start - lastLabelStart >= minimumLabelGap) {
        melodyTimelineLabelIds.add(note.id);
        lastLabelStart = note.start;
      }
    }
  }

  useEffect(() => {
    if (!followPlayhead || !activeChordId || (!isPlaying && !isSynthPlaying)) return;
    // The open melody editor owns its own scrolling viewport. Chord follow
    // must not pull the page away during audition, source playback or seek.
    if (document.querySelector(".melody-editor[open], .song-range-editor[open]")) return;
    document.querySelector<HTMLElement>(".chord-block-active")?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "nearest",
    });
  }, [activeChordId, followPlayhead, isPlaying, isSynthPlaying]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitInFlight.current || status === "queued" || (analysisJob && !["completed", "failed", "cancelled"].includes(analysisJob.status))) return;
    const useYouTube = Boolean(youtubeUrl.trim());
    if (!useYouTube && !file) {
      setError("請選擇音檔或輸入 YouTube 網址。");
      return;
    }
    if (!capabilities || (useYouTube && !capabilities.youtube_enabled)) {
      setError("來源能力尚未就緒，請確認服務狀態。"); return;
    }
    if (hasUnsavedChanges && !window.confirm("目前工作譜有未保存修改。新分析完成後將切換曲目；請先取消並保存，或確認繼續分析。")) return;

    submitInFlight.current = true;
    pendingAnalysisBase.current = scoreRef.current;
    pendingAnalysisOrigin.current = score ? { score, job: analysisJob, revision: new URLSearchParams(window.location.search).get("revision") } : null;
    setStatus("queued");
    setError("");
    try {
      if (!skipSeconds.trim() || !Number.isFinite(Number(skipSeconds)) || Number(skipSeconds) < 0) throw new Error("略過秒數必須是大於或等於 0 的數字。");
      audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
      workGenerationRef.current++;
      revisionRequestRef.current++;
      setIsLoadingRevision(false); setRestorePreview(null);
      const createdJob = useYouTube
        ? await createYouTubeAnalysisJob(youtubeUrl.trim(), melodyMode, MELODY_ENABLED && capabilities.vocal_separation_enabled && separateVocals, chordComplexity, Number(skipSeconds), analysisSeconds === "full" ? null : Number(analysisSeconds))
        : await createAnalysisJob(file!, melodyMode, MELODY_ENABLED && capabilities.vocal_separation_enabled && separateVocals, chordComplexity, Number(skipSeconds), analysisSeconds === "full" ? null : Number(analysisSeconds));
      const url = new URL(window.location.href);
      url.searchParams.delete("revision"); url.searchParams.set("job", createdJob.id);
      window.history.replaceState({}, "", url);
      setAnalysisJob(createdJob);
      window.localStorage.setItem("guitarscribe.activeJobId", createdJob.id);
    } catch (submitError) {
      pendingAnalysisBase.current = undefined;
      pendingAnalysisOrigin.current = null;
      setStatus("error");
      setError(submitError instanceof Error ? submitError.message : "Analysis failed.");
    } finally { submitInFlight.current = false; }
  }

  function recoverFailedAnalysis(failed: AnalysisJob) {
    const origin = pendingAnalysisOrigin.current;
    pendingAnalysisBase.current = undefined;
    pendingAnalysisOrigin.current = null;
    setStatus("error");
    setError(analysisErrorMessage(failed.error ?? failed.message ?? "分析已停止，目前工作譜保留。"));
    const current = scoreRef.current;
    if (!origin || !current || sourceJobId(current) !== sourceJobId(origin.score)) return;
    // Restore only the source context; never replace edits or clear Undo.
    const source = sourceJobId(current);
    const previousJob = origin.job?.status === "completed" && origin.job.id === source ? origin.job : null;
    setAnalysisJob(previousJob);
    setAudioUrl(previousJob ? `${API_BASE}/api/v1/jobs/${previousJob.id}/audio` : null);
    setDiagnosticAudioTrack("source");
    const url = new URL(window.location.href);
    if (url.searchParams.get("job") === failed.id) {
      url.searchParams.delete("job");
      if (origin.revision) url.searchParams.set("revision", origin.revision);
      else if (source) url.searchParams.set("job", source);
      window.history.replaceState({}, "", url);
    }
    try {
      if (source) localStorage.setItem("guitarscribe.activeJobId", source);
      else localStorage.removeItem("guitarscribe.activeJobId");
    } catch { /* The restored URL remains usable without browser storage. */ }
  }

  async function cancelCurrentJob() {
    if (!analysisJob) return;
    try {
      const cancelled = await cancelAnalysisJob(analysisJob.id);
      setAnalysisJob(cancelled);
      if (["failed", "cancelled"].includes(cancelled.status)) recoverFailedAnalysis(cancelled);
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Could not cancel analysis.");
    }
  }

  async function optimizeSongVoicings() {
    if (!score) return;
    try {
      const response = await fetch(`${API_BASE}/scores/optimize-voicings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score) });
      if (!response.ok) throw new Error(await response.text());
      recordScoreChange(await response.json());
    } catch (optimizerError) {
      if (!isCurrentWork()) return;
      setError(optimizerError instanceof Error ? optimizerError.message : "Could not optimize voicings.");
    }
  }

  async function findEasierCapo() {
    if (!score) return;
    try {
      const response = await fetch(`${API_BASE}/scores/capo-recommendations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ score, max_capo: score.guitar.max_capo }) });
      if (!response.ok) throw new Error(await response.text());
      const recommendations = await response.json();
      if (isCurrentWork()) setCapoRecommendations(recommendations);
    } catch (capoError) {
      if (!isCurrentWork()) return;
      setError(capoError instanceof Error ? capoError.message : "Could not find capo recommendations.");
    }
  }

  async function retuneScore(nextKey: string, nextCapo = capo, nextPreference = accidentalPreference) {
    if (!score) return;
    setIsRetuningScore(true);
    setError("");
    try {
      const nextSemitones = semitoneDelta(score.key_context.source.key, nextKey);
      const updated = await postTranspose(score, nextSemitones, nextPreference, nextCapo);
      recordScoreChange({ ...updated, guitar: { ...updated.guitar, capo: nextCapo } });
    } catch (transposeError) {
      if (!isCurrentWork()) return;
      setError(transposeError instanceof Error ? transposeError.message : "Transposition failed.");
    } finally {
      setIsRetuningScore(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  async function importLrcFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (!score || !selected) return;
    setIsImportingLyrics(true);
    try {
      const content = await selected.text();
      if (!isCurrentWork()) return;
      setLyricsDraft(content);
      recordScoreChange(await importLyrics(score, content, "lrc"));
    } catch (lyricsError) {
      if (!isCurrentWork()) return;
      setError(lyricsError instanceof Error ? lyricsError.message : "LRC import failed.");
    } finally {
      setIsImportingLyrics(false);
      event.target.value = "";
    }
  }

  async function saveLyrics() {
    if (!score || !lyricsDraft.trim()) return;
    setIsImportingLyrics(true);
    try {
      recordScoreChange(await importLyrics(score, lyricsDraft));
    } catch (lyricsError) {
      if (!isCurrentWork()) return;
      setError(lyricsError instanceof Error ? lyricsError.message : "Lyrics import failed.");
    } finally {
      setIsImportingLyrics(false);
    }
  }

  function nearestBeatTime(time: number) {
    if (!score || !snapLyricTiming || !score.beats.length) return time;
    return score.beats.reduce((closest, beat) => Math.abs(beat.time - time) < Math.abs(closest - time) ? beat.time : closest, score.beats[0].time);
  }

  function commitLyricTiming(lineId: string, start?: number, end?: number) {
    if (!score?.lyrics) return;
    const current = score.lyrics.lines.find((line) => line.id === lineId);
    if (!current) return;
    const nextStart = start === undefined ? current.start : Number(nearestBeatTime(start).toFixed(3));
    const nextEnd = end === undefined ? current.end : Number(nearestBeatTime(end).toFixed(3));
    if (nextStart !== null && nextStart !== undefined && nextEnd !== null && nextEnd !== undefined && nextEnd < nextStart) {
      setError("Lyric end must not precede start.");
      return;
    }
    recordScoreChange({
      ...score,
      lyrics: {
        ...score.lyrics,
        revision: score.lyrics.revision + 1,
        lines: score.lyrics.lines.map((line) => line.id === lineId ? { ...line, start: nextStart, end: nextEnd, origin: "user", edited: true } : line),
      },
    });
    setLyricTimingDrafts((drafts) => {
      const { [lineId]: _, ...remaining } = drafts;
      return remaining;
    });
  }

  function setLyricTiming(lineId: string, boundary: "start" | "end") {
    commitLyricTiming(lineId, boundary === "start" ? playbackTime : undefined, boundary === "end" ? playbackTime : undefined);
  }

  function updateLyricTimingDraft(lineId: string, boundary: "start" | "end", value: number, fallbackStart: number, fallbackEnd: number) {
    setLyricTimingDrafts((drafts) => ({
      ...drafts,
      [lineId]: { start: drafts[lineId]?.start ?? fallbackStart, end: drafts[lineId]?.end ?? fallbackEnd, [boundary]: value },
    }));
  }

  function saveLyricText(lineId: string) {
    if (!score?.lyrics || editingLyricLineId !== lineId) return;
    const text = editingLyricText.trim();
    const current = score.lyrics.lines.find((line) => line.id === lineId);
    setEditingLyricLineId(null);
    if (!text || !current || text === current.text) return;
    recordScoreChange({
      ...score,
      lyrics: {
        ...score.lyrics,
        revision: score.lyrics.revision + 1,
        lines: score.lyrics.lines.map((line) => line.id === lineId ? { ...line, text, origin: "user", edited: true } : line),
      },
    });
  }

  function splitLyricLine(lineId: string) {
    if (!score?.lyrics) return;
    const lines = [...score.lyrics.lines].sort((left, right) => left.order - right.order);
    const index = lines.findIndex((line) => line.id === lineId);
    if (index < 0) return;
    const line = lines[index];
    const midpoint = Math.floor(line.text.length / 2);
    const splitAt = line.text.lastIndexOf(" ", midpoint) > 0 ? line.text.lastIndexOf(" ", midpoint) : line.text.indexOf(" ", midpoint);
    if (splitAt <= 0 || splitAt >= line.text.length - 1) {
      setError("This lyric line needs a space before it can be split.");
      return;
    }
    const before = line.text.slice(0, splitAt).trim();
    const after = line.text.slice(splitAt).trim();
    const splitTime = line.start !== null && line.start !== undefined && line.end !== null && line.end !== undefined
      ? line.start + (line.end - line.start) * (splitAt / line.text.length)
      : null;
    const first = { ...line, text: before, end: splitTime, origin: "user", edited: true };
    const second = { ...line, id: `${line.id}-split-${Date.now()}`, text: after, start: splitTime, origin: "user", edited: true };
    const nextLines = [...lines.slice(0, index), first, second, ...lines.slice(index + 1)].map((item, order) => ({ ...item, order }));
    recordScoreChange({ ...score, lyrics: { ...score.lyrics, revision: score.lyrics.revision + 1, lines: nextLines } });
  }

  function mergeLyricLineWithNext(lineId: string) {
    if (!score?.lyrics) return;
    const lines = [...score.lyrics.lines].sort((left, right) => left.order - right.order);
    const index = lines.findIndex((line) => line.id === lineId);
    if (index < 0 || index + 1 >= lines.length) return;
    const line = lines[index];
    const next = lines[index + 1];
    const merged = { ...line, text: `${line.text.trim()} ${next.text.trim()}`.trim(), end: next.end ?? line.end, origin: "user", edited: true };
    const nextLines = [...lines.slice(0, index), merged, ...lines.slice(index + 2)].map((item, order) => ({ ...item, order }));
    recordScoreChange({ ...score, lyrics: { ...score.lyrics, revision: score.lyrics.revision + 1, lines: nextLines } });
  }

  async function distributeLyricTiming() {
    if (!score?.lyrics) return;
    try {
      const response = await fetch(API_BASE + "/scores/lyrics/distribute-timing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score) });
      if (!response.ok) throw new Error(await response.text());
      recordScoreChange(await response.json());
    } catch (error) {
      if (isCurrentWork()) setError(error instanceof Error ? error.message : "Lyrics timing failed.");
    }
  }

  async function fitLyricTimingToBars() {
    if (!score?.lyrics) return;
    try {
      const response = await fetch(API_BASE + "/scores/lyrics/fit-timing-to-bars", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score) });
      if (!response.ok) throw new Error(await response.text());
      recordScoreChange(await response.json());
    } catch (error) {
      if (isCurrentWork()) setError(error instanceof Error ? error.message : "Lyrics timing failed.");
    }
  }

  async function simplifyMelody() {
    if (!score || score.melody.length === 0) return;
    try {
      const response = await fetch(`${API_BASE}/scores/melody/simplify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ score, mode: melodyMode, min_confidence: 0.55, min_duration: 0.16 }),
      });
      if (!response.ok) throw new Error(await response.text());
      recordScoreChange(await response.json() as SongScore);
    } catch (simplifyError) {
      if (!isCurrentWork()) return;
      setError(simplifyError instanceof Error ? `Could not simplify melody: ${simplifyError.message}` : "Could not simplify melody.");
    }
  }

  async function downloadTextScore(endpoint: string, filename: string, mimeType: string, label: string) {
    if (!score) return;
    setError("");
    try {
      const response = await fetch(API_BASE + endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(score),
      });
      if (!response.ok) throw new Error(await response.text());
      const content = await response.text();
      if (!isCurrentWork()) return;
      const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
      try {
        const link = document.createElement("a");
        link.href = url; link.download = filename; link.click();
      } finally { URL.revokeObjectURL(url); }
    } catch (exportError) {
      if (isCurrentWork()) setError(`${label} 匯出失敗，工作譜仍保留，請稍後重試。${exportError instanceof Error ? ` ${exportError.message}` : ""}`);
    }
  }

  async function downloadLrc() {
    if (!score?.lyrics) return;
    await downloadTextScore("/scores/lrc", "guitarscribe-lyrics.lrc", "text/plain", "LRC");
  }

  async function downloadMidi() {
    if (!score || midiPending) return;
    const generation = performanceGenerationRef.current;
    const request = ++midiRequestRef.current;
    const obsolete = () => !isCurrentWork() || generation !== performanceGenerationRef.current || request !== midiRequestRef.current;
    setMidiPending(true);
    try {
      const exportScore = MELODY_ENABLED ? score : { ...score, melody: [] };
      const response = await fetch(API_BASE + (chordPerformance === "original" ? "/scores/midi" : "/scores/chord-entry-performance"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chordPerformance === "original" ? exportScore : { score: exportScore, mode: chordPerformance, output: "midi" }),
      });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      if (obsolete()) return;
      const url = URL.createObjectURL(new Blob([blob], { type: "audio/midi" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = chordPerformance === "original" ? (MELODY_ENABLED ? "guitarscribe-melody.mid" : "guitarscribe-accompaniment.mid") : `guitarscribe-${chordPerformance}.mid`;
      link.click(); URL.revokeObjectURL(url);
    } catch (error) {
      if (!obsolete()) setError(error instanceof Error ? error.message : "MIDI 匯出失敗");
    } finally { if (request === midiRequestRef.current) setMidiPending(false); }
  }

  async function downloadMusicXml() {
    await downloadTextScore("/scores/musicxml", "guitarscribe-melody.musicxml", "application/vnd.recordare.musicxml+xml", "MusicXML");
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
    await downloadTextScore("/scores/chordpro", "guitarscribe-score.chopro", "text/plain", "ChordPro");
  }

  function updateGuitarSetting<Key extends keyof SongScore["guitar"]>(key: Key, value: SongScore["guitar"][Key]) {
    if (!score) return;
    recordScoreChange({ ...score, guitar: { ...score.guitar, [key]: value } });
  }

  async function updateTabMapping(key: "max_fret" | "tab_preference", value: number | string) {
    if (!score) return;
    const nextScore = { ...score, guitar: { ...score.guitar, [key]: value } } as SongScore;
    try {
      const response = await fetch(`${API_BASE}/scores/remap-tab`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextScore),
      });
      if (!response.ok) throw new Error(await response.text());
      recordScoreChange(await response.json() as SongScore);
    } catch (requestError) {
      if (!isCurrentWork()) return;
      setError(requestError instanceof Error ? `Could not remap Tab: ${requestError.message}` : "Could not remap Tab.");
    }
  }

  function updateChords(transform: (chords: ScoreChord[]) => ScoreChord[]) {
    if (!score) return;
    recordScoreChange({ ...score, chords: transform(score.chords) });
  }

  function currentMeasureRange(time: number): [number, number] | null {
    if (!score || score.beats.length === 0) return null;
    const currentBeat = score.beats.filter((beat) => beat.time <= time).at(-1);
    if (!currentBeat) return null;
    const start = score.beats.find((beat) => beat.measure === currentBeat.measure)?.time ?? currentBeat.time;
    const next = score.beats.find((beat) => beat.measure === currentBeat.measure + 1)?.time ?? score.song.duration_seconds;
    return [Math.max(bounds.start, start), Math.min(bounds.end, next)];
  }

  function stopSynth(reset = false) {
    setActiveReview(null);
    melodyAuditionRef.current?.stop(); melodyAuditionRef.current = null;
    sourceLoadAbortRef.current?.abort(); sourceLoadAbortRef.current = null;
    setIsSourcePreparing(false);
    if (sourceSegmentRef.current) audioRef.current?.pause();
    sourceSegmentRef.current = false;
    synthGenerationRef.current++;
    setSynthSnapshot(null);
    setIsSynthPreparing(false);
    synthSourcesRef.current.forEach((source) => { try { source.stop(); } catch { } });
    synthSourcesRef.current = [];
    if (synthAnimationRef.current !== null) window.cancelAnimationFrame(synthAnimationRef.current);
    synthAnimationRef.current = null;
    if (synthSchedulerRef.current !== null) window.clearTimeout(synthSchedulerRef.current);
    synthSchedulerRef.current = null;
    if (synthCountInTimerRef.current !== null) window.clearTimeout(synthCountInTimerRef.current);
    synthCountInTimerRef.current = null;
    setIsCountingIn(false);
    setIsSynthPlaying(false);
    if (reset) {
      audioRef.current?.pause();
      if (audioRef.current) audioRef.current.currentTime = bounds.start;
      setPlaybackTime(bounds.start);
    }
  }

  function trackSynthSource(source: AudioScheduledSourceNode) {
    source.onended = () => {
      synthSourcesRef.current = synthSourcesRef.current.filter((scheduled) => scheduled !== source);
    };
    synthSourcesRef.current.push(source);
  }

  async function auditionEditedNotes(notes: Array<{ midi: number; start: number; end: number }>, range?: { start: number; end: number; loop?: boolean; from?: number }) {
    referenceStopRef.current(); audioRef.current?.pause(); stopSynth(false);
    if (notes.length > 256) { setError("此片段音符過密，請縮短試聽範圍；音符未變更。"); return; }
    const generation = synthGenerationRef.current;
    try {
      const context = synthContextRef.current ?? new AudioContext();
      synthContextRef.current = context;
      await context.resume();
      if (generation !== synthGenerationRef.current) return;
      const duration = range ? range.end - range.start : Math.max(...notes.map(n => n.end), 0);
      if (duration <= 0) return;
      const transport = startMelodyAudition(context, notes, {
        duration, from: range ? (range.from ?? range.start) - range.start : 0,
        loop: range?.loop, connection: melodyConnection,
        onComplete: () => {
          if (generation !== synthGenerationRef.current) return;
          if (range) setPlaybackTime(range.end);
          stopSynth(false);
        },
        onError: error => {
          if (generation !== synthGenerationRef.current) return;
          stopSynth(false); setError(error instanceof Error ? error.message : "Audio preview unavailable");
        },
      });
      melodyAuditionRef.current = transport;
      if (range) {
        setIsSynthPlaying(true); setPlaybackTime(range.start + transport.position());
        const update = () => {
          if (generation !== synthGenerationRef.current) return;
          setPlaybackTime(range.start + transport.position());
          if (transport.finished()) { stopSynth(false); return; }
          synthAnimationRef.current = window.requestAnimationFrame(update);
        };
        synthAnimationRef.current = window.requestAnimationFrame(update);
      }
    } catch (error) {
      if (generation !== synthGenerationRef.current) return;
      stopSynth(false); setError(error instanceof Error ? error.message : "Audio preview unavailable");
    }
  }

  async function auditionSourceSegment(start: number, end: number, previewOutsideRange = false) {
    if (!previewOutsideRange) { start = Math.max(bounds.start, start); end = Math.min(bounds.end, end); }
    if (end <= start) return;
    referenceStopRef.current(); stopSynth(false);
    setLoopRange(null); setLoopStart(null); setLoopEnd(null);
    const audio = audioRef.current;
    if (!audio) { setError("沒有可用來源音訊。"); return; }
    audio.pause(); setPlaybackTime(start);
    if (pendingAudioTrackSeekRef.current !== null) pendingAudioTrackSeekRef.current = start;
    const generation = synthGenerationRef.current;
    const loading = new AbortController(); sourceLoadAbortRef.current = loading;
    sourceSegmentRef.current = true;
    try {
      setIsSourcePreparing(true);
      await waitForMediaMetadata(audio, loading.signal);
      if (generation !== synthGenerationRef.current || audio !== audioRef.current) return;
      setIsSourcePreparing(false);
      audio.currentTime = start;
      await audio.play();
      if (generation !== synthGenerationRef.current) return;
      const update = () => {
        if (generation !== synthGenerationRef.current) return;
        if (audio.currentTime >= end || audio.ended) { audio.pause(); audio.currentTime = end; setPlaybackTime(end); stopSynth(false); return; }
        synthAnimationRef.current = window.requestAnimationFrame(update);
      };
      synthAnimationRef.current = window.requestAnimationFrame(update);
    } catch (error) { if (generation === synthGenerationRef.current) { stopSynth(false); setError(error instanceof Error ? error.message : "Source playback unavailable"); } }
  }

  function scheduleGuitarPick(context: AudioContext, startAt: number, peak: number) {
    const length = Math.max(1, Math.floor(context.sampleRate * 0.018));
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      samples[index] = (Math.random() * 2 - 1) * (1 - index / samples.length);
    }
    const pick = context.createBufferSource();
    const highPass = context.createBiquadFilter();
    const gain = context.createGain();
    highPass.type = "highpass";
    highPass.frequency.setValueAtTime(1500, startAt);
    gain.gain.setValueAtTime(Math.min(0.04, peak * 0.26), startAt);
    gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.018);
    pick.buffer = buffer;
    pick.connect(highPass).connect(gain).connect(context.destination);
    pick.start(startAt);
    pick.stop(startAt + 0.02);
    trackSynthSource(pick);
  }

  async function toggleSynthPlayback(segment?: { start: number; end: number; loop: boolean; from?: number; guitarOnly?: boolean; reviewMode?: ReviewMode }) {
    referenceStopRef.current();
    if (!score) return;
    if (isSynthPlaying && !segment) { stopSynth(false); return; }
    stopSynth(false);
    const selectedRange = segment ? clipRange(segment.start, segment.end, score) : null;
    if (selectedRange && selectedRange.end <= selectedRange.start) return;
    const reviewMode = segment?.reviewMode;
    const rate = reviewMode && reviewMode !== "guitar" ? 1 : playbackRate;
    const tone = reviewMode ? "pluck" : guitarTone;
    const tracks = reviewMode ? { guitar: reviewMode !== "source", melody: false, metronome: false } : segment ? { guitar: true, melody: !segment.guitarOnly, metronome: false } : synthTracks;
    const editorMelodyGain = segment && !segment.guitarOnly ? 0.25 : 1;
    const solo = segment ? null : synthSoloTrack;
    const generation = synthGenerationRef.current;
    setIsSynthPreparing(true);
    try {
      audioRef.current?.pause();
      const context = synthContextRef.current ?? new AudioContext();
      synthContextRef.current = context;
      await context.resume();
      if (generation !== synthGenerationRef.current) return;
      let originalBuffer: AudioBuffer | null = null;
      if (reviewMode && reviewMode !== "guitar") {
        if (!analysisJob || analysisJob.status !== "completed" || sourceJobId(score) !== analysisJob.id) throw new Error("此版本沒有相符的原曲來源。");
        if (reviewMode === "mix" && !score.key_context.audio_matches_notation) throw new Error("工作譜已移調，不能直接與原曲合奏。");
        const url = `${API_BASE}/api/v1/jobs/${analysisJob.id}/audio`;
        const cached = reviewSourceCacheRef.current;
        if (cached?.url === url) originalBuffer = cached.buffer;
        else {
          const abort = new AbortController(); sourceLoadAbortRef.current = abort;
          const response = await fetch(url, {signal: abort.signal});
          if (!response.ok) throw new Error("原曲載入失敗，請稍後重試。");
          originalBuffer = await context.decodeAudioData(await response.arrayBuffer());
          if (generation !== synthGenerationRef.current) return;
          reviewSourceCacheRef.current = {url, buffer: originalBuffer};
        }
        if (originalBuffer.duration + .01 < (selectedRange?.end ?? bounds.end)) throw new Error("原曲長度不足以涵蓋所選小節。");
      }
      const { manifest, notice } = await compilePlayback(score, chordPerformance);
      if (generation !== synthGenerationRef.current) return;
      setPerformanceNotice(notice);
      const buffers = tone === "pluck" && tracks.guitar && (solo === null || solo === "guitar")
        ? await preparePluckedBuffers(context, manifest.events.filter((event) => event.track === "guitar").flatMap((event) => event.pitches), () => generation !== synthGenerationRef.current)
        : new Map<number, AudioBuffer>();
      if (generation !== synthGenerationRef.current) return;
      setIsSynthPreparing(false);
      setActiveReview(reviewMode ?? null);
      setSynthSnapshot({ manifest, chords: score.chords });
      const rawLoop = selectedRange ? (segment?.loop ? [selectedRange.start, selectedRange.end] as [number, number] : null) : loopStart !== null && loopEnd !== null && loopEnd > loopStart
        ? [loopStart, loopEnd] as [number, number]
        : loopRange;
      const clippedLoop = rawLoop ? [Math.max(bounds.start, rawLoop[0]), Math.min(bounds.end, rawLoop[1])] : null;
      const requestedLoop = clippedLoop && clippedLoop[1] > clippedLoop[0] ? clippedLoop : null;
      const playhead = selectedRange ? Math.max(selectedRange.start, Math.min(segment?.from ?? selectedRange.start, selectedRange.end - .001)) : playbackTime >= bounds.end || playbackTime < bounds.start ? bounds.start : playbackTime;
      const scoreStart = requestedLoop && (playhead < requestedLoop[0] || playhead >= requestedLoop[1])
        ? requestedLoop[0]
        : playhead;
      const countInBeats = segment ? 0 : (Number(score.analysis.time_signature.charAt(0)) || 4) * countInMeasures;
      const beatSeconds = 60 / Math.max(score.analysis.bpm, 1) / rate;
      const countInStart = context.currentTime + 0.06;
      if (countInBeats > 0) {
        setIsCountingIn(true);
        for (let beat = 0; beat < countInBeats; beat += 1) {
          scheduleMetronomeClick(context, countInStart + beat * beatSeconds, beat % (Number(score.analysis.time_signature.charAt(0)) || 4) === 0);
        }
        synthCountInTimerRef.current = window.setTimeout(() => {
          synthCountInTimerRef.current = null;
          setIsCountingIn(false);
        }, countInBeats * beatSeconds * 1000);
      }
      const initialContextStart = countInStart + countInBeats * beatSeconds;
      const acousticEnd = (event: PlaybackManifest["events"][number]) =>
        event.track === "guitar" && tone === "pluck" ? event.sustain_end ?? event.end : event.end;
      const segmentEnd = selectedRange?.end ?? requestedLoop?.[1] ?? bounds.end;
      const firstEnd = initialContextStart + (segmentEnd - scoreStart) / rate;
      const loopDuration = requestedLoop ? (requestedLoop[1] - requestedLoop[0]) / rate : 0;
      if (requestedLoop && (!Number.isFinite(loopDuration) || loopDuration < .01 || firstEnd + loopDuration <= firstEnd)) {
        throw new Error("循環範圍過短，請擴大選取範圍。");
      }
      const createSegmentScheduler = (segmentStart: number, contextStart: number) => {
        if (originalBuffer) {
          const at = Math.max(context.currentTime + .005, contextStart);
          const offset = segmentStart + Math.max(0, at - contextStart) * rate;
          const duration = Math.min(segmentEnd, originalBuffer.duration) - offset;
          if (duration > 0) {
            const source = context.createBufferSource(), gain = context.createGain();
            source.buffer = originalBuffer; source.playbackRate.value = rate;
            const until = at + duration / rate, fade = Math.min(.005, duration / rate / 4);
            gain.gain.setValueAtTime(0, at); gain.gain.linearRampToValueAtTime(.45, at + fade);
            gain.gain.setValueAtTime(.45, until - fade); gain.gain.linearRampToValueAtTime(0, until);
            source.connect(gain).connect(context.destination);
            source.start(at, offset, duration); source.stop(until); trackSynthSource(source);
          }
        }

        const connected = melodyConnection === "connected" && tracks.melody && synthVolumes.melody > 0 && (solo === null || solo === "melody");
        const phrases = connected ? melodyPhrases(manifest.events.filter(event => event.track === "melody" && event.pitches.length === 1 && event.end > segmentStart && event.start < segmentEnd)
          .map(event => ({ start: event.start, end: event.end, midi: event.pitches[0], velocity: event.pitch_velocities?.[0] ?? event.velocity }))) : [];
        let nextPhraseIndex = 0;
        const segmentEvents = manifest.events
          .filter((event) => tracks[event.track] && synthVolumes[event.track] > 0 && (solo === null || event.track === solo) && acousticEnd(event) > segmentStart && event.start < segmentEnd)
          .filter(event => !(connected && event.track === "melody" && event.pitches.length === 1))
          .sort((left, right) => left.start - right.start);
        // Short editor selections are bounded: queue their complete audio up
        // front so rendering a large score cannot delay an internal onset.
        // Whole-song playback and dense selections keep the rolling horizon.
        const scheduleWholeSelection = !!selectedRange && segmentEnd - segmentStart <= 30
          && segmentEvents.reduce((count, event) => count + event.pitches.length, 0)
            + phrases.reduce((count, phrase) => count + phrase.length, 0) <= 1024;
        let nextEventIndex = 0;
        const scheduleEvent = (event: PlaybackManifest["events"][number], resumeScoreTime: number) => {
          const eventStart = Math.max(event.start, segmentStart, resumeScoreTime);
          const eventEnd = Math.min(acousticEnd(event), segmentEnd);
          if (eventEnd <= eventStart) return;
          if (event.track === "metronome") {
            const source = createMetronomeVoice(context,
              Math.max(context.currentTime + 0.005, contextStart + (eventStart - segmentStart) / rate),
              event.velocity > 100, synthVolumes.metronome);
            if (source) trackSynthSource(source);
            return;
          }
          event.pitches.forEach((pitch, pitchIndex) => {
            const compiledOffset = event.pitch_offsets[pitchIndex];
            if (event.track === "guitar" && tone === "pluck") {
              const onset = event.start + (compiledOffset ?? pitchIndex * 0.012);
              const startAt = Math.max(context.currentTime + 0.005,
                contextStart + (Math.max(onset, segmentStart, resumeScoreTime) - segmentStart) / rate);
              const endAt = contextStart + (eventEnd - segmentStart) / rate;
              const age = Math.max(0, (segmentStart - onset) / rate + (startAt - contextStart));
              const buffer = buffers.get(pitch);
              if (buffer) {
                const source = createPluckedVoice(context, buffer, startAt, endAt,
                  synthVolumes.guitar * (event.pitch_velocities[pitchIndex] ?? event.velocity) / 127 / Math.sqrt(event.pitches.length), age, event.stroke);
                if (source) trackSynthSource(source);
              }
              return;
            }
            const strumDelay = event.track === "guitar" ? (compiledOffset ?? pitchIndex * 0.012) / rate : 0;
            const startAt = Math.max(context.currentTime + 0.005, contextStart + (eventStart - segmentStart) / rate + strumDelay);
            const writtenEnd = contextStart + (eventEnd - segmentStart) / rate;
            const endAt = event.track === "melody" ? writtenEnd : Math.max(startAt + 0.025, writtenEnd);
            if (endAt <= startAt) return;
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            const isGuitar = event.track === "guitar";
            oscillator.type = isGuitar || event.track === "melody" ? "triangle" : "square";
            oscillator.frequency.setValueAtTime(440 * 2 ** ((pitch - 69) / 12), startAt);
            const pitchVelocity = event.pitch_velocities[pitchIndex] ?? event.velocity;
            const peak = Math.max(0.001, synthVolumes[event.track] * pitchVelocity / 127 / Math.max(event.pitches.length, 1))
              * (event.track === "melody" ? editorMelodyGain : 1);
            let releaseEnd = endAt;
            if (isGuitar) {
              const envelope = guitarEnvelope(startAt, endAt, peak);
              releaseEnd = envelope[envelope.length - 1].time;
              gain.gain.setValueAtTime(envelope[0].value, envelope[0].time);
              gain.gain.linearRampToValueAtTime(envelope[1].value, envelope[1].time);
              for (const point of envelope.slice(2)) {
                gain.gain.exponentialRampToValueAtTime(point.value, point.time);
              }
            } else {
              const envelope = melodyEnvelope(startAt, endAt, peak);
              gain.gain.setValueAtTime(envelope[0].value, envelope[0].time);
              gain.gain.linearRampToValueAtTime(envelope[1].value, envelope[1].time);
              gain.gain.linearRampToValueAtTime(envelope[2].value, envelope[2].time);
              gain.gain.exponentialRampToValueAtTime(envelope[3].value, envelope[3].time);
            }
            if (isGuitar) {
              const filter = context.createBiquadFilter();
              filter.type = "lowpass";
              filter.frequency.setValueAtTime(event.stroke === "U" ? 5600 : 3200, startAt);
              filter.frequency.exponentialRampToValueAtTime(event.stroke === "U" ? 1500 : 900, Math.min(endAt, startAt + 0.3));
              oscillator.connect(gain).connect(filter).connect(context.destination);
              if (pitchIndex === 0) scheduleGuitarPick(context, startAt, peak);
            } else {
              oscillator.connect(gain).connect(context.destination);
            }
            oscillator.start(startAt);
            oscillator.stop(releaseEnd + 0.01);
            trackSynthSource(oscillator);
          });
        };
        return () => {
          const elapsedScoreTime = Math.max(0, (context.currentTime - contextStart) * rate);
          const horizon = scheduleWholeSelection ? segmentEnd
            : segmentStart + (context.currentTime + SYNTH_SCHEDULE_AHEAD_SECONDS - contextStart) * rate;
          while (nextPhraseIndex < phrases.length && phrases[nextPhraseIndex][0].start < horizon) {
            const source = playMelodyPhrase(context, phrases[nextPhraseIndex], {
              scoreStart: segmentStart, scoreEnd: segmentEnd, contextStart, rate, peak: synthVolumes.melody * editorMelodyGain,
            });
            if (source) trackSynthSource(source);
            nextPhraseIndex++;
          }
          while (nextEventIndex < segmentEvents.length && segmentEvents[nextEventIndex].start < horizon) {
            scheduleEvent(segmentEvents[nextEventIndex], segmentStart + elapsedScoreTime);
            nextEventIndex += 1;
          }
        };
      };
      let passes = [{ end: firstEnd, schedule: createSegmentScheduler(scoreStart, initialContextStart) }];
      let nextOrigin = firstEnd;
      const schedulePending = () => {
        if (generation !== synthGenerationRef.current) return;
        try {
          const now = context.currentTime;
          if (!requestedLoop && now >= firstEnd) {
            setPlaybackTime(segmentEnd); stopSynth(false); return;
          }
          passes = passes.filter(pass => pass.end > now);
          if (requestedLoop) {
            // Preserve the original audio-clock grid even after a late timer.
            if (nextOrigin + loopDuration <= now) nextOrigin += Math.floor((now - nextOrigin) / loopDuration) * loopDuration;
            const horizon = now + SYNTH_SCHEDULE_AHEAD_SECONDS;
            while (nextOrigin < horizon) {
              passes.push({ end: nextOrigin + loopDuration, schedule: createSegmentScheduler(requestedLoop[0], nextOrigin) });
              nextOrigin += loopDuration;
            }
          }
          for (const pass of passes) pass.schedule();
          synthSchedulerRef.current = window.setTimeout(schedulePending, SYNTH_SCHEDULER_INTERVAL_MS);
        } catch (error) {
          stopSynth(false); setError(error instanceof Error ? error.message : "Could not schedule compiled score.");
        }
      };
      const updatePlayhead = () => {
        if (generation !== synthGenerationRef.current) return;
        const now = context.currentTime;
        const time = requestedLoop && now >= firstEnd
          ? requestedLoop[0] + ((now - firstEnd) % loopDuration) * rate
          : Math.min(segmentEnd, scoreStart + Math.max(0, now - initialContextStart) * rate);
        setPlaybackTime(time);
        synthAnimationRef.current = window.requestAnimationFrame(updatePlayhead);
      };
      setIsSynthPlaying(true);
      schedulePending();
      if (generation === synthGenerationRef.current) synthAnimationRef.current = window.requestAnimationFrame(updatePlayhead);
    } catch (synthError) {
      if (generation !== synthGenerationRef.current) return;
      stopSynth(false);
      setError(synthError instanceof Error ? synthError.message : "Could not play compiled score.");
    }
  }

  function scheduleMetronomeClick(context: AudioContext, startAt: number, accented: boolean) {
    const source = createMetronomeVoice(context, startAt, accented, synthVolumes.metronome);
    if (source) trackSynthSource(source);
  }

  function playMetronomeClick(accented: boolean) {
    const context = metronomeContextRef.current ?? new AudioContext();
    metronomeContextRef.current = context;
    scheduleMetronomeClick(context, context.currentTime, accented);
  }

  async function togglePlayback() {
    referenceStopRef.current();
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) { audio.pause(); if (sourceSegmentRef.current) stopSynth(false); return; }
    stopSynth(false);
    if (audio.currentTime < bounds.start || audio.currentTime >= bounds.end) audio.currentTime = bounds.start;
    if (!score || countInMeasures === 0) { await audio.play(); return; }
    const beatsPerMeasure = Number(score.analysis.time_signature.charAt(0)) || 4;
    const beatSeconds = 60 / Math.max(score.analysis.bpm, 1) / playbackRate;
    const clickCount = beatsPerMeasure * countInMeasures;
    const generation = synthGenerationRef.current;
    setIsCountingIn(true);
    for (let beat = 0; beat < clickCount; beat += 1) {
      window.setTimeout(() => { if (generation === synthGenerationRef.current) playMetronomeClick(beat % beatsPerMeasure === 0); }, beat * beatSeconds * 1000);
    }
    synthCountInTimerRef.current = window.setTimeout(() => {
      synthCountInTimerRef.current = null;
      if (generation !== synthGenerationRef.current) return;
      setIsCountingIn(false); void audio.play();
    }, clickCount * beatSeconds * 1000);
  }

  function handlePlaybackTime(time: number) {
    // Explicit source previews own their own boundary, including before a
    // previously saved song start while the user auditions a replacement.
    if (!sourceSegmentRef.current && score?.song_range) {
      if (time >= bounds.end) {
        const loop = loopStart !== null && loopEnd !== null && loopEnd > loopStart ? [loopStart, loopEnd] : loopRange;
        if (loop && loop[1] > bounds.start && loop[0] < bounds.end) { seekTo(Math.max(bounds.start, loop[0])); return; }
        audioRef.current?.pause();
        if (audioRef.current && audioRef.current.currentTime !== bounds.end) audioRef.current.currentTime = bounds.end;
        setPlaybackTime(bounds.end); return;
      }
      if (time < bounds.start) { if (audioRef.current) audioRef.current.currentTime = bounds.start; setPlaybackTime(bounds.start); return; }
    }
    setPlaybackTime(time);
    if (metronomeEnabled && score) {
      const beatIndex = score.beats.findIndex((beat, index) => time >= beat.time && time < (score.beats[index + 1]?.time ?? Infinity));
      if (beatIndex >= 0 && lastMetronomeBeatRef.current !== beatIndex) {
        lastMetronomeBeatRef.current = beatIndex;
        playMetronomeClick(score.beats[beatIndex].beat === 1);
      }
    }
    const activeLoop = loopStart !== null && loopEnd !== null && loopEnd > loopStart ? [loopStart, loopEnd] : loopRange;
    if (activeLoop && time >= activeLoop[1] - 0.03) seekTo(activeLoop[0]);
  }

  function seekTo(time: number) {
    time = Math.max(bounds.start, Math.min(bounds.end, time));
    if (isSynthPlaying || isSynthPreparing || sourceSegmentRef.current || isCountingIn) stopSynth(false);
    if (pendingAudioTrackSeekRef.current !== null) pendingAudioTrackSeekRef.current = time;
    setPlaybackTime(time);
    if (audioRef.current) {
      createMediaTransportClock(audioRef.current).seek?.(time);
    }
  }

  function selectDiagnosticAudioTrack(track: DiagnosticAudioTrack) {
    if (!analysisJob || analysisJob.status !== "completed" ||
        (score && sourceJobId(score) !== analysisJob.id) || track === diagnosticAudioTrack) return;
    referenceStopRef.current(); stopSynth(false);
    audioRef.current?.pause();
    setIsPlaying(false);
    pendingAudioTrackSeekRef.current = playbackTime;
    setDiagnosticAudioTrack(track);
    setAudioUrl(track === "source"
      ? `${API_BASE}/api/v1/jobs/${analysisJob.id}/audio`
      : `${API_BASE}/api/v1/jobs/${analysisJob.id}/artifacts/${track}`);
  }

  function seekMeasure(direction: -1 | 1) {
    if (!score) return;
    const measureStarts = Array.from(new Map(score.beats.map((beat) => [beat.measure, beat.time])).entries());
    const currentIndex = Math.max(0, measureStarts.findIndex(([, time], index) => playbackTime < (measureStarts[index + 1]?.[1] ?? Infinity)));
    const target = measureStarts[Math.max(0, Math.min(measureStarts.length - 1, currentIndex + direction))];
    if (target) seekTo(target[1]);
  }

  function nudgeBeatGrid(seconds: number) {
    if (!score || score.beats.length === 0) return;
    if (score.beats[0].time + seconds < 0) return;
    recordScoreChange({
      ...score,
      beats: score.beats.map((beat) => ({ ...beat, time: Number((beat.time + seconds).toFixed(3)) })),
    });
  }

  function setFirstDetectedBeat(beatNumber: number) {
    if (!score || score.beats.length === 0) return;
    const beatsPerMeasure = Number(score.analysis.time_signature.charAt(0)) || 4;
    const phase = Math.max(0, Math.min(beatsPerMeasure - 1, beatNumber - 1));
    recordScoreChange({
      ...score,
      beats: score.beats.map((beat, index) => ({
        ...beat,
        beat: (index + phase) % beatsPerMeasure + 1,
        measure: Math.floor((index + phase) / beatsPerMeasure) + 1,
      })),
    });
  }

  function nudgeActiveBeatRange(seconds: number) {
    if (!score || activeBeatIndex < 0) return;
    const firstMeasure = score.beats[activeBeatIndex].measure;
    const indexes = score.beats
      .map((beat, index) => ({ beat, index }))
      .filter(({ beat }) => beat.measure >= firstMeasure && beat.measure < firstMeasure + beatNudgeMeasures)
      .map(({ index }) => index);
    if (indexes.length === 0) return;

    const firstIndex = indexes[0];
    const lastIndex = indexes.at(-1)!;
    const firstTime = score.beats[firstIndex].time;
    const lastTime = score.beats[lastIndex].time;
    const minimum = (score.beats[firstIndex - 1]?.time ?? 0) + 0.02 - firstTime;
    const maximum = (score.beats[lastIndex + 1]?.time ?? score.song.duration_seconds) - 0.02 - lastTime;
    if (seconds < minimum || seconds > maximum) {
      setError("This bar range must remain at least 0.02 seconds away from its neighboring beats.");
      return;
    }
    const selected = new Set(indexes);
    recordScoreChange({
      ...score,
      beats: score.beats.map((beat, index) => selected.has(index) ? { ...beat, time: Number((beat.time + seconds).toFixed(3)) } : beat),
    });
  }

  function rebuildBeatGrid(points: SongScore["beats"], bpm: number) {
    if (!score) return;
    const beatsPerMeasure = Number(score.analysis.time_signature.charAt(0)) || 4;
    recordScoreChange({
      ...score,
      analysis: { ...score.analysis, bpm: Math.max(1, Math.round(bpm * 100) / 100) },
      beats: points.map((beat, index) => ({
        ...beat,
        beat: index % beatsPerMeasure + 1,
        measure: Math.floor(index / beatsPerMeasure) + 1,
      })),
    });
  }

  function correctHalfTime() {
    if (!score || score.beats.length < 3) return;
    const retained = score.beats.filter((_, index) => index % 2 === 0);
    if (retained.length >= 2) rebuildBeatGrid(retained, score.analysis.bpm / 2);
  }

  function correctDoubleTime() {
    if (!score || score.beats.length < 2) return;
    const expanded = score.beats.flatMap((beat, index) => {
      const next = score.beats[index + 1];
      if (!next) return [beat];
      return [
        beat,
        { ...beat, time: Number(((beat.time + next.time) / 2).toFixed(3)), confidence: Math.min(beat.confidence, next.confidence) },
      ];
    });
    rebuildBeatGrid(expanded, score.analysis.bpm * 2);
  }

  function commitBeatTiming(index: number, time: number) {
    if (!score || index < 0 || index >= score.beats.length) return;
    const previousTime = score.beats[index - 1]?.time ?? -0.02;
    const nextTime = score.beats[index + 1]?.time ?? score.song.duration_seconds + 0.02;
    if (time <= previousTime + 0.02 || time >= nextTime - 0.02) {
      setError("A beat must remain at least 0.02 seconds away from its neighboring beats.");
      return;
    }
    recordScoreChange({
      ...score,
      beats: score.beats.map((beat, beatIndex) => beatIndex === index ? { ...beat, time: Number(time.toFixed(3)) } : beat),
    });
    setBeatTimingDraft(null);
  }

  function setActiveBeatAtPlayhead() {
    if (activeBeatIndex >= 0) commitBeatTiming(activeBeatIndex, playbackTime);
  }

  function setSpeed(nextRate: number) {
    if (isSynthPlaying || isSynthPreparing) stopSynth(false);
    setPlaybackRate(nextRate);
    if (audioRef.current) audioRef.current.playbackRate = nextRate;
  }

  function selectChord(chord: ScoreChord, seekTime = chord.start) {
    setChordEditScope(null);
    setSelectedChordId(chord.id);
    seekTo(seekTime);
    setChordDraft(chord.symbol);
  }

  function renameSelectedChord() {
    if (!selectedChordId) return;
    const nextSymbol = chordDraft.trim();
    if (!nextSymbol) return;
    if (!/^[A-G][#b]?[a-zA-Z0-9+#b()°ø-]*(?:\/[A-G][#b]?)?$/.test(nextSymbol)) { setError("請輸入和弦名稱，例如 C、Am、G7 或 C/E。"); return; }
    setError("");

    try {
      audioRef.current?.pause(); stopSynth(false);
      updateChords(chords => editChordSlice(chords, selectedChordId, chordEditScope, {
        symbol: nextSymbol,
        shape_symbol: shiftedChordName(nextSymbol, -(score?.guitar.capo ?? 0)),
        source_symbol: shiftedChordName(nextSymbol, -(score?.key_context.transpose_semitones ?? 0)),
        voicing_id: null, available_voicings: [], origin: "user", edited: true,
      }));
    } catch (error) { setError(error instanceof Error ? error.message : "修改失敗，原譜已保留。"); }
  }

  function applyVoicing(voicing: NonNullable<ScoreChord["available_voicings"]>[number]) {
    if (!selectedChordId) return;
    updateChords((chords) => chords.map((chord) => chord.id === selectedChordId ? { ...chord, voicing_id: voicing.id, available_voicings: candidateVoicings, origin: "user", edited: true } : chord));
  }

  function applyChordTiming(start: number, end: number) {
    if (!selectedChordId || !score) return;
    try {
      const next = retimeChord(score, selectedChordId, start, end);
      audioRef.current?.pause(); stopSynth(false);
      setError(""); recordScoreChange(next);
    } catch (error) { setError(error instanceof Error ? error.message : "拍長調整失敗，原譜已保留。"); }
  }
  function saveSelectedChordTiming() {
    if (!chordStartDraft.trim() || !chordEndDraft.trim()) { setError("請填入開始與結束時間。"); return; }
    applyChordTiming(Number(chordStartDraft), Number(chordEndDraft));
  }
  function changeChordBeats(delta: number) {
    if (!score || !selectedChord) return;
    try { applyChordTiming(selectedChord.start, shiftByBeats(score, selectedChord.end, delta)); }
    catch (error) { setError(error instanceof Error ? error.message : "目前無法調整拍長。"); }
  }
  const selectedChordBeats = (() => {
    if (!score || !selectedChord) return null;
    try {return beatCoordinate(score,selectedChord.end)-beatCoordinate(score,selectedChord.start);}
    catch {return null;}
  })();

  function addChordAtPlayhead() {
    if (!score) return;
    const start = Number(playbackTime.toFixed(3));
    const current = score.chords.find((chord) => start >= chord.start && start < chord.end);
    const symbol = chordDraft.trim() || "C";
    if (current) {
      if (start - current.start < 0.1 || current.end - start < 0.1) {
        setError("Move the playhead at least 0.1 seconds inside the chord before adding a change.");
        return;
      }
      const chord: ScoreChord = { id: "user-" + Date.now(), start, end: current.end, symbol, source_symbol: null, shape_symbol: symbol, confidence: 1, origin: "user", edited: true, voicing_id: null, available_voicings: [] };
      updateChords((chords) => [
        ...chords.map((existing) => existing.id === current.id ? { ...existing, end: start, origin: "user", edited: true } : existing),
        chord,
      ].sort((left, right) => left.start - right.start));
      setSelectedChordId(chord.id);
      return;
    }
    const next = score.chords.filter((chord) => chord.start > start).sort((left, right) => left.start - right.start)[0];
    const end = next?.start ?? score.song.duration_seconds;
    if (end - start < 0.1) {
      setError("Move the playhead to an empty gap of at least 0.1 seconds before adding a chord.");
      return;
    }
    const chord: ScoreChord = { id: "user-" + Date.now(), start, end, symbol, source_symbol: null, shape_symbol: symbol, confidence: 1, origin: "user", edited: true, voicing_id: null, available_voicings: [] };
    updateChords((chords) => [...chords, chord].sort((left, right) => left.start - right.start));
    setSelectedChordId(chord.id);
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

  function removeSelectedBarChord() {
    if (!selectedChordId || !chordEditScope) return;
    try {
      audioRef.current?.pause(); stopSynth(false); setError("");
      updateChords(chords => removeChordSlice(chords,selectedChordId,chordEditScope));
      setCompactEditOpen(false); setChordEditScope(null); setSelectedChordId(null);
    } catch (error) {setError(error instanceof Error ? error.message : "刪除失敗，原譜保留。");}
  }

  function deleteSelectedChord() {
    if (!selectedChordId) return;
    updateChords((chords) => chords.filter((chord) => chord.id !== selectedChordId));
    setSelectedChordId(null);
    setChordDraft("");
  }

  async function saveRevision(createNew = true) {
    if (!score || saveInFlightRef.current) return;
    saveInFlightRef.current = true;
    const generation = workGenerationRef.current;
    setIsSavingRevision(true);
    setError("");
    try {
      const response = await postSaveRevision(score, revisionId.trim() || null, createNew);
      const jobId = sourceJobId(score) ?? workingJobId;
      const remembered = { id: response.revision_id, label: MELODY_ENABLED ? `${melodyVersion(score)} · ${score.melody.length} 音符` : `伴奏工作譜 · ${score.chords.length} 段和弦`, jobId };
      setRememberedVersion(remembered);
      let storageWarning = "";
      try {
        window.localStorage.setItem("guitarscribe.savedVersion", JSON.stringify(remembered));
        if (jobId) window.localStorage.setItem(`guitarscribe.melodyRevision.${jobId}`, response.revision_id);
      } catch { storageWarning = " 瀏覽器無法記住版本，請抄下此 ID。"; }
      if (scoreRef.current !== score || generation !== workGenerationRef.current) {
        setSaveStatus(`Saved snapshot ${response.revision_id}; subsequent changes are not saved.${storageWarning}`);
        return;
      }
      setRevisionId(response.revision_id);
      rememberRevisionUrl(response.revision_id);
      cleanScoreRef.current = score;
      setSavedSnapshot({ id: response.revision_id, score });
      setSaveStatus(`Saved revision ${response.revision_id}.${storageWarning}`);
    } catch (saveError) {
      const message = MELODY_ENABLED ? saveError instanceof Error ? saveError.message : "Revision save failed." : "暫時無法保存，修改仍保留在這個頁面。請保持頁面開啟，並在版本歷史中按保存重試。";
      setError(message); setSaveStatus(message);
    } finally {
      saveInFlightRef.current = false;
      setIsSavingRevision(false);
    }
  }

  async function loadRevision(requestedId = revisionId.trim()) {
    if (!requestedId) return;
    const request = ++revisionRequestRef.current;
    const base = scoreRef.current;
    const generation = workGenerationRef.current;
    setRestorePreview(null);
    setIsLoadingRevision(true);
    setError("");
    try {
      const loadedScore = await getRevision(requestedId);
      const source = sourceJobId(loadedScore);
      let job: AnalysisJob | null = null;
      if (source) {
        try { job = await getAnalysisJob(source); } catch { /* Saved notes remain usable after source expiry. */ }
      }
      if (request !== revisionRequestRef.current) return;
      if (base !== scoreRef.current || generation !== workGenerationRef.current) { setSaveStatus("讀取期間工作譜已改變，未載入舊回應。請重新選擇恢復版本。"); return; }
      setRestorePreview({ id: requestedId, base, generation, next: loadedScore, job });
      setSaveStatus("已讀取保存版本；請在上方「工作版本」確認恢復，目前樂譜未變。");
    } catch (loadError) {
      if (request === revisionRequestRef.current) setError(loadError instanceof Error ? loadError.message : "Revision load failed.");
    } finally {
      if (request === revisionRequestRef.current) setIsLoadingRevision(false);
    }
  }

  function applyRestoredVersion() {
    if (!restorePreview) return;
    const { id, base, generation, next, job } = restorePreview;
    if (scoreRef.current !== base || generation !== workGenerationRef.current) { setRestorePreview(null); setSaveStatus("工作譜已改變，未恢復舊預覽。請重新讀取版本。"); return; }
    audioRef.current?.pause(); stopSynth(false); referenceStopRef.current();
    if (!recordScoreChange(next)) return;
    if (!id && job) {
      setRestorePreview(null); setSavedSnapshot(null); cleanScoreRef.current = next;
      setWorkingJobId(job.id); setAnalysisJob(job); setRevisionId("");
      setAudioUrl(`${API_BASE}/api/v1/jobs/${job.id}/audio`); setDiagnosticAudioTrack("source");
      const url = new URL(window.location.href);
      url.searchParams.delete("revision"); url.searchParams.set("job", job.id);
      window.history.replaceState({}, "", url);
      setShowNewSong(false); setFocusedWorkspace(true); setStatus("ready");
      setSaveStatus("已載入新曲目分析；可用 Undo 回復前一份工作譜，請另存版本。");
      return;
    }
    finishRevisionRestore(id, next, job);
  }

  function rememberRevisionUrl(id: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("revision", id);
    url.searchParams.delete("job");
    window.history.replaceState({}, "", url);
  }

  function finishRevisionRestore(id: string, next: SongScore, job: AnalysisJob | null) {
    cleanScoreRef.current = next;
    rememberRevisionUrl(id);
    setError("");
    setSavedSnapshot({ id, score: next });
    setRevisionId(id);
    const source = sourceJobId(next);
    setWorkingJobId(source);
    const remembered = { id, label: MELODY_ENABLED ? `${melodyVersion(next)} · ${next.melody.length} 音符` : `伴奏工作譜 · ${next.chords.length} 段和弦`, jobId: source };
    setRememberedVersion(remembered);
    let storageWarning = "";
    try {
      localStorage.setItem("guitarscribe.savedVersion", JSON.stringify(remembered));
      if (source) localStorage.setItem(`guitarscribe.melodyRevision.${source}`, id);
    } catch { storageWarning = " 瀏覽器無法記住版本，請抄下此 ID。"; }
    // Never leave another song's source audio attached to a restored score.
    const compatible = job?.status === "completed" && job.score
      && job.score.song.duration_seconds === next.song.duration_seconds
      && (job.score.song.source_start_seconds ?? 0) === (next.song.source_start_seconds ?? 0);
    setAnalysisJob(compatible ? job : null);
    setDiagnosticAudioTrack("source");
    setAudioUrl(compatible ? `${API_BASE}/api/v1/jobs/${job.id}/audio` : null);
    setStatus("ready");
    setRestorePreview(null);
    setSaveStatus(`Loaded revision ${id}.${compatible ? "" : " 來源音訊未恢復；仍可編輯及播放保存的樂譜。"}${storageWarning}`);
  }

  useEffect(() => {
    if (MELODY_ENABLED || !revisionId) { setVersionHistory([]); return; }
    let active=true;
    void fetch(`${API_BASE}/revisions/${encodeURIComponent(revisionId)}/history`).then(r=>r.ok?r.json():[]).then(rows=>{if(active)setVersionHistory(rows);}).catch(()=>{if(active)setVersionHistory([]);});
    return ()=>{active=false;};
  },[revisionId]);
  const lastAutoSaveAttempt = useRef<SongScore | null>(null);
  useEffect(() => {
    if (MELODY_ENABLED || !score || !hasUnsavedChanges || analysisBusy || isSavingRevision || lastAutoSaveAttempt.current === score) return;
    const timer = window.setTimeout(() => { lastAutoSaveAttempt.current = score; void saveRevision(true); }, 1200);
    return () => window.clearTimeout(timer);
  }, [score, hasUnsavedChanges, analysisBusy, isSavingRevision]);

  const compactChordEditor = !MELODY_ENABLED && compactEditOpen && selectedChord ? <section className="compact-chord-editor" aria-label="修改和弦">
                  <h3>修改 {chordEditScope ? chordEditScope.bar===0 ? "起始片段的 " : `第 ${chordEditScope.bar} 小節的 ` : ""}{selectedChord.symbol}</h3>
                  {score?.analysis.timing_status === "unmetered" ? <>
                    <p>使用歌曲的實際秒數。調整相連交界時，前後和弦會一起銜接；已有空白會保留，可用「復原」取消。</p>
                    <label>開始時間（秒）<input type="number" step="0.01" min="0" value={chordStartDraft} onChange={e=>setChordStartDraft(e.target.value)}/></label>
                    <label>結束時間（秒）<input type="number" step="0.01" min="0" value={chordEndDraft} onChange={e=>setChordEndDraft(e.target.value)}/></label>
                    <button type="button" onClick={saveSelectedChordTiming}>套用時間</button>
                    <p>刪除後此段吉他留白，原曲繼續播放。</p>
                    <button type="button" onClick={()=>{audioRef.current?.pause();stopSynth(false);recordScoreChange({...score,chords:score.chords.filter(c=>c.id!==selectedChord.id)});setCompactEditOpen(false);}}>刪除此段和弦</button>
                  </> : <>
                  <p>{chordEditScope ? `名稱只修改${chordEditScope.bar===0 ? "起始片段" : `第 ${chordEditScope.bar} 小節`}內選到的和弦，不影響前後小節。` : "名稱修改整段和弦。"}拍長調整仍影響整段和弦與相連交界，可用「復原」取消。</p>
                  {chordEditScope && selectedChordBeats !== null && score ? <p aria-label="本小節片段拍長">本小節內：{Number((beatCoordinate(score,Math.min(selectedChord.end,chordEditScope.end))-beatCoordinate(score,Math.max(selectedChord.start,chordEditScope.start))).toFixed(2))} 拍</p> : null}
                  <p aria-label="目前和弦拍長">整段拍長（含跨小節部分）：{selectedChordBeats === null ? "拍點不足" : `${Number(selectedChordBeats.toFixed(2))} 拍`}</p>
                  <div><button type="button" disabled={selectedChordBeats === null} onClick={()=>changeChordBeats(-.5)}>減少半拍</button><button type="button" disabled={selectedChordBeats === null} onClick={()=>changeChordBeats(.5)}>增加半拍</button></div>
                  <p>拍長按鈕會立即套用並自動保存；已有休止不移動下一和弦，不能跨越其他和弦。</p>
                  {chordEditScope ? <div className="chord-removal"><p>只刪除此小節內的片段：前面相連的和弦會接續；沒有則留白。下一小節保留，可用「復原」取消。</p><button type="button" onClick={removeSelectedBarChord}>刪除此小節內的片段</button></div> : null}
                  </>}
                  <label htmlFor="compact-chord-name">和弦名稱</label>
                  <input id="compact-chord-name" value={chordDraft} onChange={e=>setChordDraft(e.target.value)} placeholder="例如 C、Am、G7" />
                  <div><button type="button" disabled={!chordDraft.trim() || chordDraft.trim()===selectedChord.symbol} onClick={()=>{renameSelectedChord();setCompactEditOpen(false);}}>套用和弦修改</button>
                  <button type="button" onClick={()=>{setChordDraft(selectedChord.symbol);setCompactEditOpen(false);}}>關閉編輯</button>
                  <button type="button" hidden={score?.analysis.timing_status === "unmetered"} onClick={()=>{setCompactEditOpen(false);setChordEditScope(null);setFocusedWorkspace(false);window.requestAnimationFrame(()=>document.querySelector<HTMLElement>(".side-panel")?.scrollIntoView({block:"start"}));}}>調整時間與指型</button></div>
                </section> : null;

  return (
    <div className={`page-shell${!MELODY_ENABLED ? " chord-product" : ""}${focusMode ? " focus-workspace" : ""}`}>
      <div className="aurora aurora-left" />
      <div className="aurora aurora-right" />
      <main className="layout">
        <div hidden={focusMode || !MELODY_ENABLED}><PlaybackReference stopRef={referenceStopRef} onStart={() => { stopSynth(false); audioRef.current?.pause(); }} /></div>
        <section className="hero-card new-song-panel" aria-label="新曲目來源" hidden={MELODY_ENABLED ? focusMode && !showNewSong : productScreen !== "home"}>
          <div className="hero-copy">
            <p className="eyebrow">GuitarScribe</p>
            <h1>把歌曲變成和弦譜</h1>
            <p className="lede">
              選擇歌曲，對照原曲與吉他，再保存你的和弦譜。
            </p>
          </div>

          <form className="intake-card" onSubmit={handleSubmit}>
            <p role="status">{capabilities ? "分析服務已就緒" : capabilitiesFailed ? "無法取得分析能力，請確認服務後重新整理。" : "正在確認分析能力…"}</p>
            {MELODY_ENABLED && capabilities && !capabilities.melody_available ? <p role="note">目前僅分析拍點與和弦，不會產生旋律；完成後可手動補音。</p> : null}
            {MELODY_ENABLED && capabilities?.melody_available && capabilities.vocal_separation_enabled && melodyMode === "vocal" && separateVocals ? <p>分析完成後先用「原曲＋系統吉他」核對和弦。自動旋律仍屬實驗功能，未達品質驗收門檻。</p> : null}
            <label className="field">
              <span>選擇音檔</span>
              <input type="file" accept=".wav,.mp3,.flac,.ogg,.m4a,audio/*" onChange={handleFileChange} />
            </label>

            <label className="field">
              <span>YouTube 網址</span>
              <input aria-label="YouTube video URL" aria-invalid={!youtubeUrlValid} aria-describedby="youtube-url-feedback" type="url" disabled={!capabilities?.youtube_enabled} value={youtubeUrl} onChange={(event) => setYoutubeUrl(event.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
              <small id="youtube-url-feedback">{!youtubeUrlValid ? "請貼上單一 YouTube 影片網址，例如 https://youtu.be/影片代碼。" : capabilities?.youtube_enabled ? "同時選擇音檔與網址時，以網址為準。" : "目前服務未開啟 YouTube，請使用音檔。"}</small>
            </label>

            <label className="field">分析長度<select aria-label="Analysis duration" value={analysisSeconds} onChange={event => setAnalysisSeconds(event.target.value)}>
              {[30, 45, 60].map(seconds => <option key={seconds} value={seconds}>{seconds} 秒</option>)}
              <option value="full">整首</option>
            </select></label>
            <details><summary>進階分析設定</summary>
            <label><input type="checkbox" checked={analysisSeconds === "full"} onChange={event => setAnalysisSeconds(event.target.checked ? "full" : "45")} />分析整首（耗時較長）</label>
            <div className="field-row">
              <label className="field" hidden={!MELODY_ENABLED}>
                <span>Melody focus (Beta)</span>
                <select disabled={capabilities?.melody_available === false} value={melodyMode} onChange={(event) => setMelodyMode(event.target.value)}>
                  <option value="vocal">Vocal melody (Beta)</option>
                  <option value="guitar">Guitar melody (Experimental)</option>
                  <option value="mix">Full-mix lead guess (Experimental)</option>
                </select>
              </label>

              <label className="field vocal-isolation-option" hidden={!MELODY_ENABLED}>
                <span>Vocal isolation</span>
                <label className="checkbox-label">
                  <input type="checkbox" checked={separateVocals} disabled={melodyMode !== "vocal" || !capabilities?.vocal_separation_enabled || !capabilities?.melody_available} onChange={(event) => setSeparateVocals(event.target.checked)} />
                  Isolate vocals first (requires enabled server; slower, clearer lead line)
                </label>
              </label>

              <label className="field">
                <span>和弦細節</span>
                <select value={chordComplexity} onChange={(event) => setChordComplexity(event.target.value)}>
                  <option value="simple">Simple</option>
                  <option value="standard">Standard</option>
                  <option value="full">Full</option>
                </select>
              </label>
            </div>
            </details>

            <div className="rights-box">
              <label className="field">
                <span>分析前略過開頭（秒）</span>
                <input aria-label="Skip opening seconds" type="number" min="0" step="0.01" required value={skipSeconds} onChange={(event) => setSkipSeconds(event.target.value)} />
              </label>
              <p>從略過位置開始分析所選長度，工作譜以 0 秒起算。請使用有權分析的來源。</p>
            </div>

            <button aria-label="Start analysis" className="primary-button" type="submit" disabled={!youtubeUrlValid || !capabilities || status === "queued" || !!(analysisJob && !["completed", "failed", "cancelled"].includes(analysisJob.status))}>
              {status === "queued" ? "正在分析…" : "開始分析"}
            </button>
            {score ? <button type="button" className="ghost-button" onClick={() => setShowNewSong(false)}>{MELODY_ENABLED ? "收起來源，繼續修譜" : "回到歌曲"}</button> : !MELODY_ENABLED && rememberedVersion ? <button type="button" disabled={isLoadingRevision} onClick={()=>void loadRevision(rememberedVersion.id)}>繼續上次的歌曲</button> : null}
          </form>
        </section>

        {error ? <p className="error-banner" role="alert">{error}</p> : null}
        {analysisJob && !["completed", "failed", "cancelled"].includes(analysisJob.status) ? (
          <section className="job-progress" aria-live="polite">
            <div>
              <strong>{analysisJob.message}</strong>
              <span>{analysisJob.progress}%</span>
            </div>
            <progress value={analysisJob.progress} max="100">{analysisJob.progress}%</progress>
            {analysisJob.status === "vocal_separation" ? <p className="job-stage-note">This stage may stay at 66% while Demucs is actively processing. You can leave this page open; do not submit the same song again.</p> : null}
            <button className="ghost-button" type="button" onClick={() => void cancelCurrentJob()}>Cancel analysis</button>
          </section>
        ) : null}

        <section className="workspace" hidden={!MELODY_ENABLED && productScreen !== "song"}>
          <div className="panel result-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">GuitarScribe</p>
                <h2>{score ? score.song.title : "開始你的和弦譜"}</h2>
                {!MELODY_ENABLED && ["bc41b274-69d4-430f-8dda-52bd0759119d", "3188712c-bfb9-461d-a19b-d45b10466efe"].includes(revisionId) ? <p role="note">這是尚未完整整理拍格的歷史版本。<a href="/review.html" target="_blank" rel="noopener noreferrer">開啟拍格譜（新分頁）</a>；目前修改保留在此頁。</p> : null}
                {!MELODY_ENABLED && score ? <p role="status" className="autosave-status">{isSavingRevision ? "正在保存…" : hasUnsavedChanges ? lastAutoSaveAttempt.current === score ? "尚未保存，請在版本歷史中重試。" : "等待自動保存…" : savedSnapshot ? "已保存" : "原始分析已保留"}</p> : null}
              </div>
              <div className="status-pill" hidden={!MELODY_ENABLED}>{status === "ready" ? "可編輯" : analysisJob ? `${analysisJob.progress}%` : "尚未分析"}</div>
            </div>

            {score ? <nav className="workspace-mode" aria-label="工作區模式">
              <div><strong>{focusMode ? accompanimentView ? "和弦核對" : "專注修譜" : "完整工具"}</strong><p>選一段 → 對照來源 → 修譜與重播 → 保存版本</p></div>
              <button type="button" className="ghost-button" onClick={() => { setShowNewSong(value => !value); }}>{showNewSong ? "收起新曲目" : "分析新曲目"}</button>
              <button type="button" hidden={!MELODY_ENABLED} className="ghost-button" onClick={switchWorkspace}>{focusMode ? "顯示完整工具" : accompanimentView ? "回到和弦核對" : "回到專注修譜"}</button>
              <button type="button" hidden={accompanimentView && focusMode} className="ghost-button" onClick={openPerformanceControls}>伴奏演奏</button>
              <button type="button" hidden={!MELODY_ENABLED} className="ghost-button" onClick={switchEditorView}>{accompanimentView ? "旋律編輯（實驗）" : "簡潔和弦頁"}</button>
            </nav> : null}
            <details className="version-history" open={MELODY_ENABLED ? true : undefined}><summary hidden={MELODY_ENABLED}>版本歷史與還原</summary><section className="revision-recovery" aria-label="工作版本">
              <h3>工作版本</h3>
              {!MELODY_ENABLED && versionHistory.length ? <label>已保存的版本<select aria-label="版本歷史" value="" onChange={e=>{if(e.target.value)void loadRevision(e.target.value);}}><option value="">選擇版本（最近 50 份）</option>{versionHistory.map(item=><option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} {item.id===revisionId?"· 目前版本":""}</option>)}</select></label>:null}
              {!MELODY_ENABLED && score ? <><button type="button" disabled={!analysisJob?.score || analysisJob.status!=="completed"} onClick={()=>{if(analysisJob?.score && window.confirm("還原原始分析？目前修改可用「復原」找回。")) {audioRef.current?.pause();stopSynth(false);recordScoreChange(scoreFromJob(analysisJob));}}}>還原原始分析</button><button type="button" onClick={switchWorkspace}>{focusMode?"診斷與完整工具":"關閉完整工具"}</button></>:null}
              <p aria-label="Current working version">{score ? accompanimentView ? `伴奏工作譜 · ${score.chords.length} 段和弦` : `${melodyVersion(score)} · ${score.melody.length} 音符` : "尚未載入樂譜"} · {savedSnapshot?.score === score ? accompanimentView && focusMode ? "已保存／載入" : `已保存／載入：${savedSnapshot.id}` : hasUnsavedChanges ? "有未保存修改" : "目前為原分析／未保存初稿"}</p>
              {score ? <button type="button" disabled={isSavingRevision || isLoadingRevision} onClick={() => void saveRevision(true)}>{isSavingRevision ? "正在保存…" : "保存目前工作版本"}</button> : null}
              {score && accompanimentView && focusMode ? <button type="button" disabled={!undoHistory.length} title="還原這個工作階段最近一次修改" onClick={undoScoreChange}>還原上一步</button> : null}
              {rememberedVersion ? <div hidden={accompanimentView && focusMode && savedSnapshot?.score === score && rememberedVersion.id === savedSnapshot.id}>
                <p>可恢復：{MELODY_ENABLED ? rememberedVersion.label : "伴奏工作版本"} · {rememberedVersion.id}。此記錄不代表目前已載入。</p>
                <button type="button" disabled={isLoadingRevision || isSavingRevision} onClick={() => void loadRevision(rememberedVersion.id)}>恢復上次保存版本</button>
              </div> : <p hidden={!MELODY_ENABLED}>尚無此分析的保存記錄。請保存目前工作版本；保存後可用版本網址重新開啟同一份譜。</p>}
              {isLoadingRevision ? <button type="button" onClick={() => { revisionRequestRef.current++; setIsLoadingRevision(false); setSaveStatus("已取消讀取，目前工作譜不變。"); }}>取消讀取版本</button> : null}
              {restorePreview ? <div role="status">
                <p>待恢復：{MELODY_ENABLED ? `${melodyVersion(restorePreview.next)} · ${restorePreview.next.melody.length} 音符` : `伴奏工作譜 · ${restorePreview.next.chords.length} 段和弦`} · {restorePreview.id}</p>
                {restorePreview.generation !== workGenerationRef.current ? <p>工作譜已改變，此預覽已失效；請重新讀取要恢復的版本。</p> : null}
                <p>{hasUnsavedChanges ? "目前有未保存修改，建議先保存。" : ""}確認後切換工作譜；原工作譜可用 Undo 找回。</p>
                <button type="button" disabled={isSavingRevision || restorePreview.generation !== workGenerationRef.current} onClick={applyRestoredVersion}>確認恢復版本（可 Undo）</button>
                <button type="button" onClick={() => setRestorePreview(null)}>保留目前工作譜</button>
              </div> : null}
              <p role="status" hidden={accompanimentView && focusMode && saveStatus.startsWith("Loaded revision")}>{!MELODY_ENABLED && saveStatus === "No saved revision yet." ? "" : !MELODY_ENABLED && saveStatus.startsWith("Saved revision") ? "已保存，可放心離開；下次用目前網址繼續。" : saveStatus}</p>
            </section>

            </details>
            {!score ? <section className="revision-recovery" aria-label="載入已保存修訂">
              <h3>繼續編輯已保存的樂譜</h3>
              <p>原分析失效時，仍可用保存的版本 ID 載入和弦譜、編輯及試聽吉他；原曲音訊需仍保留在本機。</p>
              <label className="field">版本 ID<input aria-label="Saved revision ID" value={revisionId} onChange={(event) => setRevisionId(event.target.value)} /></label>
              <button type="button" className="ghost-button" disabled={isLoadingRevision || !revisionId.trim()} onClick={() => void loadRevision()}>載入已保存修訂</button>
            </section> : null}

            {score ? (
              <>
                <ReviewComponent score={score} sourceAvailable={!!analysisJob && analysisJob.status === "completed" && sourceJobId(score) === analysisJob.id}
                  playing={activeReview !== null && isSynthPlaying} preparing={isSynthPreparing}
                  playhead={playbackTime} guitarVolume={synthVolumes.guitar} onVolume={value => setSynthVolumes(v => ({...v, guitar: value}))}
                  performanceLabel={chordPerformance === "original" ? "原版刷奏" : chordPerformance === "continuous" ? "換和弦即彈・連續刷奏" : "換和弦只彈一下"}
                  onStop={() => { audioRef.current?.pause(); stopSynth(false); }} onTools={openPerformanceControls}
                  onPlay={(mode, start, end, loop, from) => void toggleSynthPlayback({start, end, loop, from, reviewMode: mode})}
                  editPanel={compactChordEditor} speed={playbackRate} onSpeed={setSpeed}
                  keyControls={!MELODY_ENABLED ? <><label>調性 <select aria-label="歌曲調性" value={score.key_context.target.key} disabled={isRetuningScore} onChange={e=>void retuneScore(e.target.value)}>{PITCH_TO_FLAT_KEY.map(key=><option key={key} value={key}>{key}</option>)}{!PITCH_TO_FLAT_KEY.includes(score.key_context.target.key)?<option value={score.key_context.target.key}>{score.key_context.target.key}</option>:null}</select></label><label>Capo <select aria-label="歌曲 Capo" value={capo} disabled={isRetuningScore} onChange={e=>void retuneScore(score.key_context.target.key,Number(e.target.value))}>{Array.from({length:9},(_,n)=><option key={n} value={n}>{n}</option>)}</select></label></>:null}
                  secondaryActions={!MELODY_ENABLED ? <><button type="button" disabled={!undoHistory.length} onClick={undoScoreChange}>復原</button><button type="button" disabled={!redoHistory.length} onClick={redoScoreChange}>重做</button></>:null}
                  onEditChord={(id, scope) => { const chord=score.chords.find(c=>c.id===id); if (!chord) return; selectChord(chord, Math.max(chord.start, scope?.start ?? chord.start)); setChordEditScope(scope ?? null); setCompactEditOpen(true); window.requestAnimationFrame(()=>document.querySelector<HTMLInputElement>("#compact-chord-name")?.focus()); }} />
                {!MELODY_ENABLED ? <section className="compact-exports" aria-label="保存與匯出">
                  <details><summary>下載與備份</summary><p>{score.analysis.timing_status === "unmetered" ? "下載附秒數的和弦文字或完整工作檔。" : "下載和弦文字、伴奏 MIDI 或完整工作檔。"}</p>
                  <div><button type="button" onClick={()=>void downloadChordPro()}>下載和弦譜</button>
                  <button type="button" hidden={score.analysis.timing_status === "unmetered"} disabled={midiPending} onClick={()=>void downloadMidi()}>{midiPending ? "準備伴奏檔…" : "下載伴奏 MIDI"}</button>
                  <button type="button" onClick={downloadScoreJson}>備份完整工作檔</button></div></details>
                </section> : null}
                <div hidden={focusMode || score.analysis.timing_status === "unmetered"} className="advanced-workspace">
                {(score.song.source_start_seconds ?? 0) > 0 ? <p role="status">分析前已略過 {score.song.source_start_seconds} 秒；樂譜／播放 0 秒 = 原檔 {score.song.source_start_seconds} 秒。請勿再次略過同一段開場。</p> : null}
                <SongRangeEditor score={score} playhead={playbackTime}
                  onPreview={(start, end) => void auditionSourceSegment(start, end, true)}
                  onApply={(range) => { audioRef.current?.pause(); stopSynth(false); recordScoreChange({ ...score, song_range: range ?? null }); }} />
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

                <div className="capo-advisor"><button type="button" className="ghost-button" onClick={() => void findEasierCapo()}>Find easier capo</button>
                  <button type="button" className="ghost-button" onClick={() => void optimizeSongVoicings()}>Optimize song voicings</button>{capoRecommendations.length > 0 ? <div className="capo-options">{capoRecommendations.slice(0, 3).map((option) => <button key={option.capo} type="button" className="voicing-card" onClick={() => void retuneScore(score.key_context.target.key, option.capo)}><strong>Capo {option.capo} · {option.shape_key} shape</strong><span>Difficulty {option.difficulty}/5 · {option.open_chords} open · {option.barre_chords} barre</span></button>)}</div> : null}</div>

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
                  <button type="button" className="ghost-button" onClick={undoScoreChange} disabled={undoHistory.length === 0}>Undo</button>
                  <button type="button" className="ghost-button" onClick={redoScoreChange} disabled={redoHistory.length === 0}>Redo</button>
                </div>

                <section className="guitar-settings">
                  <h3>Guitar settings</h3>
                  <label className="field compact-field"><span>Max capo</span><select value={score.guitar.max_capo} onChange={(event) => updateGuitarSetting("max_capo", Number(event.target.value))}>{Array.from({ length: 13 }, (_, value) => <option key={value} value={value}>{value}</option>)}</select></label>
                  <label className="field compact-field"><span>Max fret</span><select value={score.guitar.max_fret} onChange={(event) => void updateTabMapping("max_fret", Number(event.target.value))}>{[5, 7, 9, 12, 15, 17, 19, 21, 24].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
                  <label className="field compact-field"><span>Tab mapping</span><select value={score.guitar.tab_preference} onChange={(event) => void updateTabMapping("tab_preference", event.target.value)}><option value="balanced">Balanced</option><option value="low_position">Low position</option><option value="single_string">Stay on one string</option></select></label>
                  <label className="field compact-field"><span>Handedness</span><select value={score.guitar.handedness} onChange={(event) => updateGuitarSetting("handedness", event.target.value)}><option value="right">Right-handed</option><option value="left">Left-handed</option></select></label>
                  <label className="field compact-field"><span>Difficulty</span><select value={score.guitar.difficulty} onChange={(event) => updateGuitarSetting("difficulty", event.target.value)}><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label>
                </section>

                {!score.key_context.audio_matches_notation ? (
                  <p className="warning-banner">
                    Notation is transposed to {score.key_context.target.key} {score.key_context.target.mode}, but the
                    original uploaded audio still sounds in {score.key_context.source.key} {score.key_context.source.mode}.
                  </p>
                ) : null}

                {score.analysis.warnings.length ? (
                  <section className="analysis-warnings" aria-live="polite">
                    <strong>Analysis notes</strong>
                    <ul>{score.analysis.warnings.map((warning, index) => <li key={warning + index}>{warning}</li>)}</ul>
                  </section>
                ) : null}

                {audioUrl ? (
                  <section className="transport-bar">
                    <audio
                      key={audioUrl}
                      ref={audioRef}
                      src={audioUrl}
                      onLoadedMetadata={(event) => {
                        if (event.currentTarget !== audioRef.current) return;
                        event.currentTarget.playbackRate = playbackRate;
                        if (pendingAudioTrackSeekRef.current !== null) {
                          event.currentTarget.currentTime = pendingAudioTrackSeekRef.current;
                          pendingAudioTrackSeekRef.current = null;
                        }
                      }}
                      onTimeUpdate={(event) => handlePlaybackTime(event.currentTarget.currentTime)}
                      onPlay={() => { referenceStopRef.current(); if (!sourceSegmentRef.current) stopSynth(false); setIsPlaying(true); }}
                      onPause={() => setIsPlaying(false)}
                      onEnded={() => setIsPlaying(false)}
                    />
                    {analysisJob?.status === "completed" ? <div className="diagnostic-track-switcher" aria-label="Diagnostic audio source"><span>Compare audio</span>{([
                      ["source", "Original"],
                      ["vocal-stem", "Vocal stem"],
                      ["accompaniment-stem", "Accompaniment stem"],
                      ["melody-contour", "Contour melody (Experimental)"],
                      ["raw-melody", "Raw detector"],
                      ["final-melody", "Final melody"],
                    ] as Array<[DiagnosticAudioTrack, string]>).filter(([track]) => MELODY_ENABLED || ["source", "accompaniment-stem"].includes(track)).map(([track, label]) => <button key={track} type="button" title={track === "melody-contour" ? "Requires saved pitch data from a new vocal-isolated pYIN analysis. This does not change Play score, MIDI or Tab." : undefined} className={diagnosticAudioTrack === track ? "ghost-button diagnostic-track-active" : "ghost-button"} disabled={track !== "source" && !analysisJob.artifacts?.includes(track)} onClick={() => selectDiagnosticAudioTrack(track)}>{label}</button>)}</div> : null}
                    {diagnosticAudioTrack === "melody-contour" ? <p role="status">Experimental source-pitch playback, separate from score notes. Vocal-source only: instrumental interludes and outros are not recovered. Key/capo edits, MIDI and Tab do not change this audio. Whole-song melody accuracy is not yet verified.</p> : null}
                    {diagnosticAudioTrack === "accompaniment-stem" ? <p role="status">Separated accompaniment for comparison: includes rhythm, bass and other instruments, not an extracted instrumental melody.</p> : null}
                    <button type="button" className="ghost-button" onClick={() => seekMeasure(-1)}>Previous bar</button>
                    <button type="button" className="ghost-button" disabled={isCountingIn} onClick={() => void togglePlayback()}>
                      {isCountingIn ? "Counting in..." : isPlaying ? "Pause" : "Play"}
                    </button>
                    <button type="button" className="ghost-button" onClick={() => seekMeasure(1)}>Next bar</button>
                    <button type="button" className="ghost-button" onClick={() => setLoopRange((range) => range ? null : currentMeasureRange(playbackTime))}>{loopRange ? "Looping bar" : "Loop bar"}</button>
                    <button type="button" className="ghost-button" onClick={() => { setLoopStart(playbackTime); setLoopEnd(null); }}>Set A</button>
                    <button type="button" className="ghost-button" disabled={loopStart === null} onClick={() => { if (loopStart !== null && playbackTime > loopStart) setLoopEnd(playbackTime); }}>Set B</button>
                    {loopStart !== null ? <button type="button" className="ghost-button" onClick={() => { setLoopStart(null); setLoopEnd(null); }}>Clear A–B</button> : null}
                    <button type="button" className="ghost-button" onClick={() => setMetronomeEnabled((enabled) => !enabled)}>{metronomeEnabled ? "Metronome on" : "Metronome off"}</button>
                    <button type="button" className="ghost-button" onClick={() => setFollowPlayhead((enabled) => !enabled)}>{followPlayhead ? "Follow score on" : "Follow score off"}</button>
                    <span className="transport-beat-grid">Beat grid {score.beats[0]?.time.toFixed(1) ?? "—"}s</span><button type="button" className="ghost-button" disabled={!score.beats.length || score.beats[0].time < 0.1} onClick={() => nudgeBeatGrid(-0.1)}>Beat −100ms</button><button type="button" className="ghost-button" disabled={!score.beats.length} onClick={() => nudgeBeatGrid(0.1)}>Beat +100ms</button>
                    <button type="button" className="ghost-button" disabled={score.beats.length < 3} onClick={correctHalfTime}>Half-time</button><button type="button" className="ghost-button" disabled={score.beats.length < 2} onClick={correctDoubleTime}>Double-time</button>
                    <label className="transport-speed">First detected beat <select aria-label="First detected beat in bar" value={score.beats[0]?.beat ?? 1} disabled={!score.beats.length} onChange={(event) => setFirstDetectedBeat(Number(event.target.value))}>{Array.from({ length: Number(score.analysis.time_signature.charAt(0)) || 4 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}</select></label>
                    <span className="transport-beat-grid">{activeBeatIndex >= 0 ? `Current beat ${score.beats[activeBeatIndex].beat} · Bar ${score.beats[activeBeatIndex].measure} at ${score.beats[activeBeatIndex].time.toFixed(1)}s` : "No current beat"}</span><button type="button" className="ghost-button" disabled={activeBeatIndex < 0} onClick={setActiveBeatAtPlayhead}>Set beat at playhead</button>
                    {activeBeatTimingBounds && activeBeatIndex >= 0 ? <label className="beat-timing-control">Drag beat<input aria-label="Drag current beat time" type="range" min={activeBeatTimingBounds.min} max={Math.max(activeBeatTimingBounds.min, activeBeatTimingBounds.max)} step="0.01" value={activeBeatTimingBounds.value} onChange={(event) => setBeatTimingDraft({ index: activeBeatIndex, time: Number(event.target.value) })} onPointerUp={() => commitBeatTiming(activeBeatIndex, activeBeatTimingBounds.value)} /></label> : null}
                    <label className="transport-speed">Nudge range <select aria-label="Beat nudge range" value={beatNudgeMeasures} onChange={(event) => setBeatNudgeMeasures(Number(event.target.value))}><option value={1}>1 bar</option><option value={2}>2 bars</option><option value={4}>4 bars</option></select></label><button type="button" className="ghost-button" disabled={activeBeatIndex < 0} onClick={() => nudgeActiveBeatRange(-0.1)}>Range −100ms</button><button type="button" className="ghost-button" disabled={activeBeatIndex < 0} onClick={() => nudgeActiveBeatRange(0.1)}>Range +100ms</button>
                    <label className="transport-speed">Count-in <select value={countInMeasures} onChange={(event) => setCountInMeasures(Number(event.target.value))}><option value={0}>Off</option><option value={1}>1 bar</option><option value={2}>2 bars</option></select></label>
                    <button type="button" className="ghost-button" onClick={() => stopSynth(true)}>Stop</button>
                    <label className="transport-speed">Speed <select value={playbackRate} onChange={(event) => setSpeed(Number(event.target.value))}>{[0.5, 0.6, 0.75, 0.9, 1, 1.1, 1.25, 1.5].map((rate) => <option key={rate} value={rate}>{Math.round(rate * 100)}%</option>)}</select></label>
                    <input className="transport-timeline" type="range" min={bounds.start} max={bounds.end} step="0.01" value={Math.max(bounds.start, Math.min(playbackTime, bounds.end))} onPointerDown={() => setFollowPlayhead(false)} onKeyDown={() => setFollowPlayhead(false)} onChange={(event) => { setFollowPlayhead(false); seekTo(Number(event.target.value)); }} aria-label="Playback position" />
                    <span>{playbackTime.toFixed(1)}s / {score.song.duration_seconds.toFixed(1)}s</span>
                    {MELODY_ENABLED && analysisJob?.status === "completed" ? <DiagnosticTimeline audioUrl={`${API_BASE}/api/v1/jobs/${analysisJob.id}/audio`} score={score} playbackTime={playbackTime} onSeek={seekTo} /> : null}
                  </section>
                ) : null}

                <details className="synth-panel workspace-disclosure">
                  <summary>Compiled score playback</summary>
                  <PlaybackRangeEditor start={bounds.start} end={bounds.end} loopStart={loopStart} loopEnd={loopEnd}
                    onInteract={() => setFollowPlayhead(false)}
                    onApply={(a, b) => { audioRef.current?.pause(); stopSynth(false); setFollowPlayhead(false); setLoopRange(null); setLoopStart(a); setLoopEnd(b); seekTo(a); }}
                    onClear={() => { audioRef.current?.pause(); stopSynth(false); setLoopStart(null); setLoopEnd(null); }} />
                  {!followPlayhead ? <p>手動定位時已關閉頁面自動跟隨。<button type="button" className="ghost-button" onClick={() => setFollowPlayhead(true)}>恢復播放跟隨</button></p> : null}
                  <div className="toolbar-actions">
                    <button type="button" hidden={!MELODY_ENABLED} className="ghost-button" onClick={() => { stopSynth(false); setSynthTracks({ guitar: true, melody: true, metronome: false }); setSynthSoloTrack(null); setSynthVolumes({ guitar: 0.24, melody: 0.45, metronome: 0.18 }); }}>旋律＋吉他（預設平衡）</button>
                    <button type="button" hidden={!MELODY_ENABLED} className="ghost-button" onClick={() => { stopSynth(false); setSynthTracks((tracks) => ({ ...tracks, melody: true })); setSynthSoloTrack("melody"); setSynthVolumes((volumes) => ({ ...volumes, melody: 0.45 })); }}>只聽旋律</button>
                  </div>
                  <p>旋律音色與上下刷音色調整只影響此處試聽，不改寫音符／拍點，也不改變 MIDI 播放器的音色。套用聆聽配置後請按 Play score。</p>
                  <p>播放採用目前調性、移調夾、指型與刷奏設定。 修改樂譜或刷奏後會停止舊播放，請重新按 Play score。</p>
                  <p aria-label="Playback chord comparison">譜面當前：{score.chords.find((chord) => chord.id === activeChordId)?.symbol ?? "—"} · 演奏事件：{isSynthPlaying && !isCountingIn && synthTracks.guitar && synthVolumes.guitar > 0 && (synthSoloTrack === null || synthSoloTrack === "guitar") ? soundingChord?.symbol ?? "—" : "—"}</p>
                  <p>Guitar plays a suggested strumming pattern on the detected beat grid, not the original recording's arrangement. To compare, click the same bar's chord before using Original / Play and Play score. Short chords between strums may not sound; inspect the chord sheet for all detected changes.</p>
                  <p>「吉他演奏」同時用於 Play score 與 Download MIDI。這是本次工作階段的選擇，不寫入樂譜；改譜、載入版本或重新整理後回到原版。實驗方案不會自動校正錯誤和弦。</p>
                  {performanceNotice ? <p role="status">{performanceNotice}</p> : null}
                  <ChordEntryAudit score={score} mode={chordPerformance} apiBase={API_BASE}
                    onSeek={(time) => { stopSynth(false); setFollowPlayhead(false); seekTo(time); }} />
                  <ChordGridCandidate score={score} apiBase={API_BASE} canUndo={undoHistory.length > 0} onUndo={undoScoreChange} onCommit={(base, next) => {
                    if (scoreRef.current !== base) return false;
                    return recordScoreChange(next);
                  }} />
                  <div className="synth-controls">
                    <label>吉他演奏 <select aria-label="吉他演奏方案" value={chordPerformance} onChange={(event) => selectChordPerformance(event.target.value as ChordPerformanceMode)}>
                      <option value="original">原版刷奏</option>
                      <option value="continuous">換和弦即彈・連續刷奏（實驗）</option>
                      <option value="sparse">換和弦只彈一下（實驗）</option>
                    </select></label>
                    <button type="button" className="ghost-button" disabled={chordPerformance === "original"} onClick={() => selectChordPerformance("original")}>回原版演奏</button>
                    <label>Guitar tone <select aria-label="Score guitar tone" value={guitarTone} onChange={(event) => { stopSynth(false); setGuitarTone(event.target.value); }}><option value="pluck">新：逐泛音衰減</option><option value="simple">舊：簡單振盪器</option></select></label>
                    <button type="button" className="ghost-button" disabled={isSynthPreparing} onClick={() => void toggleSynthPlayback()}>{isSynthPreparing ? "Preparing score…" : isSynthPlaying ? "Pause score" : "Play score"}</button>
                    <button type="button" className="ghost-button" onClick={() => stopSynth(true)}>Stop score</button>
                    {(["guitar", "melody", "metronome"] as PlaybackTrack[]).filter(track => MELODY_ENABLED || track !== "melody").map((track) => <label className="synth-track" key={track}><input type="checkbox" aria-label={track + " track"} checked={synthTracks[track]} onChange={() => { stopSynth(false); setSynthTracks((tracks) => ({ ...tracks, [track]: !tracks[track] })); }} /><span>{track}</span><input type="range" min="0" max="1" step="0.01" value={synthVolumes[track]} onChange={(event) => { stopSynth(false); setSynthVolumes((volumes) => ({ ...volumes, [track]: Number(event.target.value) })); }} aria-label={track + " volume"} /><button type="button" className={synthSoloTrack === track ? "synth-solo synth-solo-active" : "synth-solo"} onClick={() => { stopSynth(false); setSynthSoloTrack((current) => current === track ? null : track); }}>{synthSoloTrack === track ? "Soloed" : "Solo"}</button></label>)}
                    <span role="status">{activeBeatIndex >= 0 ? `Bar ${score.beats[activeBeatIndex].measure} · Beat ${score.beats[activeBeatIndex].beat}` : "Beat —"}</span>
                  </div>
                </details>

                <details className="lyrics-panel workspace-disclosure">
                  <summary>Lyrics{score.lyrics?.lines.length ? ` · ${score.lyrics.lines.length} lines` : ""}</summary>
                  <textarea value={lyricsDraft} onChange={(event) => setLyricsDraft(event.target.value)} placeholder="Paste lyrics you are allowed to use. One line per lyric line." rows={5} />
                  <div className="lyrics-actions"><button type="button" className="ghost-button" disabled={isImportingLyrics || !lyricsDraft.trim()} onClick={() => void saveLyrics()}>{isImportingLyrics ? "Importing..." : "Import lyrics"}</button><label className="ghost-button">Import LRC<input type="file" accept=".lrc,text/plain" onChange={importLrcFile} hidden /></label><button type="button" className="ghost-button" disabled={!score.lyrics?.lines.length} onClick={() => void distributeLyricTiming()}>Distribute timing</button><button type="button" className="ghost-button" disabled={!score.lyrics?.lines.length || !score.beats.length} onClick={() => void fitLyricTimingToBars()}>Fit timing to bars</button><button type="button" className="ghost-button" onClick={() => setSnapLyricTiming((enabled) => !enabled)}>{snapLyricTiming ? "Snap to beat on" : "Snap to beat off"}</button></div>
                  {score.lyrics?.lines.length ? <div className="lyrics-lines">{score.lyrics.lines.map((line, lineIndex) => {
                    const hasTiming = line.start !== null && line.start !== undefined && line.end !== null && line.end !== undefined;
                    const draft = lyricTimingDrafts[line.id];
                    const start = draft?.start ?? line.start ?? 0;
                    const end = draft?.end ?? line.end ?? Math.min(score.song.duration_seconds, start + 0.1);
                    const active = playbackTime >= (line.start ?? Infinity) && playbackTime < (line.end ?? Infinity);
                    return <div key={line.id} className={active ? "lyric-line lyric-line-active" : "lyric-line"}>
                      {editingLyricLineId === line.id ? <input aria-label={`Edit lyric line ${line.order}`} value={editingLyricText} autoFocus onChange={(event) => setEditingLyricText(event.target.value)} onBlur={() => saveLyricText(line.id)} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") setEditingLyricLineId(null); }} /> : <button type="button" onClick={() => line.start !== null && line.start !== undefined && seekTo(line.start)}>{line.text}</button>}
                      <span>{start.toFixed(1)}–{end.toFixed(1)}</span>
                      {line.origin === "alignment" ? <span className="lyric-suggestion" title="Structural timing suggestion; review and edit this line.">Suggested · {Math.round(line.confidence * 100)}%</span> : null}
                      <button type="button" onClick={() => { setEditingLyricLineId(line.id); setEditingLyricText(line.text); }}>Edit text</button>
                      <button type="button" onClick={() => splitLyricLine(line.id)}>Split line</button>
                      <button type="button" disabled={lineIndex + 1 >= (score.lyrics?.lines.length ?? 0)} onClick={() => mergeLyricLineWithNext(line.id)}>Merge next</button>
                      <button type="button" onClick={() => setLyricTiming(line.id, "start")}>Set start</button>
                      <button type="button" onClick={() => setLyricTiming(line.id, "end")}>Set end</button>
                      {hasTiming ? <div className="lyric-timing-editor">
                        <label>Start<input aria-label={`Start timing for lyric line ${line.order}`} type="range" min="0" max={Math.max(0, end - 0.01)} step="0.01" value={start} onChange={(event) => updateLyricTimingDraft(line.id, "start", Number(event.target.value), start, end)} onPointerUp={() => commitLyricTiming(line.id, start, end)} onBlur={() => draft && commitLyricTiming(line.id, start, end)} /></label>
                        <label>End<input aria-label={`End timing for lyric line ${line.order}`} type="range" min={Math.min(score.song.duration_seconds, start + 0.01)} max={score.song.duration_seconds} step="0.01" value={end} onChange={(event) => updateLyricTimingDraft(line.id, "end", Number(event.target.value), start, end)} onPointerUp={() => commitLyricTiming(line.id, start, end)} onBlur={() => draft && commitLyricTiming(line.id, start, end)} /></label>
                      </div> : <span className="lyric-timing-hint">Set both boundaries, or distribute timing, to drag this line.</span>}
                    </div>;
                  })}</div> : null}
                </details>

                <div className="export-actions">
                  <button type="button" className="ghost-button" onClick={downloadScoreJson}>Download JSON</button>
                  <button type="button" className="ghost-button" disabled={midiPending} onClick={() => void downloadMidi()}>{midiPending ? "Preparing MIDI…" : "Download MIDI"}</button>
                  <span>MIDI 演奏：{chordPerformance === "original" ? "原版" : chordPerformance === "continuous" ? "換和弦即彈・連續刷奏" : "換和弦只彈一下"}；JSON／MusicXML 保留原譜。</span>
                  <button type="button" hidden={!MELODY_ENABLED} className="ghost-button" onClick={() => void downloadMusicXml()}>Download MusicXML</button>
                  <button type="button" className="ghost-button" onClick={() => void downloadChordPro()}>Download ChordPro</button>
                  <button type="button" className="ghost-button" disabled={!score.lyrics} onClick={() => void downloadLrc()}>Download LRC</button>
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
                    <span>Detected key</span>
                    <strong>{score.analysis.key} {score.analysis.mode}</strong>
                  </article>
                  <article className="metric-card">
                    <span>Chord chart</span>
                    <strong>Needs review</strong>
                  </article>
                  <article className="metric-card" hidden={!MELODY_ENABLED}>
                    <span>Melody engine</span>
                    <strong className="metric-engine">{score.provenance.melody_engine.replace(/_/g, " ") || "—"}</strong>
                  </article>
                  <article className="metric-card" hidden={!MELODY_ENABLED}>
                    <span>Melody status</span>
                    <strong>Experimental</strong>
                  </article>
                </div>

                <section className="rhythm-panel">
                  {score.analysis.time_signature === "4/4" ? <button type="button" className="ghost-button" disabled={!rhythmOptions.some((pattern) => pattern.pattern_id === "metered_4_4_8th")}
                    onClick={() => { const pattern = rhythmOptions.find((item) => item.pattern_id === "metered_4_4_8th"); if (pattern) recordScoreChange({ ...score, rhythm: pattern }); }}>套用四小節試聽的 4/4 刷奏</button> : null}
                  <div><h3>Rhythm suggestion</h3><p>{score.rhythm.label || "Suggested strumming pattern"} · {score.rhythm.subdivision}th-note grid</p></div>
                  <label className="rhythm-selector">Pattern<select aria-label="Rhythm pattern" value={score.rhythm.pattern_id} onChange={(event) => { const selected = [...rhythmOptions, score.rhythm].find((pattern) => pattern.pattern_id === event.target.value); if (selected && selected.pattern_id !== score.rhythm.pattern_id) recordScoreChange({ ...score, rhythm: selected }); }}><option value={score.rhythm.pattern_id}>{score.rhythm.label || score.rhythm.pattern_id || "Current pattern"}</option>{rhythmOptions.filter((pattern) => pattern.pattern_id !== score.rhythm.pattern_id).map((pattern) => <option key={pattern.pattern_id} value={pattern.pattern_id}>{pattern.label}</option>)}</select></label>
                  <div className="rhythm-steps">{score.rhythm.display.map((stroke, index) => <span key={index} title={stroke === "A" ? "Arpeggio" : undefined} className={stroke ? "rhythm-step rhythm-step-active" : "rhythm-step"}>{stroke === "A" ? "⌁" : stroke ?? "·"}</span>)}</div>
                </section>

                </div>
                {!MELODY_ENABLED && !focusMode ? <AccompanimentCandidate score={score} jobId={workingJobId} apiBase={API_BASE}
                  onCommit={(base, next) => { if (scoreRef.current !== base) return false; stopSynth(false); return recordScoreChange(next); }} /> : null}
                {MELODY_ENABLED ? <div hidden={accompanimentView && focusMode}>
                {score.provenance.parameters?.melody_note_processing !== "bounded-source-v1" ? <p role="note">目前為原分析／其他音符版本，尚未套用 G。若要使用 G，請展開下方候選入口，先產生、再確認套用；不會自動替換旋律。</p> : null}
                <ContourCandidate score={score} jobId={workingJobId} apiBase={API_BASE}
                  onCommit={(base, next) => { if (scoreRef.current !== base) return false; audioRef.current?.pause(); stopSynth(false); return recordScoreChange(next); }} />
                <AccompanimentCandidate score={score} jobId={workingJobId} apiBase={API_BASE}
                  onCommit={(base, next) => { if (scoreRef.current !== base) return false; audioRef.current?.pause(); stopSynth(false); return recordScoreChange(next); }} />
                <MelodyEditor score={score} jobId={workingJobId} playhead={playbackTime} apiBase={API_BASE}
                  focused={focusMode} sourceAvailable={!!audioUrl} sourceTrack={diagnosticAudioTrack}
                  melodyConnection={melodyConnection} onMelodyConnection={value => { stopSynth(false); setMelodyConnection(value); }}
                  playbackRate={playbackRate} onSpeed={setSpeed}
                  sourceTracks={analysisJob?.artifacts ?? []} onSourceTrack={track => selectDiagnosticAudioTrack(track as DiagnosticAudioTrack)}
                  playbackStatus={isSourcePreparing ? "載入來源中" : isSynthPreparing ? "準備合奏中" : isSynthPlaying ? "播放工作譜" : isPlaying ? "播放來源音訊" : "已暫停"}
                  onCommit={(base, next) => { if (scoreRef.current !== base) return false; return recordScoreChange(next); }}
                  onSeek={seekTo} onPitch={(midi) => void auditionEditedNotes([{ midi, start: 0, end: 0.6 }])}
                  onAudition={(start, end, loop, from) => { const range = clipRange(start, end, score); if (range.end <= range.start) return; void auditionEditedNotes(score.melody.filter((note) => note.end > range.start && note.start < range.end).map((note) => ({ midi: note.midi, start: Math.max(0, note.start - range.start), end: Math.min(range.end, note.end) - range.start })), { ...range, loop, from }); }}
                  onOriginal={(start, end) => void auditionSourceSegment(start, end)}
                  onEnsemble={(start, end, loop, from) => void toggleSynthPlayback({ start, end, loop, from })}
                  onGuitar={(start, end, loop, from) => void toggleSynthPlayback({ start, end, loop, from, guitarOnly: true })}
                  onListenOriginal={(start, end) => {
                    if (diagnosticAudioTrack === "source") { void auditionSourceSegment(start, end); return; }
                    if (!analysisJob || analysisJob.status !== "completed" || sourceJobId(score) !== analysisJob.id) {
                      setError("目前無法切回原曲來源。"); return;
                    }
                    selectDiagnosticAudioTrack("source");
                    const generation = synthGenerationRef.current;
                    window.requestAnimationFrame(() => {
                      if (generation !== synthGenerationRef.current) return;
                      const expected = `${API_BASE}/api/v1/jobs/${analysisJob.id}/audio`;
                      if (audioRef.current?.getAttribute("src") === expected) void auditionSourceSegment(start, end);
                    });
                  }}
                  onStop={() => { audioRef.current?.pause(); stopSynth(false); }} onUndo={undoScoreChange} onRedo={redoScoreChange}
                  canUndo={undoHistory.length > 0} canRedo={redoHistory.length > 0}
                  revisionId={revisionId} onRevisionId={setRevisionId} onSave={() => void saveRevision(true)} onLoad={() => void loadRevision()}
                  saving={isSavingRevision || isLoadingRevision} saveStatus={saveStatus} />
                </div> : null}

                <div hidden={focusMode || score.analysis.timing_status === "unmetered"} className="advanced-workspace">
                {MELODY_ENABLED ? <>{score.melody.length > 0 ? <details className="melody-workspace workspace-disclosure">
                <summary>Melody &amp; Tab previews · Experimental</summary>
                <section className="melody-panel">
                  <div><h3>Estimated melody timeline</h3><p>Click a note to seek. Check Analysis notes above for transcription limitations.</p></div><button type="button" className="ghost-button melody-simplify" onClick={() => void simplifyMelody()}>Simplify melody</button>
                  <div className="melody-timeline" aria-label="Detected melody notes">{score.melody.filter((note) => note.end > bounds.start && note.start < bounds.end).map((note) => { const showLabel = melodyTimelineLabelIds.has(note.id); return <button key={note.id} type="button" aria-label={`${note.note} at ${note.start.toFixed(2)} seconds`} className={`melody-note ${showLabel ? "melody-note-label" : "melody-note-dot"}${activeMelodyNoteId === note.id ? " melody-note-active" : ""}`} title={note.note + " · " + note.start.toFixed(2) + "s"} onClick={() => seekTo(note.start)} style={{ left: String((Math.max(0, note.start - bounds.start) / Math.max(bounds.end - bounds.start, .01)) * 100) + "%", bottom: String(Math.max(0, Math.min(85, (note.midi - 40) * 1.8))) + "%" }}>{showLabel ? note.note : "•"}</button>; })}</div>
                </section>

                <section className="score-preview-panel">
                  <div><h3>Estimated score preview</h3><p>A simplified pitch view, not a verified transcription. Click a note to seek.</p></div>
                  <div className="score-measures" aria-label="Melody score preview">
                    {(scoreMeasures.length ? scoreMeasures : [1]).map((measure) => {
                      const measureStart = measureGroups.find((group) => group.measure === measure)?.start ?? bounds.start;
                      const measureEnd = measureGroups.find((group) => group.measure === measure)?.end ?? bounds.end;
                      const measureDuration = Math.max(measureEnd - measureStart, 0.01);
                      const measureNotes = score.melody.filter((note) => note.end > measureStart && note.start < measureEnd);
                      const labelStride = Math.max(1, Math.ceil(measureNotes.length / 8));
                      return <div className="score-measure" key={measure}><span className="score-measure-label">Bar {measure}</span><div className="score-staff">{measureNotes.map((note, index) => <button key={note.id} type="button" className="score-note" aria-label={note.note + " in bar " + measure} title={note.note + " · " + (note.end - note.start).toFixed(2) + "s"} onClick={() => seekTo(note.start)} style={{ left: String(Math.min(96, Math.max(2, ((note.start - measureStart) / measureDuration) * 100))) + "%", bottom: String(Math.min(94, Math.max(2, ((note.midi - 52) / 24) * 100))) + "%" }}><span>●</span>{index % labelStride === 0 || note.id === activeMelodyNoteId ? <small>{note.note}</small> : null}</button>)}</div></div>;
                    })}
                  </div>
                </section>

                {score.song_range ? <p>完整 MusicXML 預覽未裁切；取消歌曲範圍可查看。有效範圍請使用旋律編輯器。</p> : <Suspense fallback={<section className="alphatab-panel"><p>Loading notation preview…</p></section>}><AlphaTabScore score={score} /></Suspense>}

                <section className="tab-panel">
                  <div><h3>Playable Tab {activeMeasureGroup ? "· Bar " + activeMeasureGroup.measure : ""}</h3><p>Read left to right. Each horizontal line is a string; a number tells you which fret to press. The amber number is playing now.</p></div>
                  {activeMeasureGroup ? <div className="tab-staff" aria-label={"Six-string tab for bar " + activeMeasureGroup.measure}>
                    {["e", "B", "G", "D", "A", "E"].map((label, index) => <span key={label + index} className="tab-string-label" style={{ top: String((index + 0.5) * (100 / 6)) + "%" }}>{label}<small>{index + 1}</small></span>)}
                    {score.beats.filter((beat) => beat.measure === activeMeasureGroup.measure).map((beat) => <span key={"tab-beat-" + beat.time} className="tab-beat-guide" style={{ left: String(5 + ((beat.time - activeMeasureGroup.start) / Math.max(activeMeasureGroup.end - activeMeasureGroup.start, 0.01)) * 92) + "%" }}><small>{beat.beat}</small></span>)}
                    {activeMeasureNotes.map((note) => <button key={note.id} type="button" className={"tab-marker" + (activeMelodyNoteId === note.id ? " tab-marker-active" : "")} title={note.note + " · String " + note.string + " · Fret " + note.fret} onClick={() => seekTo(note.start)} style={{ left: String(5 + ((note.start - activeMeasureGroup.start) / Math.max(activeMeasureGroup.end - activeMeasureGroup.start, 0.01)) * 92) + "%", top: String(((note.string ?? 1) - 0.5) * (100 / 6)) + "%" }}>{note.fret}</button>)}
                  </div> : null}
                  {activeMeasureGroup && !activeMeasureNotes.length ? <p className="tab-empty">No playable melody note is mapped in this bar.</p> : null}
                </section>
                </details> : <section className="melody-empty" aria-live="polite"><h3>No melody notes in working score</h3><p>Use Melody editor to add missing notes. The original analysis and contour audio remain separate; adding notes enables melody notation and exports without rerunning analysis.</p></section>}</> : null}

                <label><input type="checkbox" checked={showRawChordSegments} onChange={(event) => setShowRawChordSegments(event.target.checked)} />顯示原始分析區段（逐段編輯）</label>
                <p>和弦寬度依拍長排列：兩和弦不一定各半小節。相鄰同和弦／指型合併顯示；刷奏型不會自動校正小節線。</p>
                <p>{score.provenance.parameters?.chord_grid_candidate
                  ? "目前伴奏是八分拍格候選：依現有拍點整理成整拍或半拍位置，旋律未改。片段首尾可能是不完整小節。"
                  : "這裡依工作譜的實際時間繪製；尚未整理的辨識時間可能帶有零碎拍長，片段首尾也可能不滿小節。"}</p>
                {score.analysis.warnings.filter((warning) => /downbeat|first detected pulse/i.test(warning)).length ? <p role="note">小節起點尚未確認：分析以第一個偵測拍點作為第 1 拍，Bar 可能未對準原曲。</p> : null}
                <div className="chord-sheet">
                  {measureGroups.map((group) => (
                    <div key={"measure-" + group.measure} className="measure-card" data-measure={group.measure}>
                      <div className="measure-header">Bar {group.measure}</div>
                      <div className="measure-beat-ruler" aria-label={"Bar " + group.measure + " beat positions"}>
                        {group.layout.ticks.map((tick) => <span key={tick.beat} className={score.beats[activeBeatIndex]?.measure === group.measure && score.beats[activeBeatIndex]?.beat === tick.beat ? "measure-beat-active" : undefined} style={{ left: `${tick.fraction * 100}%` }}>{tick.beat}</span>)}
                        {!group.layout.ticks.length ? <small>時間比例（無拍點）</small> : null}
                      </div>
                      <div className="measure-chords">
                        {group.spans.map(({ chord, start, end, continues, members }) => chord ? (
                          <button
                            key={chord.id + "-" + group.measure}
                            type="button"
                            style={{ gridColumn: `${1 + Math.round(group.layout.fraction(start) * 1000)} / ${1 + Math.max(Math.round(group.layout.fraction(start) * 1000) + 1, Math.round(group.layout.fraction(end) * 1000))}` }}
                            title={`${chord.symbol} · ${group.layout.length(start, end)} · ${start.toFixed(2)}–${end.toFixed(2)}s${members.length > 1 ? " · 連續和弦：點選編輯第一段；修改其他段請勾選顯示原始分析區段。" : ""}`}
                            className={"chord-block" + (members.some((item) => item.id === selectedChordId) ? " chord-block-selected" : "") + (playbackTime >= start && playbackTime < end ? " chord-block-active" : "")}
                            onClick={() => selectChord(chord, start)}
                          >
                            <span className="chord-symbol">{chord.symbol}</span>
                            <span className="chord-beat-length">{group.layout.length(start, end)}</span>
                            <span className="chord-meta">{start.toFixed(1)}s - {end.toFixed(1)}s</span>
                            {members.length > 1 ? <span className="shape-meta">延續 · {members.length} 個分析區段</span> : null}
                            {chord.roman_numeral ? <span className="shape-meta">{chord.roman_numeral} · {chord.harmonic_function?.replace(/_/g, " ")}</span> : null}
                            <span className="shape-meta">Shape: {chord.shape_symbol ?? chord.symbol}</span>
                            {continues ? <span className="continuation-badge">Continues</span> : null}
                            {members.some((item) => item.needs_review) ? <span className="review-badge" title={members.flatMap((item) => item.review_reasons ?? []).join(", ")}>Review</span> : null}
                            {members.some((item) => item.edited) ? <span className="edit-badge">Edited</span> : null}
                          </button>
                        ) : (
                          <button key={"gap-" + start} type="button" className="chord-block chord-gap"
                            style={{ gridColumn: `${1 + Math.round(group.layout.fraction(start) * 1000)} / ${1 + Math.max(Math.round(group.layout.fraction(start) * 1000) + 1, Math.round(group.layout.fraction(end) * 1000))}` }}
                            aria-label={"No chord assigned from " + start.toFixed(1) + " to " + end.toFixed(1) + " seconds"}
                            title="No chord assigned here. Click to listen and check whether a chord is missing."
                            onClick={() => seekTo(start)}>
                            <span className="chord-symbol">N.C.</span>
                            <span className="chord-beat-length">{group.layout.length(start, end)}</span>
                            <span className="chord-meta">{start.toFixed(1)}s - {end.toFixed(1)}s</span>
                            <span className="shape-meta">No chord assigned</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                </div>
              </>
            ) : (
              <div className="placeholder">
                <p>先選擇音檔或貼上 YouTube 網址，完成分析後會顯示和弦核對頁。</p>
              </div>
            )}
          </div>

          <aside className="panel side-panel" hidden={focusMode || (!MELODY_ENABLED && !selectedChord)}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">和弦編輯</p>
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
                    <button type="button" className="ghost-button" onClick={() => void saveRevision()} disabled={isSavingRevision}>
                      {isSavingRevision ? "Saving..." : "Save revision (new version)"}
                    </button>
                    <button type="button" className="ghost-button" onClick={() => void loadRevision()} disabled={isLoadingRevision}>
                      {isLoadingRevision ? "Loading..." : "Load revision"}
                    </button>
                  </div>
                  <p className="revision-status">{!MELODY_ENABLED && saveStatus === "No saved revision yet." ? "" : !MELODY_ENABLED && saveStatus.startsWith("Saved revision") ? "已保存，可放心離開；下次用目前網址繼續。" : saveStatus}</p>
                </div>
                <label className="field compact-field">
                  <span>Chord symbol</span>
                  <input value={chordDraft} onChange={(event) => setChordDraft(event.target.value)} />
                </label>
                <div className="timing-fields">
                  <label className="field compact-field"><span>Start (seconds)</span><input type="number" min="0" step="0.01" value={chordStartDraft} onChange={(event) => setChordStartDraft(event.target.value)} /></label>
                  <label className="field compact-field"><span>End (seconds)</span><input type="number" min="0" step="0.01" value={chordEndDraft} onChange={(event) => setChordEndDraft(event.target.value)} /></label>
                </div>
                {selectedChordTimingBounds ? <div className="chord-boundary-editor">
                  <p>Drag a boundary to retime this chord without overlapping its neighbors.</p>
                  <label>Start handle<input aria-label="Drag chord start boundary" type="range" min={selectedChordTimingBounds.startMin} max={Math.max(selectedChordTimingBounds.startMin, selectedChordTimingBounds.end - 0.1)} step="0.01" value={selectedChordTimingBounds.start} onChange={(event) => setChordStartDraft(event.target.value)} onPointerUp={saveSelectedChordTiming} /></label>
                  <label>End handle<input aria-label="Drag chord end boundary" type="range" min={Math.min(selectedChordTimingBounds.endMax, selectedChordTimingBounds.start + 0.1)} max={selectedChordTimingBounds.endMax} step="0.01" value={selectedChordTimingBounds.end} onChange={(event) => setChordEndDraft(event.target.value)} onPointerUp={saveSelectedChordTiming} /></label>
                </div> : null}
                <div className="editor-actions">
                  <button type="button" className="ghost-button" onClick={saveSelectedChordTiming}>Save timing</button>
                  <button type="button" className="ghost-button" onClick={addChordAtPlayhead}>Add/change at playhead</button>
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
                  {candidateVoicings && candidateVoicings.length > 0 ? (
                    candidateVoicings.map((voicing) => (
                      <button key={voicing.id} type="button" className="voicing-card" onClick={() => applyVoicing(voicing)}>
                        <ChordDiagram frets={voicing.frets} baseFret={voicing.base_fret} label={voicing.shape_symbol} />
                        <strong>{voicing.shape_symbol}</strong>
                        <span>Frets: {voicing.frets.map((fret) => (fret === null ? "x" : fret)).join(" ")}</span>
                        <span>Position {voicing.base_fret} · Difficulty {voicing.difficulty}/5</span>
                        {selectedChord.voicing_id === voicing.id ? <span className="edit-badge">Selected</span> : null}
                      </button>
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
                <li>點選和弦即可修改名稱、起訖或指型；修改後可還原上一步。</li>
              </ul>
            )}
          </aside>
        </section>
      </main>
    </div>
  );
}
