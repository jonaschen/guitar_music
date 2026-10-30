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



@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'https://youtu.be/FjFU9QHdx1g',
    'https://youtu.be/FjFU9QHdx1g?feature=shared',
    'https://youtu.be/FjFU9QHdx1g?si=phone-share',
    'https://www.youtube.com/watch?v=FjFU9QHdx1g',
])
async def test_shared_video_urls_reach_downloader_with_js_runtime(url, tmp_path, monkeypatch):
    async def create_process(*command, **options):
        assert command[command.index('--js-runtimes') + 1] == 'node'
        assert '--no-config' in command and '--no-playlist' in command
        assert command[-2:] == ('--', url)
        (tmp_path / 'input.wav').write_bytes(b'audio')
        return SuccessfulProcess()

    monkeypatch.setattr('app.sources.youtube.asyncio.create_subprocess_exec', create_process)
    assert await YouTubeAudioDownloader().download(url, tmp_path) == tmp_path / 'input.wav'


def test_downloader_prefers_runtime_dependency_but_respects_custom_binary(tmp_path, monkeypatch):
    monkeypatch.setattr('app.sources.youtube.sys.executable', str(tmp_path / 'python'))
    assert YouTubeAudioDownloader().binary == 'yt-dlp'
    (tmp_path / 'yt-dlp').touch()
    assert YouTubeAudioDownloader().binary == str(tmp_path / 'yt-dlp')
    assert YouTubeAudioDownloader(binary='/custom/downloader').binary == '/custom/downloader'


@pytest.mark.asyncio
async def test_unavailable_video_gives_actionable_message_and_keeps_diagnostic_log(tmp_path, monkeypatch, caplog):
    class UnavailableProcess:
        returncode = 1

        async def communicate(self):
            return b'', b'ERROR: [youtube] FjFU9QHdx1g: This video is not available'

    async def create_process(*command, **options):
        return UnavailableProcess()

    monkeypatch.setattr('app.sources.youtube.asyncio.create_subprocess_exec', create_process)
    with pytest.raises(RuntimeError, match='網址已辨識'):
        await YouTubeAudioDownloader().download('https://youtu.be/FjFU9QHdx1g', tmp_path)
    assert 'FjFU9QHdx1g: This video is not available' in caplog.text


@pytest.mark.asyncio
async def test_service_can_select_js_runtime_outside_default_path(tmp_path, monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv('GUITARSCRIBE_YOUTUBE_JS_RUNTIME', 'node:/opt/node22/bin/node')
    settings = Settings.from_env()

    async def create_process(*command, **options):
        assert command[command.index('--js-runtimes') + 1] == 'node:/opt/node22/bin/node'
        (tmp_path / 'input.wav').write_bytes(b'audio')
        return SuccessfulProcess()

    monkeypatch.setattr('app.sources.youtube.asyncio.create_subprocess_exec', create_process)
    await YouTubeAudioDownloader(js_runtime=settings.youtube_js_runtime).download('https://youtu.be/FjFU9QHdx1g', tmp_path)
