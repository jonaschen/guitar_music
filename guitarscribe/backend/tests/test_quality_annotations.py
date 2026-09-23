import pytest
from pydantic import ValidationError

from app.evaluation.annotations import QualityAnnotation


def test_quality_annotation_schema_captures_quality_gate_ground_truth():
    annotation = QualityAnnotation(
        recording_id="licensed-easy-01",
        evaluation_tier="quality_gate",
        annotation_status="reviewed",
        reviewed_by="test-reviewer",
        source_file="licensed-easy-01.wav",
        source_sha256="a" * 64,
        rights_note="Original recording owned by the test team.",
        difficulty="easy",
        excerpt_start=10,
        excerpt_end=40,
        beats=[{"time": 10}],
        downbeats=[{"time": 10}],
        chords=[{"start": 10, "end": 12, "label": "C", "acceptable_labels": ["Cmaj"]}],
        sections=[{"start": 10, "end": 40, "label": "chorus", "melody_source": "vocal"}],
        melody=[{"start": 10, "end": 10.5, "midi": 60}],
        error_tags=["melody_rhythm"],
    )

    assert annotation.schema_version == "1.0"
    assert annotation.evaluation_tier == "quality_gate"
    assert annotation.annotation_status == "reviewed"
    assert annotation.sections[0].melody_source == "vocal"
    assert "source_sha256" in QualityAnnotation.model_json_schema()["properties"]


def test_quality_annotation_rejects_invalid_intervals():
    with pytest.raises(ValidationError):
        QualityAnnotation(
            recording_id="bad",
            source_sha256="b" * 64,
            rights_note="Licensed fixture",
            difficulty="easy",
            excerpt_start=10,
            excerpt_end=9,
        )


def test_quality_gate_rejects_short_smoke_length_and_missing_source_file():
    with pytest.raises(ValidationError, match="30 to 60 seconds"):
        QualityAnnotation(
            recording_id="too-short",
            evaluation_tier="quality_gate",
            source_file="too-short.wav",
            source_sha256="c" * 64,
            rights_note="Licensed fixture",
            difficulty="easy",
            excerpt_start=0,
            excerpt_end=8,
        )
