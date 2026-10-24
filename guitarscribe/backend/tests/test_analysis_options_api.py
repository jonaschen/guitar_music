import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service, get_submission_limiter
from app.models.jobs import AnalysisJob
from app.services.rate_limit import SubmissionRateLimiter


class CapturingJobService:
    def __init__(self):
        self.submissions = []

    @staticmethod
    def _job(job_id: str, analysis_seconds: float | None, source_url: str | None = None) -> AnalysisJob:
        return AnalysisJob(
            id=job_id,
            analysis_seconds=analysis_seconds,
            source_url=source_url,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )

    async def submit(
        self, filename, content, melody_mode, chord_complexity,
        separate_vocals=False, skip_seconds=0, analysis_seconds=None,
    ):
        self.submissions.append({"source": "upload", "analysis_seconds": analysis_seconds})
        return self._job("upload-job", analysis_seconds)

    async def submit_youtube(
        self, url, melody_mode, chord_complexity,
        separate_vocals=False, skip_seconds=0, analysis_seconds=None,
    ):
        self.submissions.append({"source": "youtube", "analysis_seconds": analysis_seconds})
        return self._job("youtube-job", analysis_seconds, source_url=url)


@pytest.fixture
def api_service():
    previous_overrides = app.dependency_overrides.copy()
    service = CapturingJobService()
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_submission_limiter] = lambda: SubmissionRateLimiter(
        limit=100, window_seconds=60,
    )
    yield service
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)


async def post_analysis(client, source: str, analysis_seconds):
    if source == "upload":
        return await client.post(
            "/api/v1/jobs",
            files={"audio_file": ("song.wav", b"audio", "audio/wav")},
            data={"rights_confirmed": "true", "analysis_seconds": str(analysis_seconds)},
        )
    payload = {
        "url": "https://youtu.be/example",
        "rights_confirmed": True,
        "analysis_seconds": analysis_seconds,
    }
    # Python's JSON decoder accepts these non-finite numeric spellings; make
    # sure request validation can return its normal 422 response for them.
    body = json.dumps(payload, allow_nan=True)
    return await client.post(
        "/api/v1/youtube-jobs", content=body, headers={"Content-Type": "application/json"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["upload", "youtube"])
@pytest.mark.parametrize(
    "analysis_seconds",
    [0, -1, 600.001, float("nan"), float("inf"), float("-inf")],
    ids=["zero", "negative", "over-limit", "nan", "positive-infinity", "negative-infinity"],
)
async def test_analysis_seconds_invalid_values_are_rejected(source, analysis_seconds, api_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await post_analysis(client, source, analysis_seconds)

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert len(errors) == 1
    assert errors[0]["loc"] == ["body", "analysis_seconds"]
    assert {"type", "msg", "input"} <= errors[0].keys()
    if isinstance(analysis_seconds, float) and analysis_seconds != analysis_seconds:
        assert errors[0]["input"] == "nan"
    elif isinstance(analysis_seconds, float) and analysis_seconds in (float("inf"), float("-inf")):
        assert errors[0]["input"] == str(analysis_seconds)
    else:
        expected_input = str(analysis_seconds) if source == "upload" else analysis_seconds
        assert errors[0]["input"] == expected_input
    assert api_service.submissions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["upload", "youtube"])
async def test_45_second_analysis_option_reaches_job_service(source, api_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await post_analysis(client, source, 45)

    assert response.status_code == 202, response.text
    assert response.json()["analysis_seconds"] == 45
    assert api_service.submissions == [{"source": source, "analysis_seconds": 45.0}]


@pytest.mark.asyncio
async def test_capabilities_reports_recommended_analysis_window():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")

    assert response.status_code == 200, response.text
    capabilities = response.json()
    assert capabilities["recommended_analysis_seconds"] == 45
    assert capabilities["beat_engine"] in {"librosa", "beat_this_small"}
    assert capabilities["chord_engine"] in {"auto", "chordino", "chromagram"}
    for key in (
        "improved_accompaniment", "youtube_enabled", "vocal_separation_enabled",
        "melody_available",
    ):
        assert isinstance(capabilities[key], bool)
