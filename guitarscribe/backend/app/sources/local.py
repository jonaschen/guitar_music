import os
from pathlib import Path
from ..models.audio import SourceRequest, AudioAsset, SourceType
import soundfile as sf
import logging

logger = logging.getLogger(__name__)

class LocalAudioSource:
    async def fetch(self, request: SourceRequest) -> AudioAsset:
        if not request.path:
            raise ValueError("Path is required for local source")
        
        path = Path(request.path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        valid_extensions = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(f"Invalid audio extension: {path.suffix}")
            
        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > 200:
            raise ValueError(f"File too large: {file_size_mb:.2f}MB (max 200MB)")
            
        if not request.rights_confirmed:
            raise ValueError("Rights must be confirmed")

        duration = None
        try:
            if path.suffix.lower() == ".wav":
                info = sf.info(str(path))
                duration = info.duration
        except Exception as e:
            logger.warning(f"Could not read duration for {path}: {e}")

        return AudioAsset(
            path=path,
            source_type=SourceType.LOCAL,
            title=path.stem,
            duration_seconds=duration,
            original_format=path.suffix.lower()[1:]
        )
