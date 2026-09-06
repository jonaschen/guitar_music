from pydantic import BaseModel, Field
from pathlib import Path
from enum import Enum
from typing import Optional
import os

class ChordEngine(str, Enum):
    AUTO = "auto"
    CHORDINO = "chordino"
    CHROMAGRAM = "chromagram"

class Settings(BaseModel):
    max_duration_seconds: int = 600
    max_upload_bytes: int = 100 * 1024 * 1024
    max_concurrent_jobs: int = 1
    job_ttl_seconds: int = 24 * 60 * 60
    work_dir: Path = Path("/tmp/guitarscribe")
    chord_engine: ChordEngine = ChordEngine.AUTO
    melody_engine: str = "basic_pitch"
    melody_separator: str = "off"
    demucs_binary: Optional[str] = None
    rhythm_patterns_dir: Path = Path("/app/rhythm-patterns")
    ffmpeg_binary: Optional[str] = None
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_duration_seconds=int(os.environ.get("GUITARSCRIBE_MAX_DURATION_SECONDS", "600")),
            max_upload_bytes=int(os.environ.get("GUITARSCRIBE_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            max_concurrent_jobs=int(os.environ.get("GUITARSCRIBE_MAX_CONCURRENT_JOBS", "1")),
            job_ttl_seconds=int(os.environ.get("GUITARSCRIBE_JOB_TTL_SECONDS", str(24 * 60 * 60))),
            work_dir=Path(os.environ.get("GUITARSCRIBE_WORK_DIR", "/tmp/guitarscribe")),
            chord_engine=ChordEngine(os.environ.get("GUITARSCRIBE_CHORD_ENGINE", "auto")),
            melody_engine=os.environ.get("GUITARSCRIBE_MELODY_ENGINE", "basic_pitch"),
            melody_separator=os.environ.get("GUITARSCRIBE_MELODY_SEPARATOR", "off"),
            demucs_binary=os.environ.get("GUITARSCRIBE_DEMUCS_BINARY"),
            ffmpeg_binary=os.environ.get("GUITARSCRIBE_FFMPEG_BINARY"),
            log_level=os.environ.get("GUITARSCRIBE_LOG_LEVEL", "INFO"),
        )
