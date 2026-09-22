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
    max_concurrent_jobs: int = Field(default=1, ge=1)
    max_queued_jobs: int = Field(default=3, ge=0)
    job_ttl_seconds: int = 24 * 60 * 60
    work_dir: Path = Path("/tmp/guitarscribe")
    chord_engine: ChordEngine = ChordEngine.AUTO
    chord_change_threshold: float = Field(default=0.12, ge=0, le=2)
    chord_no_chord_threshold: float = Field(default=0.18, ge=0, le=1)
    chord_base_change_penalty: float = Field(default=0.04, ge=0, le=1)
    chord_short_event_change_penalty: float = Field(default=0.05, ge=0, le=1)
    chord_circle_fifths_bonus: float = Field(default=0.015, ge=0, le=1)
    chord_tonal_prior_scale: float = Field(default=1.0, ge=0, le=4)
    melody_engine: str = "basic_pitch"
    melody_separator: str = "off"
    demucs_binary: Optional[str] = None
    youtube_enabled: bool = False
    youtube_dl_binary: str = "yt-dlp"
    youtube_download_timeout_seconds: int = 600
    submission_rate_limit: int = 5
    submission_rate_window_seconds: int = 3600
    rhythm_patterns_dir: Path = Path("/app/rhythm-patterns")
    ffmpeg_binary: Optional[str] = None
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            max_duration_seconds=int(os.environ.get("GUITARSCRIBE_MAX_DURATION_SECONDS", "600")),
            max_upload_bytes=int(os.environ.get("GUITARSCRIBE_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            max_concurrent_jobs=int(os.environ.get("GUITARSCRIBE_MAX_CONCURRENT_JOBS", "1")),
            max_queued_jobs=int(os.environ.get("GUITARSCRIBE_MAX_QUEUED_JOBS", "3")),
            job_ttl_seconds=int(os.environ.get("GUITARSCRIBE_JOB_TTL_SECONDS", str(24 * 60 * 60))),
            work_dir=Path(os.environ.get("GUITARSCRIBE_WORK_DIR", "/tmp/guitarscribe")),
            chord_engine=ChordEngine(os.environ.get("GUITARSCRIBE_CHORD_ENGINE", "auto")),
            chord_change_threshold=float(os.environ.get("GUITARSCRIBE_CHORD_CHANGE_THRESHOLD", "0.12")),
            chord_no_chord_threshold=float(os.environ.get("GUITARSCRIBE_CHORD_NO_CHORD_THRESHOLD", "0.18")),
            chord_base_change_penalty=float(os.environ.get("GUITARSCRIBE_CHORD_BASE_CHANGE_PENALTY", "0.04")),
            chord_short_event_change_penalty=float(os.environ.get("GUITARSCRIBE_CHORD_SHORT_EVENT_CHANGE_PENALTY", "0.05")),
            chord_circle_fifths_bonus=float(os.environ.get("GUITARSCRIBE_CHORD_CIRCLE_FIFTHS_BONUS", "0.015")),
            chord_tonal_prior_scale=float(os.environ.get("GUITARSCRIBE_CHORD_TONAL_PRIOR_SCALE", "1.0")),
            melody_engine=os.environ.get("GUITARSCRIBE_MELODY_ENGINE", "basic_pitch"),
            melody_separator=os.environ.get("GUITARSCRIBE_MELODY_SEPARATOR", "off"),
            demucs_binary=os.environ.get("GUITARSCRIBE_DEMUCS_BINARY"),
            youtube_enabled=os.environ.get("GUITARSCRIBE_YOUTUBE_ENABLED", "false").lower() == "true",
            youtube_dl_binary=os.environ.get("GUITARSCRIBE_YTDLP_BINARY", "yt-dlp"),
            youtube_download_timeout_seconds=int(os.environ.get("GUITARSCRIBE_YOUTUBE_DOWNLOAD_TIMEOUT_SECONDS", "600")),
            submission_rate_limit=int(os.environ.get("GUITARSCRIBE_SUBMISSION_RATE_LIMIT", "5")),
            submission_rate_window_seconds=int(os.environ.get("GUITARSCRIBE_SUBMISSION_RATE_WINDOW_SECONDS", "3600")),
            ffmpeg_binary=os.environ.get("GUITARSCRIBE_FFMPEG_BINARY"),
            log_level=os.environ.get("GUITARSCRIBE_LOG_LEVEL", "INFO"),
        )
