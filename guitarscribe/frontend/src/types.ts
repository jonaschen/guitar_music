export type AccidentalPreference = "auto" | "sharps" | "flats";

export type SongScore = {
  schema_version: string;
  song: {
    title: string;
    source_type: string;
    source_url?: string | null;
    duration_seconds: number;
  };
  analysis: {
    key: string;
    mode: string;
    bpm: number;
    time_signature: string;
    capo: number;
    confidence: number;
    warnings: string[];
  };
  key_context: {
    source: { key: string; mode: string };
    target: { key: string; mode: string };
    shape: { key: string; mode: string };
    sounding: { key: string; mode: string };
    transpose_semitones: number;
    accidental_preference: AccidentalPreference;
    audio_matches_notation: boolean;
  };
  beats: Array<{
    time: number;
    beat: number;
    measure: number;
    confidence: number;
  }>;
  chords: Array<{
    id: string;
    start: number;
    end: number;
    symbol: string;
    source_symbol?: string | null;
    shape_symbol?: string | null;
    confidence: number;
    origin: string;
    edited: boolean;
    voicing_id?: string | null;
    available_voicings?: Array<{
      id: string;
      symbol: string;
      shape_symbol: string;
      frets: Array<number | null>;
      fingers: Array<number | null>;
      base_fret: number;
      capo: number;
      difficulty: number;
      tags: string[];
    }>;
  }>;
  melody: Array<{
    id: string;
    start: number;
    end: number;
    midi: number;
    note: string;
    confidence: number;
    string?: number | null;
    fret?: number | null;
    origin: string;
    edited: boolean;
  }>;
  rhythm: {
    subdivision: number;
    pattern_id: string;
    display: Array<string | null>;
    confidence: number;
    label: string;
  };
  lyrics?: LyricsTrack | null;
  provenance: {
    beat_engine: string;
    chord_engine: string;
    melody_engine: string;
  };
};

export type JobStatus =
  | "queued"
  | "resolving"
  | "preprocessing"
  | "beat_analysis"
  | "chord_analysis"
  | "melody_analysis"
  | "postprocessing"
  | "completed"
  | "failed"
  | "cancelled";

export interface AnalysisJob {
  id: string;
  status: JobStatus;
  progress: number;
  message: string;
  melody_mode: string;
  chord_complexity: string;
  created_at: string;
  updated_at: string;
  error: string | null;
  score: SongScore | null;
}

export type LyricsTrack = {
  id: string;
  language: string;
  source: string;
  timing_level: string;
  raw_text: string;
  revision: number;
  lines: Array<{ id: string; order: number; start?: number | null; end?: number | null; text: string; confidence: number; origin: string; edited: boolean }>;
};
