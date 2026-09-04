import subprocess
import tempfile
import soundfile as sf
from pathlib import Path
import logging
from ..models.audio import AudioAsset, NormalizedAudio

logger = logging.getLogger(__name__)

class FFmpegPreprocessor:
    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    async def normalize(self, asset: AudioAsset) -> NormalizedAudio:
        work_dir = Path(tempfile.mkdtemp(prefix="guitarscribe_"))
        output_path = work_dir / "normalized.wav"
        
        cmd = [
            "ffmpeg", "-y", "-i", str(asset.path),
            "-ar", "44100", "-ac", "1",
            "-sample_fmt", "s16", "-f", "wav",
            str(output_path)
        ]
        
        try:
            logger.info(f"Running ffmpeg on {asset.path}")
            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr.decode()}")
                
            if not output_path.exists():
                raise RuntimeError("FFmpeg did not produce output file")
                
            info = sf.info(str(output_path))
            return NormalizedAudio(
                path=output_path,
                sample_rate=44100,
                channels=1,
                duration_seconds=info.duration,
                bit_depth=16
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FFmpeg timed out after {self.timeout}s")
        except Exception as e:
            raise RuntimeError(f"Normalization failed: {e}")
