from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from .analysis import AccidentalPreference, BeatInfo, ChordEvent, MelodyNote, RhythmSuggestion
from .lyrics import LyricsTrack

class SongInfo(BaseModel):
    title: str = "Unknown"
    source_type: str = "local"
    source_url: Optional[str] = None
    duration_seconds: float = 0.0
    source_start_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)

class AnalysisSummary(BaseModel):
    key: str = "C"
    mode: str = "major"
    bpm: float = 120.0
    time_signature: str = "4/4"
    capo: int = 0
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)

class KeySignature(BaseModel):
    key: str = "C"
    mode: str = "major"

class KeyContext(BaseModel):
    source: KeySignature = Field(default_factory=KeySignature)
    target: KeySignature = Field(default_factory=KeySignature)
    shape: KeySignature = Field(default_factory=KeySignature)
    sounding: KeySignature = Field(default_factory=KeySignature)
    transpose_semitones: int = 0
    accidental_preference: AccidentalPreference = AccidentalPreference.AUTO
    audio_matches_notation: bool = True

class GuitarSettings(BaseModel):
    tuning: list[int] = Field(default_factory=lambda: [40, 45, 50, 55, 59, 64])
    tuning_name: str = "EADGBE"
    capo: int = Field(default=0, ge=0, le=12)
    max_capo: int = Field(default=8, ge=0, le=12)
    max_fret: int = Field(default=15, ge=1, le=24)
    handedness: str = "right"
    difficulty: str = "beginner"
    tab_preference: str = "balanced"

class Provenance(BaseModel):
    beat_engine: str = ""
    chord_engine: str = ""
    melody_engine: str = ""
    beat_engine_version: str = ""
    chord_engine_version: str = ""
    melody_engine_version: str = ""
    tempo_map_version: str = "legacy-beat-grid-v1"
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)

class MelodyEditRecord(BaseModel):
    id: str
    operation: str
    created_at: str
    source_job_id: str | None = None
    intent: Literal["unclassified"] = "unclassified"
    transpose_semitones: int = 0
    before: list[MelodyNote] = Field(default_factory=list)
    after: list[MelodyNote] = Field(default_factory=list)


class SongRange(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class SongScore(BaseModel):
    schema_version: str = "1.0"
    song: SongInfo = Field(default_factory=SongInfo)
    analysis: AnalysisSummary = Field(default_factory=AnalysisSummary)
    key_context: KeyContext = Field(default_factory=KeyContext)
    beats: list[BeatInfo] = Field(default_factory=list)
    chords: list[ChordEvent] = Field(default_factory=list)
    melody: list[MelodyNote] = Field(default_factory=list)
    melody_edits: list[MelodyEditRecord] = Field(default_factory=list)
    rhythm: RhythmSuggestion = Field(default_factory=RhythmSuggestion)
    guitar: GuitarSettings = Field(default_factory=GuitarSettings)
    provenance: Provenance = Field(default_factory=Provenance)
    lyrics: LyricsTrack | None = None
    song_range: SongRange | None = None

    @model_validator(mode="after")
    def validate_song_range(self):
        if self.song_range and not 0 <= self.song_range.start < self.song_range.end <= self.song.duration_seconds:
            raise ValueError("Song range must stay within the source duration and have positive length")
        return self
