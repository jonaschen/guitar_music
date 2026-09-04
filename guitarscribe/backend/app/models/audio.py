from pydantic import BaseModel
from pathlib import Path
from enum import Enum
from typing import Optional

class SourceType(str, Enum):
    LOCAL = "local"
    YOUTUBE = "youtube"

class SourceRequest(BaseModel):
    source_type: SourceType
    path: Optional[Path] = None
    url: Optional[str] = None
    rights_confirmed: bool = False

class AudioAsset(BaseModel):
    path: Path
    source_type: SourceType
    title: str = "Unknown"
    duration_seconds: Optional[float] = None
    original_format: Optional[str] = None

class NormalizedAudio(BaseModel):
    path: Path
    sample_rate: int = 44100
    channels: int = 1
    duration_seconds: float
    bit_depth: int = 16
