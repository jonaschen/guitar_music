from io import BytesIO
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import (
    SaveRevisionRequest,
    analyze_audio,
    app,
    get_job_service,
    get_submission_limiter,
    get_revision_store,
    load_revision,
    save_revision,
)
from app.models.analysis import MelodyNote
from app.models.score import AnalysisSummary, KeyContext, KeySignature, SongInfo, SongScore
from app.services.revisions import RevisionStore
from app.services.rate_limit import SubmissionRateLimiter
from app.sources.youtube import validate_youtube_url


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
async def test_openapi_documents_async_job_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    document = response.json()
    create_job = document["paths"]["/api/v1/jobs"]["post"]
    assert document["info"]["title"] == "GuitarScribe API"
    assert {tag["name"] for tag in document["tags"]} >= {"Analysis jobs", "Scores", "Lyrics"}
    assert create_job["summary"] == "Queue an uploaded audio file for analysis"
    assert "202" in create_job["responses"]
    assert document["paths"]["/api/v1/jobs/{job_id}"]["get"]["summary"] == "Read job status and result"


@pytest.mark.asyncio
async def test_rhythm_pattern_endpoint_returns_playable_templates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/rhythm-patterns", params={"time_signature": "4/4"})

    assert response.status_code == 200
    patterns = response.json()
    assert patterns
    assert patterns[0]["pattern_id"]
    assert patterns[0]["display"]


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
async def test_remap_tab_endpoint_honors_guitar_mapping_preferences():
    score = make_score()
    score.melody = [MelodyNote(id="n1", start=0.0, end=0.5, midi=67, note="G4")]
    score.guitar.max_fret = 2
    score.guitar.tab_preference = "low_position"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/remap-tab", json=score.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert body["guitar"]["tab_preference"] == "low_position"
    assert body["melody"][0]["string"] is None
    assert body["melody"][0]["fret"] is None


@pytest.mark.asyncio
async def test_fit_lyric_timing_to_bars_uses_detected_measure_starts():
    from app.models.analysis import BeatInfo
    from app.models.lyrics import LyricsTrack, LyricLine

    score = make_score()
    score.beats = [
        BeatInfo(time=0.0, beat=1, measure=1),
        BeatInfo(time=1.0, beat=1, measure=2),
        BeatInfo(time=2.0, beat=1, measure=3),
    ]
    score.song.duration_seconds = 3.0
    score.lyrics = LyricsTrack(lines=[LyricLine(id="l1", order=1, text="One"), LyricLine(id="l2", order=2, text="Two")])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/lyrics/fit-timing-to-bars", json=score.model_dump(mode="json"))

    assert response.status_code == 200
    lines = response.json()["lyrics"]["lines"]
    assert [(line["start"], line["end"]) for line in lines] == [(0.0, 1.0), (1.0, 3.0)]
    assert all(line["origin"] == "alignment" for line in lines)


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
                    "separate_vocals": "true",
                    "chord_complexity": "standard",
                },
                files={"audio_file": ("test.wav", b"RIFFfake", "audio/wav")},
            )
            assert create_response.status_code == 202
            assert create_response.json()["separate_vocals"] is True
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


@pytest.mark.asyncio
async def test_job_endpoint_returns_service_unavailable_when_queue_is_full(tmp_path):
    from app.services.jobs import AnalysisJobService, JobStore
    from tests.test_jobs import WaitingPipeline

    pipeline = WaitingPipeline()
    service = AnalysisJobService(
        JobStore(tmp_path / "jobs"), pipeline_factory=lambda: pipeline,
        max_concurrent_jobs=1, max_queued_jobs=1,
    )
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_submission_limiter] = lambda: SubmissionRateLimiter(limit=0, window_seconds=60)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post("/api/v1/jobs", data={"rights_confirmed": "true"}, files={"audio_file": ("first.wav", b"RIFFfake", "audio/wav")})
            await pipeline.started.wait()
            second = await client.post("/api/v1/jobs", data={"rights_confirmed": "true"}, files={"audio_file": ("second.wav", b"RIFFfake", "audio/wav")})
            rejected = await client.post("/api/v1/jobs", data={"rights_confirmed": "true"}, files={"audio_file": ("third.wav", b"RIFFfake", "audio/wav")})

        assert first.status_code == 202
        assert second.status_code == 202
        assert rejected.status_code == 503
        assert rejected.headers["retry-after"] == "30"
        assert "queue is full" in rejected.json()["detail"]
    finally:
        service.cancel(first.json()["id"])
        service.cancel(second.json()["id"])
        await asyncio.sleep(0)
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_youtube_job_requires_rights_and_enabled_resolver(tmp_path):
    from app.services.jobs import AnalysisJobService, JobStore

    service = AnalysisJobService(JobStore(tmp_path / "jobs"), pipeline_factory=StubPipeline)
    app.dependency_overrides[get_job_service] = lambda: service
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            denied = await client.post("/api/v1/youtube-jobs", json={"url": "https://www.youtube.com/watch?v=video", "rights_confirmed": False})
            disabled = await client.post("/api/v1/youtube-jobs", json={"url": "https://www.youtube.com/watch?v=video", "rights_confirmed": True})
        assert denied.status_code == 400
        assert disabled.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_youtube_url_validation_rejects_non_youtube_hosts():
    assert validate_youtube_url("https://youtu.be/example") == "https://youtu.be/example"
    with pytest.raises(ValueError, match="Only HTTPS"):
        validate_youtube_url("https://example.com/watch?v=video")
    with pytest.raises(ValueError, match="Only HTTPS"):
        validate_youtube_url("http://www.youtube.com/watch?v=video")

