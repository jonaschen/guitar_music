from types import SimpleNamespace
import pytest
from httpx import AsyncClient, ASGITransport
from app.api import app, get_job_service, get_revision_store
from app.services.revisions import RevisionStore
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


@pytest.mark.asyncio
async def test_g_candidate_real_revision_roundtrip_manifest_and_midi(tmp_path):
    score, contour = source()
    score.provenance.melody_engine = "pyin_vocal"
    score.provenance.parameters["vocal_source_separated"] = True
    job = AnalysisJob(id="g-source", status=JobStatus.COMPLETED, score=score,
                      created_at="2026-10-07T00:00:00Z", updated_at="2026-10-07T00:00:00Z")
    (tmp_path / "melody-contour.json").write_text(contour.model_dump_json())
    before = job.model_dump_json()
    store = RevisionStore(tmp_path / "revisions")
    parent = store.save(score)
    app.dependency_overrides[get_revision_store] = lambda: store
    app.dependency_overrides[get_job_service] = lambda: SimpleNamespace(
        get=lambda _: job, store=SimpleNamespace(job_dir=lambda _: tmp_path))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/jobs/g-source/melody-candidate", json=score.model_dump(mode="json"))
            assert response.status_code == 200
            candidate = response.json()
            saved = await client.post("/revisions", json={"score": candidate, "revision_id": parent, "create_new": True})
            assert saved.status_code == 200
            revision = saved.json()["revision_id"]
            # Reopen SQLite as a new process/session would, not an in-memory mock.
            app.dependency_overrides[get_revision_store] = lambda: RevisionStore(tmp_path / "revisions")
            loaded = await client.get(f"/revisions/{revision}")
            assert loaded.status_code == 200
            restored = loaded.json()
            assert restored == candidate
            assert restored["provenance"]["parameters"]["candidate_source_job_id"] == "g-source"
            again = await client.post("/revisions", json={"score": restored, "revision_id": revision, "create_new": True})
            assert again.status_code == 200
            assert store.load(again.json()["revision_id"]).model_dump(mode="json") == candidate
            compiled = await client.post("/scores/playback/manifest", json=restored)
            assert compiled.status_code == 200
            melody = [e for e in compiled.json()["events"] if e["track"] == "melody"]
            expected = [(n["start"], n["end"], n["midi"]) for n in candidate["melody"]]
            assert [(e["start"], e["end"], e["pitches"][0]) for e in melody] == expected
            midi = await client.post("/scores/midi", json=restored)
            assert midi.status_code == 200
            data, pos, ticks, tempo = midi.content, 22, 0, None
            division = int.from_bytes(data[12:14], "big")
            starts, ends = [], []
            def variable():
                nonlocal pos
                value = 0
                while True:
                    byte = data[pos]; pos += 1
                    value = (value << 7) | (byte & 127)
                    if byte < 128:
                        return value
            while pos < len(data):
                ticks += variable()
                status = data[pos]; pos += 1
                if status == 255:
                    kind = data[pos]; pos += 1
                    length = variable()
                    if kind == 81:
                        tempo = int.from_bytes(data[pos:pos + length], "big")
                    pos += length
                elif status & 240 == 192:
                    pos += 1
                else:
                    assert status & 240 in (128, 144)
                    if status & 15 == 0:
                        assert tempo is not None
                        seconds = ticks * tempo / division / 1_000_000
                        (starts if status & 240 == 144 else ends).append((seconds, data[pos]))
                    pos += 2
            assert [n for _, n in starts] == [n for _, _, n in expected]
            assert [n for _, n in ends] == [n for _, _, n in expected]
            assert [t for t, _ in starts] == pytest.approx([s for s, _, _ in expected], abs=.0011)
            assert [t for t, _ in ends] == pytest.approx([e for _, e, _ in expected], abs=.0011)
            assert store.load(parent) == score
            assert job.model_dump_json() == before
    finally:
        app.dependency_overrides.clear()
