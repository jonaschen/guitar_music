import subprocess
import tempfile
import shutil
import soundfile as sf
from pathlib import Path
import logging
from ..models.audio import AudioAsset, NormalizedAudio
from ..models.analysis import MelodyMode

logger = logging.getLogger(__name__)

class FFmpegPreprocessor:
    def __init__(self, timeout: int = 120, ffmpeg_binary: str | None = None):
        self.timeout = timeout
        self.ffmpeg_binary = ffmpeg_binary

    async def normalize(self, asset: AudioAsset) -> NormalizedAudio:
        work_dir = Path(tempfile.mkdtemp(prefix="guitarscribe_"))
        output_path = work_dir / "normalized.wav"
        ffmpeg_executable = self._resolve_ffmpeg()
        
        cmd = [
            ffmpeg_executable, "-y", "-i", str(asset.path),
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

    def _resolve_ffmpeg(self) -> str:
        if self.ffmpeg_binary:
            return self.ffmpeg_binary

        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise RuntimeError(
                "ffmpeg is not available. Set GUITARSCRIBE_FFMPEG_BINARY or install imageio-ffmpeg."
            ) from exc


class DemucsMelodySeparator:
    """Optional vocal isolation adapter; Demucs is deliberately not in the base image."""

    def __init__(self, binary: str | None = None, model: str = "htdemucs", timeout: int = 900):
        self.binary = binary
        self.model = model
        self.timeout = timeout

    async def separate(self, audio: NormalizedAudio, mode: MelodyMode) -> tuple[NormalizedAudio, bool]:
        if mode != MelodyMode.VOCAL:
            return audio, False

        executable = self.binary or shutil.which("demucs")
        if not executable:
            raise RuntimeError("Demucs is enabled but its executable is not installed")

        output_dir = Path(tempfile.mkdtemp(prefix="guitarscribe_stems_"))
        cmd = [
            executable, "--two-stems", "vocals", "-n", self.model,
            "--out", str(output_dir), str(audio.path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Demucs timed out after {self.timeout}s") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"Demucs failed: {stderr[-500:]}")

        stems = list(output_dir.rglob("vocals.wav"))
        if len(stems) != 1:
            raise RuntimeError("Demucs did not produce exactly one vocals.wav stem")
        info = sf.info(str(stems[0]))
        return NormalizedAudio(
            path=stems[0], sample_rate=info.samplerate, channels=info.channels,
            duration_seconds=info.duration, bit_depth=audio.bit_depth,
        ), True
