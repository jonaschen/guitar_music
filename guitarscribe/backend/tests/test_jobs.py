import asyncio

import pytest

from app.models.score import AnalysisSummary, KeyContext, KeySignature, SongInfo, SongScore
from app.services.jobs import AnalysisJobService, JobStore


class StubPipeline:
    async def run(self, source_request, options, progress_callback=None):
        if progress_callback:
            await progress_callback("resolving")
            await progress_callback("beat_analysis")
            await progress_callback("postprocessing")
        return SongScore(
            song=SongInfo(title=source_request.path.stem, source_type="local", duration_seconds=8.0),
            analysis=AnalysisSummary(key="G", mode="major", bpm=120.0, time_signature="4/4"),
            key_context=KeyContext(
                source=KeySignature(key="G", mode="major"),
                target=KeySignature(key="G", mode="major"),
                shape=KeySignature(key="G", mode="major"),
                sounding=KeySignature(key="G", mode="major"),
            ),
        )


class WaitingPipeline:
    def __init__(self):
        self.started = asyncio.Event()

    async def run(self, source_request, options, progress_callback=None):
        if progress_callback:
            await progress_callback("resolving")
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("Cancelled task should not finish")


async def wait_for_terminal(service: AnalysisJobService, job_id: str):
    for _ in range(50):
        job = service.get(job_id)
        if job.status.value in {"completed", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0)
    raise AssertionError("job did not complete")


@pytest.mark.asyncio
async def test_job_service_persists_completed_score_and_progress(tmp_path):
    service = AnalysisJobService(JobStore(tmp_path / "jobs"), pipeline_factory=StubPipeline)

    created = await service.submit("test.wav", b"RIFFfake", "vocal", "standard")
    completed = await wait_for_terminal(service, created.id)

    assert completed.status.value == "completed"
    assert completed.progress == 100
    assert completed.score is not None
    assert completed.score.analysis.key == "G"
    assert service.get(created.id).score is not None


@pytest.mark.asyncio
async def test_job_service_cancels_active_job(tmp_path):
    pipeline = WaitingPipeline()
    service = AnalysisJobService(JobStore(tmp_path / "jobs"), pipeline_factory=lambda: pipeline)

    created = await service.submit("test.wav", b"RIFFfake", "vocal", "standard")
    await pipeline.started.wait()
    cancelled = service.cancel(created.id)
    await asyncio.sleep(0)

    assert cancelled.status.value == "cancelled"
    assert service.get(created.id).status.value == "cancelled"

def test_job_store_removes_only_expired_directories(tmp_path):
    import os
    import time
    from app.services.jobs import JobStore

    store = JobStore(tmp_path / "jobs")
    expired = store.job_dir("expired")
    fresh = store.job_dir("fresh")
    expired.mkdir()
    fresh.mkdir()
    old = time.time() - 10
    os.utime(expired, (old, old))

    assert store.cleanup_expired(5) == 1
    assert not expired.exists()
    assert fresh.exists()
