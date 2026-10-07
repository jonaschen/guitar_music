import type { AnalysisJob, SongScore } from "./types";

export function melodyVersion(score: SongScore): string {
  const processing = score.provenance.parameters?.melody_note_processing;
  const label = processing === "bounded-source-v1" ? "Contour G 候選"
    : processing === "source-timed-semitone-v2" ? "原分析音符（非 G 候選）"
    : "其他／較早音符版本（未標記 G）";
  return label + (score.melody_edits?.length || score.melody.some(note => note.edited) ? "＋人工修改" : "");
}

export function sourceJobId(score: SongScore): string | undefined {
  const candidate = score.provenance.parameters?.candidate_source_job_id ?? score.provenance.parameters?.analysis_source_job_id;
  return typeof candidate === "string" && candidate.trim() ? candidate
    : score.melody_edits?.find(edit => edit.source_job_id)?.source_job_id ?? undefined;
}

export function scoreFromJob(job: AnalysisJob): SongScore {
  const score = job.score!;
  return { ...score, provenance: { ...score.provenance,
    parameters: { ...score.provenance.parameters, analysis_source_job_id: job.id } } };
}

export type SavedVersion = { id: string; label: string; jobId?: string };
export function readSavedVersion(): SavedVersion | null {
  try {
    const value = JSON.parse(localStorage.getItem("guitarscribe.savedVersion") ?? "null");
    return value && typeof value.id === "string" && typeof value.label === "string" ? value : null;
  } catch { return null; }
}
