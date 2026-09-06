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
            job_ttl_seconds=int(os.environ.get("GUITARSCRIBE_JOB_TTL_SECONDS", str(24 * 60 * 60))),
            work_dir=Path(os.environ.get("GUITARSCRIBE_WORK_DIR", "/tmp/guitarscribe")),
            chord_engine=ChordEngine(os.environ.get("GUITARSCRIBE_CHORD_ENGINE", "auto")),
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
