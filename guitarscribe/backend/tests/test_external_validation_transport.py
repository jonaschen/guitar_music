import hashlib
import json

import pytest
import requests

from scripts.run_external_validation import submit, collect


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class Transport:
    def __init__(self, fail=None):
        self.posts, self.gets, self.fail = [], [], fail

    def post(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["files"]["file"][1].read()
        self.posts.append(url)
        if self.fail == "timeout":
            raise requests.Timeout("secret-like transport content must not reach logs")
        if self.fail == "payment":
            return Response({"detail": "payment required"}, 402)
        return Response({"job_id": f"job-{len(self.posts)}"})

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        self.gets.append(url)
        return Response({"status": "COMPLETED"} if url.endswith("status") else [[0, 1]])


@pytest.fixture
def packet(tmp_path):
    path = tmp_path / "packet"
    path.mkdir()
    cases = []
    for i in range(3):
        clip = path / f"fixture-{i}.wav"
        clip.write_bytes(b"test transport bytes, not a real recording")
        cases.append({"recording_id": f"fixture-{i}", "clip": clip.name, "start": 0, "end": 15,
                      "clip_sha256": hashlib.sha256(clip.read_bytes()).hexdigest()})
    (path / "manifest.json").write_text(json.dumps({"cases": cases, "maximum_job_creations": 6}))
    return path


def test_no_submission_without_free_account_confirmation(packet, tmp_path):
    transport = Transport()
    with pytest.raises(ValueError):
        submit(packet, tmp_path / "results", transport)
    assert transport.posts == []


def test_six_submissions_are_resumable_without_duplicate_posts(packet, tmp_path):
    transport, output = Transport(), tmp_path / "results"
    submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 6
    submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 6
    collect(packet, output, transport)
    assert len(transport.gets) == 12
    collect(packet, output, transport)
    assert len(transport.gets) == 12
    result = output / "fixture-0.beats.json"
    result.write_text("[]")
    with pytest.raises(ValueError, match="changed"):
        collect(packet, output, transport)


@pytest.mark.parametrize("failure", ["timeout", "payment"])
def test_unknown_or_rejected_submission_stops_batch_and_prevents_retry(packet, tmp_path, failure):
    transport, output = Transport(fail=failure), tmp_path / "results"
    with pytest.raises(RuntimeError):
        submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 1
    with pytest.raises(RuntimeError, match="uncertain"):
        submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 1
    assert "secret-like" not in next(output.glob("*.job.json")).read_text()


def test_changed_packet_refuses_upload(packet, tmp_path):
    transport = Transport()
    (packet / "fixture-2.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="differs"):
        submit(packet, tmp_path / "results", transport, confirmed_unpaid_account=True)
    assert not transport.posts


def test_vocabulary_experiment_uses_three_jobs_and_refuses_reusing_other_config(packet, tmp_path, monkeypatch):
    import scripts.run_external_validation as runner
    transport, output = Transport(), tmp_path / "results"
    monkeypatch.setattr(runner, "TASKS", [("chords", "/chord-recognition", {"vocabulary": "full"})])
    submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 3
    monkeypatch.setattr(runner, "TASKS", [("chords", "/chord-recognition", {"vocabulary": "major-minor"})])
    with pytest.raises(ValueError, match="another packet"):
        submit(packet, output, transport, confirmed_unpaid_account=True)
    assert len(transport.posts) == 3
