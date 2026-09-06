"""Restricted YouTube audio resolver for user-authorized analysis jobs."""

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def validate_youtube_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in _YOUTUBE_HOSTS:
        raise ValueError("Only HTTPS youtube.com or youtu.be URLs are supported")
    if not parsed.path or parsed.path == "/":
        raise ValueError("A specific YouTube video URL is required")
    return value


class YouTubeAudioDownloader:
    """Invoke yt-dlp without a shell and leave one WAV inside the job folder."""

    def __init__(self, binary: str = "yt-dlp", timeout_seconds: int = 600, max_upload_bytes: int = 100 * 1024 * 1024):
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self.max_upload_bytes = max_upload_bytes

    async def download(self, url: str, destination: Path) -> Path:
        validate_youtube_url(url)
        destination.mkdir(parents=True, exist_ok=True)
        output_template = str(destination / "input.%(ext)s")
        max_size = f"{max(1, self.max_upload_bytes // (1024 * 1024))}M"
        command = [
            self.binary, "--no-config", "--no-playlist", "--restrict-filenames",
            "--max-filesize", max_size, "--extract-audio", "--audio-format", "wav",
            "--output", output_template, "--", url,
        ]
        logger.info("youtube_audio_download_started host=%s", urlparse(url).hostname)
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("YouTube import is not installed on this server") from exc
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError("YouTube audio download timed out")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
            raise RuntimeError(f"Could not download YouTube audio: {' '.join(detail) or 'yt-dlp failed'}")
        wav = destination / "input.wav"
        if not wav.exists():
            raise RuntimeError("YouTube download completed without a WAV file")
        if wav.stat().st_size > self.max_upload_bytes:
            wav.unlink(missing_ok=True)
            raise RuntimeError("Downloaded audio exceeds the configured size limit")
        return wav
