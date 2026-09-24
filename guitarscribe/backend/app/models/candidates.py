"""Canonical raw analyzer outputs used for engine bake-offs.

Third-party adapters emit these models before any result is projected into a
SongScore.  This keeps raw evidence versioned and prevents an engine-specific
schema from becoming the product's source of truth.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .analysis import ChordLabelCandidate


class AnalyzerRun(BaseModel):
    engine: str = Field(min_length=1)
    engine_version: str = "unknown"
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)
    raw_artifact: str | None = None


class TimingCandidate(BaseModel):
    bpm: float = Field(gt=0)
    meter: str = "4/4"
    phase: int = Field(default=0, ge=0)
    beats: list[float] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)


class TimingResult(BaseModel):
    run: AnalyzerRun
    candidates: list[TimingCandidate] = Field(default_factory=list)


class ChordCandidateRegion(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str
    confidence: float = Field(default=0, ge=0, le=1)
    label_candidates: list[ChordLabelCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("chord candidate end must be after start")
        return self


class ChordResult(BaseModel):
    run: AnalyzerRun
    vocabulary: str = "majmin-nc"
    regions: list[ChordCandidateRegion] = Field(default_factory=list)
    key: str = "C"
    mode: str = "major"
    confidence: float = Field(default=0, ge=0, le=1)


class MelodyCandidateNote(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    midi: float = Field(ge=0, le=127)
    confidence: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("melody candidate end must be after start")
        return self


class MelodyCandidateResult(BaseModel):
    run: AnalyzerRun
    source: Literal["vocal", "instrument", "full_mix", "unknown"] = "unknown"
    notes: list[MelodyCandidateNote] = Field(default_factory=list)
