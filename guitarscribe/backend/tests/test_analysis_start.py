import asyncio
from io import BytesIO

import numpy as np
import pytest
import soundfile as sf
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service, get_submission_limiter
from app.services.rate_limit import SubmissionRateLimiter
from app.models.score import SongInfo, SongScore
from app.models.analysis import MelodyNote
from app.exporters.midi import export_midi, compile_playback_manifest
from app.exporters.musicxml import export_musicxml
from app.services.audio_crop import crop_analysis_audio
from app.services.jobs import AnalysisJobService, JobStore
from app.services.revisions import RevisionStore


@pytest.fixture(autouse=True)
def isolated_submission_limit(tmp_path):
    limiter = SubmissionRateLimiter(limit=100, window_seconds=60)
    service = AnalysisJobService(JobStore(tmp_path / "api-jobs"), InspectPipeline)
    app.dependency_overrides[get_submission_limiter] = lambda: limiter
    app.dependency_overrides[get_job_service] = lambda: service
    yield
    app.dependency_overrides.pop(get_submission_limiter, None)
    app.dependency_overrides.pop(get_job_service, None)


def source_wav():
    buffer = BytesIO()
    sf.write(buffer, np.concatenate([np.full(8000, .1), np.full(16000, .4)]), 8000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


class InspectPipeline:
    async def run(self, request, options, progress_callback=None):
        data, rate = sf.read(request.path)
        assert len(data) == 16000
        assert rate == 8000
        assert np.allclose(data, .4, atol=.0001)
        return SongScore(song=SongInfo(duration_seconds=len(data) / rate))


def test_source_offset_is_metadata_not_extra_export_silence():
    score = SongScore(song=SongInfo(duration_seconds=2), melody=[
        MelodyNote(id="first", start=.25, end=.75, midi=60, note="C4")
    ])
    midi, xml = export_midi(score), export_musicxml(score)
    score.song.source_start_seconds = 19
    assert export_midi(score) == midi
    assert export_musicxml(score) == xml
    manifest = compile_playback_manifest(score)
    assert manifest.duration_seconds == 2
    assert next(event for event in manifest.events if event.track == "melody").start == .25


@pytest.mark.asyncio
async def test_crop_precedes_analysis_and_audio_endpoint_uses_same_copy(tmp_path):
    service = AnalysisJobService(JobStore(tmp_path / "jobs"), InspectPipeline)
    app.dependency_overrides[get_job_service] = lambda: service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs", files={"audio_file": ("mv.wav", source_wav(), "audio/wav")},
                                         data={"rights_confirmed": "true", "skip_seconds": "1"})
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            await service.tasks[job_id]
            job = service.get(job_id)
            assert job.status == "completed", job.error
            assert job.score.song.duration_seconds == 2
            assert job.score.song.source_start_seconds == 1
            assert (service.store.job_dir(job_id) / "input.wav").read_bytes() == source_wav()
            audio = await client.get(f"/api/v1/jobs/{job_id}/audio")
            data, rate = sf.read(BytesIO(audio.content))
            assert len(data) / rate == 2
            assert np.allclose(data, .4, atol=.0001)
            revisions = RevisionStore(tmp_path / "revisions")
            assert revisions.load(revisions.save(job.score)).song.source_start_seconds == 1
    finally:
        app.dependency_overrides.pop(get_job_service, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("skip", [3, 4])
async def test_skip_at_or_beyond_end_fails_without_analysis(tmp_path, skip):
    service = AnalysisJobService(JobStore(tmp_path), InspectPipeline)
    job = await service.submit("mv.wav", source_wav(), "vocal", "standard", skip_seconds=skip)
    await service.tasks[job.id]
    result = service.get(job.id)
    assert result.status == "failed"
    assert "before the end" in result.error
    assert (service.store.job_dir(job.id) / "input.wav").read_bytes() == source_wav()


@pytest.mark.asyncio
async def test_youtube_skip_uses_downloaded_source(tmp_path):
    class Downloader:
        async def download(self, url, directory):
            path = directory / "input.wav"
            path.write_bytes(source_wav())
            return path
    service = AnalysisJobService(JobStore(tmp_path), InspectPipeline, youtube_downloader=Downloader())
    job = await service.submit_youtube("https://youtu.be/example", "vocal", "standard", skip_seconds=1)
    await service.tasks[job.id]
    assert service.get(job.id).score.song.source_start_seconds == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("skip", ["-1", "nan", "inf"])
async def test_invalid_start_is_rejected_before_submission(skip):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/jobs", files={"audio_file": ("mv.wav", b"unused")},
                                     data={"rights_confirmed": "true", "skip_seconds": skip})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_cancelling_crop_terminates_child(monkeypatch, tmp_path):
    class Process:
        returncode = None
        killed = False
        async def communicate(self):
            if not self.killed:
                await asyncio.Event().wait()
            return b"", b""
        def kill(self):
            self.killed = True
    process = Process()
    started = asyncio.Event()
    async def create(*args, **kwargs):
        started.set()
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    task = asyncio.create_task(crop_analysis_audio(tmp_path / "input.wav", tmp_path / "crop.wav", 1))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed
