from enum import Enum

from pydantic import BaseModel, Field

from .score import SongScore


class JobStatus(str, Enum):
    QUEUED = "queued"
    RESOLVING = "resolving"
    PREPROCESSING = "preprocessing"
    BEAT_ANALYSIS = "beat_analysis"
    CHORD_ANALYSIS = "chord_analysis"
    MELODY_ANALYSIS = "melody_analysis"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_JOB_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.RESOLVING,
    JobStatus.PREPROCESSING,
    JobStatus.BEAT_ANALYSIS,
    JobStatus.CHORD_ANALYSIS,
    JobStatus.MELODY_ANALYSIS,
    JobStatus.POSTPROCESSING,
}


class AnalysisJob(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = Field(default=0, ge=0, le=100)
    message: str = "Queued for analysis"
    melody_mode: str = "vocal"
    chord_complexity: str = "standard"
    created_at: str
    updated_at: str
    error: str | None = None
    score: SongScore | None = None
