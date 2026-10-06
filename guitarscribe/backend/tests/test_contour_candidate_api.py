from types import SimpleNamespace
import pytest
from httpx import AsyncClient, ASGITransport
from app.api import app, get_job_service
from app.models.jobs import AnalysisJob, JobStatus
from tests.test_bounded_checkpoint import source


@pytest.mark.asyncio
async def test_candidate_endpoint_preserves_source_and_rejects_incompatible_work(tmp_path):
    score, contour = source()
    score.provenance.melody_engine = "pyin_vocal"
    score.provenance.parameters["vocal_source_separated"] = True
    job = AnalysisJob(id="test", status=JobStatus.COMPLETED, score=score,
                      created_at="2026-10-06T00:00:00Z", updated_at="2026-10-06T00:00:00Z")
    artifact = tmp_path / "melody-contour.json"
    artifact.write_text(contour.model_dump_json())
    before = job.model_dump_json()
    app.dependency_overrides[get_job_service] = lambda: SimpleNamespace(
        get=lambda _: job, store=SimpleNamespace(job_dir=lambda _: tmp_path))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = score.model_dump(mode="json")
            result = await client.post("/api/v1/jobs/test/melody-candidate", json=body)
            assert result.status_code == 200, result.text
            candidate = result.json()
            assert len(candidate["melody"]) == 2
            assert candidate["chords"] == body["chords"]
            assert candidate["beats"] == body["beats"]
            assert candidate["provenance"]["parameters"]["candidate_source_job_id"] == "test"
            assert job.model_dump_json() == before
            for section, key, value in [("song", "source_start_seconds", 19), ("song", "duration_seconds", 1)]:
                altered = score.model_dump(mode="json")
                altered[section][key] = value
                assert (await client.post("/api/v1/jobs/test/melody-candidate", json=altered)).status_code == 409
            assert (await client.post("/api/v1/jobs/test/melody-candidate", json=candidate)).status_code == 409
            artifact.unlink()
            assert (await client.post("/api/v1/jobs/test/melody-candidate", json=body)).status_code == 404
            job.status = JobStatus.MELODY_ANALYSIS
            assert (await client.post("/api/v1/jobs/test/melody-candidate", json=body)).status_code == 409
    finally:
        app.dependency_overrides.clear()
