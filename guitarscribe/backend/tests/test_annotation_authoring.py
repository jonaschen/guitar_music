import hashlib

from click.testing import CliRunner

from app.cli import main
from app.evaluation.annotations import QualityAnnotation


def test_annotation_init_creates_hashed_empty_draft_without_fake_ground_truth(tmp_path):
    source = tmp_path / "owned.wav"
    source.write_bytes(b"owned audio bytes")
    output = tmp_path / "annotations" / "owned-easy-01.json"

    result = CliRunner().invoke(main, [
        "quality-annotation-init", str(source), str(output),
        "--recording-id", "owned-easy-01",
        "--rights-note", "Original recording owned by test team",
        "--difficulty", "easy",
        "--excerpt-start", "0",
        "--excerpt-end", "30",
        "--tempo-bpm", "120",
    ])

    assert result.exit_code == 0, result.output
    annotation = QualityAnnotation.model_validate_json(output.read_text())
    assert annotation.annotation_status == "draft"
    assert annotation.reviewed_by is None
    assert annotation.source_file == "owned.wav"
    assert annotation.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert annotation.beats == []
    assert annotation.chords == []

    repeated = CliRunner().invoke(main, [
        "quality-annotation-init", str(source), str(output),
        "--recording-id", "owned-easy-01", "--rights-note", "Owned",
        "--difficulty", "easy", "--excerpt-start", "0", "--excerpt-end", "30",
    ])
    assert repeated.exit_code != 0
    assert "already exists" in repeated.output
