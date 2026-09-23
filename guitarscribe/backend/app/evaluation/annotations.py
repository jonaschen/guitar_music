"""Versioned human annotations for GuitarScribe quality gates."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TimePointAnnotation(BaseModel):
    time: float = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0, le=1)


class ChordRegionAnnotation(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str
    acceptable_labels: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("chord region end must be after start")
        return self


class MelodyNoteAnnotation(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    midi: int = Field(ge=0, le=127)

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("melody note end must be after start")
        return self


class SectionAnnotation(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str
    melody_source: Literal["vocal", "instrument", "none", "unknown"] = "unknown"

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("section end must be after start")
        return self


class QualityAnnotation(BaseModel):
    """A legal 30–60 second reference excerpt and its musical ground truth."""

    schema_version: Literal["1.0"] = "1.0"
    recording_id: str = Field(min_length=1)
    evaluation_tier: Literal["smoke", "quality_gate"] = "smoke"
    annotation_status: Literal["draft", "reviewed"] = "draft"
    reviewed_by: str | None = Field(default=None, min_length=1)
    source_file: str | None = None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_note: str = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    excerpt_start: float = Field(ge=0)
    excerpt_end: float = Field(gt=0)
    tempo_bpm: float | None = Field(default=None, gt=0)
    meter: str = "4/4"
    beats: list[TimePointAnnotation] = Field(default_factory=list)
    downbeats: list[TimePointAnnotation] = Field(default_factory=list)
    chords: list[ChordRegionAnnotation] = Field(default_factory=list)
    sections: list[SectionAnnotation] = Field(default_factory=list)
    melody: list[MelodyNoteAnnotation] = Field(default_factory=list)
    listening_notes: list[str] = Field(default_factory=list)
    error_tags: list[Literal[
        "timing_grid", "wrong_chord", "over_segmentation", "missing_beat",
        "octave", "accompaniment_leak", "melody_rhythm", "should_be_silence",
    ]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_excerpt(self):
        if self.excerpt_end <= self.excerpt_start:
            raise ValueError("excerpt end must be after start")
        duration = self.excerpt_end - self.excerpt_start
        if self.evaluation_tier == "quality_gate" and not 30 <= duration <= 60:
            raise ValueError("quality-gate excerpts must be 30 to 60 seconds")
        if self.evaluation_tier == "quality_gate" and not self.source_file:
            raise ValueError("quality-gate excerpts require source_file")
        return self
