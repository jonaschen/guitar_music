from io import BytesIO
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import (
    SaveRevisionRequest,
    analyze_audio,
    app,
    get_job_service,
    load_revision,
    save_revision,
)
from app.models.score import AnalysisSummary, KeyContext, KeySignature, SongInfo, SongScore
from app.services.revisions import RevisionStore


class StubPipeline:
    async def run(self, source_request, options):
        return SongScore(
            song=SongInfo(
                title=source_request.path.stem,
                source_type=source_request.source_type.value,
                duration_seconds=8.0,
            ),
            analysis=AnalysisSummary(key="G", mode="major", bpm=120.0, time_signature="4/4"),
            key_context=KeyContext(
                source=KeySignature(key="G", mode="major"),
                target=KeySignature(key="G", mode="major"),
                shape=KeySignature(key="G", mode="major"),
                sounding=KeySignature(key="G", mode="major"),
            ),
        )


class StubUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._buffer = BytesIO(content)

    async def read(self) -> bytes:
        return self._buffer.getvalue()


def make_score() -> SongScore:
    return SongScore(
        song=SongInfo(title="Saved Song", source_type="local", duration_seconds=8.0),
        analysis=AnalysisSummary(key="G", mode="major", bpm=120.0, time_signature="4/4"),
        key_context=KeyContext(
            source=KeySignature(key="G", mode="major"),
            target=KeySignature(key="G", mode="major"),
            shape=KeySignature(key="G", mode="major"),
            sounding=KeySignature(key="G", mode="major"),
        ),
    )


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_transpose_endpoint():
    payload = {
        "score": {
            "schema_version": "1.0",
            "song": {"title": "Test Song", "source_type": "youtube", "duration_seconds": 120.0},
            "analysis": {
                "key": "G",
                "mode": "major",
                "bpm": 120.0,
                "time_signature": "4/4",
                "capo": 0,
                "confidence": 0.0,
                "warnings": [],
            },
            "key_context": {
                "source": {"key": "G", "mode": "major"},
                "target": {"key": "G", "mode": "major"},
                "shape": {"key": "G", "mode": "major"},
                "sounding": {"key": "G", "mode": "major"},
                "transpose_semitones": 0,
                "accidental_preference": "auto",
                "audio_matches_notation": True,
            },
            "beats": [],
            "chords": [
                {
                    "id": "c1",
                    "start": 0.0,
                    "end": 2.0,
                    "symbol": "D/F#",
                    "confidence": 1.0,
                    "origin": "model",
                    "edited": False,
                    "source_symbol": None,
                    "shape_symbol": None,
                    "voicing_id": None,
                    "available_voicings": [],
                }
            ],
            "melody": [
                {
                    "id": "n1",
                    "start": 0.0,
                    "end": 0.5,
                    "midi": 67,
                    "note": "G4",
                    "confidence": 1.0,
                    "string": None,
                    "fret": None,
                    "origin": "model",
                    "edited": False,
                    "source_midi": None,
                    "source_note": None,
                }
            ],
            "rhythm": {
                "subdivision": 8,
                "pattern_id": "",
                "display": [],
                "confidence": 0.0,
                "label": "建議刷奏",
            },
            "provenance": {
                "beat_engine": "",
                "chord_engine": "",
                "melody_engine": "",
            },
        },
        "semitones": 2,
        "accidental_preference": "sharps",
        "capo": 2,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/transpose", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["key"] == "A"
    assert body["analysis"]["capo"] == 2
    assert body["key_context"]["source"]["key"] == "G"
    assert body["key_context"]["target"]["key"] == "A"
    assert body["key_context"]["shape"]["key"] == "G"
    assert body["chords"][0]["symbol"] == "E/G#"
    assert body["chords"][0]["shape_symbol"] == "D/F#"
    assert body["melody"][0]["midi"] == 69


@pytest.mark.asyncio
async def test_analyze_endpoint_requires_rights_confirmation():
    upload = StubUploadFile(filename="test.wav", content=b"RIFFfake")

    with pytest.raises(Exception) as exc_info:
        await analyze_audio(
            audio_file=upload,
            rights_confirmed=False,
            melody_mode="vocal",
            chord_complexity="standard",
            pipeline=StubPipeline(),
        )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert getattr(exc_info.value, "detail", None) == "Rights must be confirmed"


@pytest.mark.asyncio
async def test_analyze_endpoint_returns_score_for_uploaded_audio():
    upload = StubUploadFile(filename="test.wav", content=b"RIFFfake")

    score = await analyze_audio(
        audio_file=upload,
        rights_confirmed=True,
        melody_mode="vocal",
        chord_complexity="standard",
        pipeline=StubPipeline(),
    )

    assert score.song.source_type == "local"
    assert score.analysis.key == "G"
    assert score.key_context.source.key == "G"


@pytest.mark.asyncio
async def test_save_revision_endpoint(tmp_path):
    store = RevisionStore(tmp_path / "revisions")
    response = await save_revision(
        request=SaveRevisionRequest(score=make_score(), revision_id=None),
        revision_store=store,
    )

    assert store.load(response.revision_id).song.title == "Saved Song"


@pytest.mark.asyncio
async def test_load_revision_endpoint(tmp_path):
    store = RevisionStore(tmp_path / "revisions")
    revision_id = store.save(make_score(), "saved-revision")

    response = await load_revision(revision_id=revision_id, revision_store=store)

    assert response.song.title == "Saved Song"

@pytest.mark.asyncio
async def test_job_endpoints_queue_poll_and_return_completed_score(tmp_path):
    from app.services.jobs import AnalysisJobService, JobStore
    from tests.test_jobs import StubPipeline

    service = AnalysisJobService(JobStore(tmp_path / "jobs"), pipeline_factory=StubPipeline)
    app.dependency_overrides[get_job_service] = lambda: service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            create_response = await client.post(
                "/api/v1/jobs",
                data={
                    "rights_confirmed": "true",
                    "melody_mode": "vocal",
                    "chord_complexity": "standard",
                },
                files={"audio_file": ("test.wav", b"RIFFfake", "audio/wav")},
            )
            assert create_response.status_code == 202
            job_id = create_response.json()["id"]

            for _ in range(50):
                response = await client.get(f"/api/v1/jobs/{job_id}")
                body = response.json()
                if body["status"] == "completed":
                    break
                await asyncio.sleep(0)

        assert response.status_code == 200
        assert body["progress"] == 100
        assert body["score"]["analysis"]["key"] == "G"
    finally:
        app.dependency_overrides.clear()

def test_revision_store_uses_sqlite(tmp_path):
    store = RevisionStore(tmp_path / "revisions")
    revision_id = store.save(make_score(), "sqlite-revision")

    assert (tmp_path / "revisions" / "guitarscribe.sqlite3").exists()
    assert store.load(revision_id).song.title == "Saved Song"

@pytest.mark.asyncio
async def test_chordpro_export_endpoint():
    score = make_score()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/chordpro", json=score.model_dump(mode="json"))

    assert response.status_code == 200
    assert "{title: Saved Song}" in response.text
    assert "{key: G major}" in response.text
