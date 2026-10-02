"""Create a zero-based analysis copy without modifying the uploaded source."""
import asyncio
from pathlib import Path

import soundfile as sf

from ..analyzers.preprocessor import FFmpegPreprocessor
from ..core.config import Settings


async def crop_analysis_audio(source: Path, target: Path, start: float) -> Path:
    binary = FFmpegPreprocessor(ffmpeg_binary=Settings.from_env().ffmpeg_binary)._resolve_ffmpeg()
    process = await asyncio.create_subprocess_exec(
        binary, "-nostdin", "-y", "-i", str(source), "-ss", str(start),
        "-vn", "-c:a", "pcm_s16le", str(target),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        if isinstance(exc, asyncio.TimeoutError):
            raise ValueError("Preparing the analysis start timed out after 120 seconds.") from exc
        raise
    if process.returncode:
        raise ValueError("Could not prepare analysis start: " + stderr.decode(errors="replace")[-500:])
    if sf.info(str(target)).frames == 0:
        raise ValueError("Analysis start must be before the end of the audio; choose a smaller skip time.")
    return target
