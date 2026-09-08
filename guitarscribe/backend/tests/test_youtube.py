import pytest

from app.sources.youtube import YouTubeAudioDownloader


class SuccessfulProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_youtube_download_rejects_and_removes_oversized_wav(tmp_path, monkeypatch):
    async def create_process(*_command, **_options):
        (tmp_path / "input.wav").write_bytes(b"too-large")
        return SuccessfulProcess()

    monkeypatch.setattr("app.sources.youtube.asyncio.create_subprocess_exec", create_process)
    downloader = YouTubeAudioDownloader(max_upload_bytes=3)

    with pytest.raises(RuntimeError, match="size limit"):
        await downloader.download("https://youtu.be/example", tmp_path)

    assert not (tmp_path / "input.wav").exists()


@pytest.mark.asyncio
async def test_youtube_download_rejects_successful_process_without_wav(tmp_path, monkeypatch):
    async def create_process(*_command, **_options):
        return SuccessfulProcess()

    monkeypatch.setattr("app.sources.youtube.asyncio.create_subprocess_exec", create_process)

    with pytest.raises(RuntimeError, match="without a WAV"):
        await YouTubeAudioDownloader().download("https://www.youtube.com/watch?v=example", tmp_path)