def test_revision_store_uses_sqlite(tmp_path):
    store = RevisionStore(tmp_path / "revisions")
    revision_id = store.save(make_score(), "sqlite-revision")

    assert (tmp_path / "revisions" / "guitarscribe.sqlite3").exists()
    assert store.load(revision_id).song.title == "Saved Song"


@pytest.mark.asyncio
async def test_revision_lyrics_api_forks_without_overwriting_parent(tmp_path):
    from app.models.lyrics import LyricLine, LyricsTrack

    store = RevisionStore(tmp_path / "revisions")
    parent_score = make_score().model_copy(update={"lyrics": LyricsTrack(lines=[LyricLine(id="line-1", order=0, text="Original")])})
    parent_id = store.save(parent_score)
    app.dependency_overrides[get_revision_store] = lambda: store
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.patch(f"/revisions/{parent_id}/lyrics/lines/line-1", json={"text": "Edited", "start": 1.0, "end": 2.0})
            assert response.status_code == 200
            child_id = response.json()["revision_id"]
            lyrics_response = await client.get(f"/revisions/{child_id}/lyrics")
    finally:
        app.dependency_overrides.clear()

    assert child_id != parent_id
    assert store.load(parent_id).lyrics.lines[0].text == "Original"
    assert lyrics_response.json()["lines"][0]["text"] == "Edited"
    assert lyrics_response.json()["lines"][0]["start"] == 1.0


@pytest.mark.asyncio
async def test_revision_lyrics_api_splits_and_merges_lines(tmp_path):
    from app.models.lyrics import LyricLine, LyricsTrack

    store = RevisionStore(tmp_path / "revisions")
    parent_id = store.save(make_score().model_copy(update={"lyrics": LyricsTrack(lines=[LyricLine(id="line-1", order=0, text="Hello world", start=0, end=4)])}))
    app.dependency_overrides[get_revision_store] = lambda: store
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            split = await client.post(f"/revisions/{parent_id}/lyrics/lines/line-1/split", json={"character_index": 6})
            assert split.status_code == 200
            split_body = split.json()
            split_id = split_body["revision_id"]
            assert [line["text"] for line in split_body["score"]["lyrics"]["lines"]] == ["Hello", "world"]
            assert split_body["score"]["lyrics"]["lines"][0]["end"] == pytest.approx(2.18, abs=0.01)
            merged = await client.post(f"/revisions/{split_id}/lyrics/lines/line-1/merge-next")
    finally:
        app.dependency_overrides.clear()

    assert merged.status_code == 200
    assert [line["text"] for line in merged.json()["score"]["lyrics"]["lines"]] == ["Hello world"]

@pytest.mark.asyncio
async def test_chordpro_export_endpoint():
    score = make_score()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/chordpro", json=score.model_dump(mode="json"))

    assert response.status_code == 200
    assert "{title: Saved Song}" in response.text
    assert "{key: G major}" in response.text

@pytest.mark.asyncio
async def test_lyric_timing_endpoint_updates_a_line():
    payload = make_score().model_dump(mode="json")
    payload["lyrics"] = {
        "id": "lyrics-1", "language": "en", "source": "user-pasted", "timing_level": "line", "raw_text": "Hello", "revision": 1,
        "lines": [{"id": "line-1", "order": 1, "start": None, "end": None, "text": "Hello", "confidence": 1.0, "origin": "user", "edited": False, "words": []}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/lyrics/timing", json={"score": payload, "line_id": "line-1", "start": 1.25})

    assert response.status_code == 200
    assert response.json()["lyrics"]["lines"][0]["start"] == 1.25

@pytest.mark.asyncio
async def test_analysis_rejects_oversized_upload(monkeypatch):
    monkeypatch.setenv("GUITARSCRIBE_MAX_UPLOAD_BYTES", "3")
    upload = StubUploadFile(filename="test.wav", content=b"RIFFfake")
    with pytest.raises(Exception) as exc_info:
        await analyze_audio(upload, True, "vocal", "standard", StubPipeline())
    assert getattr(exc_info.value, "status_code", None) == 413


@pytest.mark.asyncio
async def test_playback_manifest_endpoint_returns_revision_and_tracks():
    score = make_score()
    from app.models.analysis import BeatInfo, MelodyNote
    score = score.model_copy(update={
        "beats": [BeatInfo(time=0.0, beat=1, measure=1)],
        "melody": [MelodyNote(id="n", start=0.0, end=0.5, midi=60, note="C4")],
    })
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/scores/playback/manifest", json=score.model_dump(mode="json"))

    assert response.status_code == 200
    body = response.json()
    assert len(body["revision"]) == 16
    assert {event["track"] for event in body["events"]} >= {"melody", "metronome"}
