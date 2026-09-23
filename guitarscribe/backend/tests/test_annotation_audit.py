import hashlib
import json

from click.testing import CliRunner

from app.cli import main
from app.evaluation.annotations import QualityAnnotation


def gate_annotation(source_file: str, digest: str) -> QualityAnnotation:
    return QualityAnnotation(
        recording_id="easy-gate-01",
        evaluation_tier="quality_gate",
        source_file=source_file,
        source_sha256=digest,
        rights_note="Original test-team recording",
        difficulty="easy",
        excerpt_start=0,
        excerpt_end=30,
        tempo_bpm=120,
        beats=[{"time": index * 0.5} for index in range(60)],
        downbeats=[{"time": index * 2.0} for index in range(15)],
        chords=[{"start": 0, "end": 15, "label": "C"}, {"start": 15, "end": 30, "label": "G"}],
    )


def test_quality_audit_accepts_hashed_contiguous_gate_excerpt(tmp_path):
    annotations = tmp_path / "annotations"
    audio = tmp_path / "audio"
    annotations.mkdir()
    audio.mkdir()
    source = audio / "easy.wav"
    source.write_bytes(b"legal original audio fixture")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (annotations / "easy.json").write_text(gate_annotation(source.name, digest).model_dump_json())
    output = tmp_path / "audit.json"

    result = CliRunner().invoke(main, [
        "quality-audit", str(annotations), str(audio), "--output", str(output), "--require-quality-gate",
    ])

    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())
    assert report["valid"] is True
    assert report["ready_for_calibration"] is True
    assert report["quality_gate_count"] == 1
    assert report["g0_remaining_count"] == 11
    assert report["g0_baseline_ready"] is False
    assert report["difficulty_counts"]["easy"] == 1
    assert report["issues"] == []


def test_quality_audit_reports_hash_and_chord_coverage_errors(tmp_path):
    annotations = tmp_path / "annotations"
    audio = tmp_path / "audio"
    annotations.mkdir()
    audio.mkdir()
    source = audio / "easy.wav"
    source.write_bytes(b"changed audio")
    annotation = gate_annotation(source.name, "a" * 64)
    annotation.chords[1].start = 16
    (annotations / "easy.json").write_text(annotation.model_dump_json())

    result = CliRunner().invoke(main, ["quality-audit", str(annotations), str(audio)])

    assert result.exit_code != 0
    assert "source_hash_mismatch" in result.output
    assert "chord_gap" in result.output


def test_quality_audit_can_validate_smoke_fixture_without_treating_it_as_gate(tmp_path):
    annotations = tmp_path / "annotations"
    audio = tmp_path / "audio"
    annotations.mkdir()
    audio.mkdir()
    annotation = QualityAnnotation(
        recording_id="smoke",
        source_sha256="b" * 64,
        rights_note="Synthetic smoke fixture",
        difficulty="easy",
        excerpt_start=0,
        excerpt_end=2,
        chords=[{"start": 0, "end": 2, "label": "C"}],
    )
    (annotations / "smoke.json").write_text(annotation.model_dump_json())

    result = CliRunner().invoke(main, ["quality-audit", str(annotations), str(audio)])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["valid"] is True
    assert report["ready_for_calibration"] is False
    assert report["g0_remaining_count"] == 12
