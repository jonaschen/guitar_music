"""Retry retained uploads without overwriting songs or duplicating an uncertain POST."""
import asyncio
import sqlite3
import pytest
from httpx import ASGITransport, AsyncClient
from app.api import app, get_job_service, get_submission_limiter
from app.models.audio import SourceType
from app.models.jobs import AnalysisJob, JobStatus
from app.models.score import SongInfo, SongScore
from app.services.jobs import AnalysisJobService, JobQueueFullError, JobStore
from app.services.rate_limit import SubmissionRateLimiter

class Pipeline:
    async def run(self, source, options, progress_callback=None):
        assert source.path.read_bytes() == b'original upload'
        if progress_callback:
            await progress_callback('postprocessing')
        return SongScore(song=SongInfo(title='internal', duration_seconds=8))

def failed_upload(store, **overrides):
    data = dict(id='interrupted', status=JobStatus.FAILED, melody_mode='off',
                chord_complexity='full', error='The server restarted',
                created_at='2026-11-23T00:00:00+00:00', updated_at='2026-11-23T00:00:00+00:00')
    data.update(overrides)
    job = AnalysisJob(**data)
    store.save(job)
    directory = store.job_dir(job.id)
    directory.mkdir()
    (directory / 'input.mp3').write_bytes(b'original upload')
    (directory / 'source-title.txt').write_text('我的練習歌', encoding='utf8')
    (directory / 'root-practice.sqlite3').write_bytes(b'personal edits must stay here')
    return job

@pytest.mark.asyncio
async def test_retry_is_new_job_preserves_source_and_is_idempotent_across_restart(tmp_path):
    store = JobStore(tmp_path)
    original = failed_upload(store)
    before = {p.name:p.read_bytes() for p in store.job_dir(original.id).iterdir()}
    service = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
    assert service.get(original.id).can_retry
    child = await service.retry(original.id)
    assert child.id != original.id and child.retry_of == original.id
    assert (await service.retry(original.id)).id == child.id
    await service.tasks[child.id]
    finished = service.get(child.id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.score.song.title == '我的練習歌'
    assert finished.melody_mode == 'off' and finished.chord_complexity == 'full'
    assert finished.error is None and not finished.can_retry
    assert store.load(original.id) == original
    assert {p.name:p.read_bytes() for p in store.job_dir(original.id).iterdir()} == before
    assert not (store.job_dir(child.id) / 'root-practice.sqlite3').exists()
    restarted = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
    assert (await restarted.retry(original.id)).id == child.id
    with sqlite3.connect(store.database_path) as db:
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 2

@pytest.mark.asyncio
@pytest.mark.parametrize('status', [JobStatus.QUEUED, JobStatus.COMPLETED])
async def test_retry_does_not_reanalyse_active_or_completed_song(tmp_path, status):
    store = JobStore(tmp_path)
    service = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
    original = failed_upload(store, status=status)
    assert not service.get(original.id).can_retry
    with pytest.raises(ValueError):
        await service.retry(original.id)
    assert store.load(original.id) == original

@pytest.mark.asyncio
async def test_retry_refuses_missing_or_symlinked_input_and_does_not_redownload_youtube(tmp_path):
    store = JobStore(tmp_path)
    original = failed_upload(store)
    service = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
    path = store.job_dir(original.id) / 'input.mp3'
    path.unlink()
    for external in [None, tmp_path / 'private.mp3']:
        if external:
            external.write_bytes(b'private'); path.symlink_to(external)
        assert not service.get(original.id).can_retry
        with pytest.raises(ValueError):
            await service.retry(original.id)
    original.source_type = SourceType.YOUTUBE; store.save(original)
    assert not service.get(original.id).can_retry
    with pytest.raises(ValueError):
        await service.retry(original.id)

@pytest.mark.asyncio
async def test_retry_keeps_queue_limit_and_cancelled_copy_can_be_retried(tmp_path):
    store = JobStore(tmp_path)
    original = failed_upload(store)
    service = AnalysisJobService(store, Pipeline, max_concurrent_jobs=1, max_queued_jobs=0, job_ttl_seconds=None)
    child = await service.retry(original.id)
    assert (await service.retry(original.id)).id == child.id
    other = failed_upload(store, id='other')
    with pytest.raises(JobQueueFullError):
        await service.retry(other.id)
    task = service.tasks[child.id]; service.cancel(child.id)
    await asyncio.gather(task, return_exceptions=True)
    assert service.get(child.id).can_retry
    next_child = await service.retry(child.id)
    await service.tasks[next_child.id]
    assert service.get(next_child.id).status == JobStatus.COMPLETED

@pytest.mark.asyncio
async def test_retry_api_has_rate_limit_missing_job_and_recovery_contract(tmp_path):
    store = JobStore(tmp_path); failed_upload(store)
    service = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
    limiter = SubmissionRateLimiter(2, 3600)
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_submission_limiter] = lambda: limiter
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/api/v1/jobs/interrupted')
            assert response.json()['can_retry']
            response = await client.post('/api/v1/jobs/interrupted/retry')
            assert response.status_code == 202
            task = service.tasks.get(response.json()['id'])
            if task: await task
            response = await client.post('/api/v1/jobs/missing/retry')
            assert response.status_code == 404
            response = await client.post('/api/v1/jobs/interrupted/retry')
            assert response.status_code == 429 and 'Retry-After' in response.headers
    finally:
        app.dependency_overrides.pop(get_job_service, None)
        app.dependency_overrides.pop(get_submission_limiter, None)
