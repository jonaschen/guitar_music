from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class MelodyMode(str, Enum):
    VOCAL = "vocal"
    GUITAR = "guitar"
    MIX = "mix"

class ChordComplexity(str, Enum):
    SIMPLE = "simple"
    STANDARD = "standard"
    FULL = "full"

class BeatInfo(BaseModel):
    time: float
    beat: int
    measure: int
    confidence: float = 1.0

class BeatAnalysis(BaseModel):
    bpm: float
    bpm_candidates: list[float] = Field(default_factory=list)
    time_signature: str = "4/4"
    beats: list[BeatInfo] = Field(default_factory=list)
    downbeat_indices: list[int] = Field(default_factory=list)
    confidence: float = 0.0
    engine: str = ""
    engine_version: str = ""
    warnings: list[str] = Field(default_factory=list)

class ChordEvent(BaseModel):
    id: str
    start: float
    end: float
    symbol: str
    confidence: float = 0.0
    origin: str = "model"
    edited: bool = False

class ChordAnalysis(BaseModel):
    chords: list[ChordEvent] = Field(default_factory=list)
    key: str = "C"
    mode: str = "major"
    confidence: float = 0.0
    engine: str = ""
    engine_version: str = ""
    warnings: list[str] = Field(default_factory=list)

class MelodyNote(BaseModel):
    id: str
    start: float
    end: float
    midi: int
    note: str
    confidence: float = 0.0
    string: Optional[int] = None
    fret: Optional[int] = None
    origin: str = "model"
    edited: bool = False

class MelodyAnalysis(BaseModel):
    notes: list[MelodyNote] = Field(default_factory=list)
    mode: MelodyMode = MelodyMode.VOCAL
    confidence: float = 0.0
    engine: str = ""
    engine_version: str = ""
    warnings: list[str] = Field(default_factory=list)

class RhythmSuggestion(BaseModel):
    subdivision: int = 8
    pattern_id: str = ""
    display: list[Optional[str]] = Field(default_factory=list)
    confidence: float = 0.0
    label: str = "建議刷奏"

class AudioFeatures(BaseModel):
    onset_strength_mean: float = 0.0
    onset_strength_std: float = 0.0
    spectral_centroid_mean: float = 0.0
    rms_mean: float = 0.0
