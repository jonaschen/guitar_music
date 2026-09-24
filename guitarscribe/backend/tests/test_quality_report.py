import json

import pytest
import soundfile as sf
from click.testing import CliRunner

from app.cli import main
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.quality_report import evaluate_quality_layers
from app.models.analysis import BeatInfo, ChordEvent, ChordLabelCandidate, MelodyNote
from app.models.score import AnalysisSummary, SongScore


def make_annotation() -> QualityAnnotation:
    return QualityAnnotation(
        recording_id="legal-easy-01",
        source_sha256="a" * 64,
        rights_note="Original test fixture",
        difficulty="easy",
        excerpt_start=0,
        excerpt_end=2,
        tempo_bpm=120,
        beats=[{"time": value} for value in (0, 0.5, 1, 1.5)],
        downbeats=[{"time": 0}],
        chords=[
            {"start": 0, "end": 1, "label": "C"},
            {"start": 1, "end": 2, "label": "Am"},
        ],
        melody=[
            {"start": 0, "end": 0.5, "midi": 60},
            {"start": 0.5, "end": 1, "midi": 62},
        ],
        listening_notes=["Recognizable lead phrase"],
    )


def make_score() -> SongScore:
    return SongScore(
        analysis=AnalysisSummary(bpm=120),
        beats=[
            BeatInfo(time=0, beat=1, measure=1),
            BeatInfo(time=0.5, beat=2, measure=1),
            BeatInfo(time=1, beat=3, measure=1),
            BeatInfo(time=1.5, beat=4, measure=1),
        ],
        chords=[
            ChordEvent(id="c1", start=0, end=1, symbol="C"),
            ChordEvent(id="c2", start=1, end=2, symbol="Am"),
        ],
        melody=[
            MelodyNote(id="m1", start=0, end=0.5, midi=60, note="C4"),
            MelodyNote(id="m2", start=0.5, end=1, midi=62, note="D4"),
        ],
    )


def test_layered_quality_report_scores_perfect_match_without_combining_layers():
    report = evaluate_quality_layers(make_score(), make_annotation())

    assert "overall" not in report
    assert report["timing"]["beat_f_measure"] == pytest.approx(1)
    assert report["timing"]["downbeat_f_measure"] == pytest.approx(1)
    assert report["chord"]["majmin_weighted_accuracy"] == pytest.approx(1)
    assert report["chord"]["root_weighted_accuracy"] == pytest.approx(1)
    assert report["chord"]["acceptable_majmin_weighted_accuracy"] == pytest.approx(1)
    assert report["chord"]["acceptable_root_weighted_accuracy"] == pytest.approx(1)
    assert report["chord"]["boundary_precision"] == pytest.approx(1)
    assert report["chord"]["boundary_recall"] == pytest.approx(1)
    assert report["chord"]["boundary_f_measure"] == pytest.approx(1)
    assert report["chord"]["fragmentation_ratio"] == pytest.approx(1)
    assert report["chord"]["over_fragmented"] is False
    assert report["chord"]["review_event_count"] == 0
    assert report["melody"]["raw_pitch_accuracy"] == pytest.approx(1)
    assert report["melody"]["overall_accuracy"] == pytest.approx(1)
    assert report["human_review"]["required"] is True


def test_quality_report_cli_writes_versioned_report(tmp_path):
    score_path = tmp_path / "score.json"
    annotation_path = tmp_path / "annotation.json"
    output_path = tmp_path / "report.json"
    audio_path = tmp_path / "sonifications"
    score_path.write_text(make_score().model_dump_json())
    annotation_path.write_text(make_annotation().model_dump_json())

    result = CliRunner().invoke(
        main,
        [
            "quality-report",
            str(score_path),
            str(annotation_path),
            "--output",
            str(output_path),
            "--sonification-dir",
            str(audio_path),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(output_path.read_text())
    assert report["schema_version"] == "1.2"
    assert report["recording_id"] == "legal-easy-01"
    assert set(report["sonifications"]) == {
        "reference_timing", "estimated_timing", "reference_chords",
        "estimated_chords", "reference_melody", "estimated_melody",
    }
    for filename in report["sonifications"].values():
        samples, sample_rate = sf.read(audio_path / filename)
        assert sample_rate == 16000
        assert len(samples) == 32000
        assert samples.any()


def test_chord_report_exposes_over_fragmentation_and_review_load():
    score = make_score()
    score.chords = [
        ChordEvent(id="c1", start=0, end=0.5, symbol="C"),
        ChordEvent(id="g", start=0.5, end=1, symbol="G", needs_review=True, review_reasons=["isolated_outlier"]),
        ChordEvent(id="a1", start=1, end=1.5, symbol="Am"),
        ChordEvent(id="a2", start=1.5, end=2, symbol="A", needs_review=True, review_reasons=["low_confidence"]),
    ]

    chord_report = evaluate_quality_layers(score, make_annotation())["chord"]

    assert chord_report["estimated_event_count"] == 4
    assert chord_report["excess_event_count"] == 2
    assert chord_report["fragmentation_ratio"] == pytest.approx(2)
    assert chord_report["over_fragmented"] is True
    assert chord_report["review_event_count"] == 2
    assert chord_report["review_event_ratio"] == pytest.approx(0.5)


def test_chord_report_honors_explicit_alternative_harmonic_readings():
    reference = make_annotation()
    reference.chords[0].acceptable_labels = ["Am"]
    estimated = make_score()
    estimated.chords[0].symbol = "Am"

    chord_report = evaluate_quality_layers(estimated, reference)["chord"]

    assert chord_report["majmin_weighted_accuracy"] < 1
    assert chord_report["acceptable_majmin_weighted_accuracy"] == pytest.approx(1)
    assert chord_report["acceptable_root_weighted_accuracy"] == pytest.approx(1)


def test_chord_report_separates_acoustic_candidate_recall_from_decoder_choice():
    reference = make_annotation()
    estimated = make_score()
    estimated.chords[0].symbol = "G"
    estimated.chords[0].label_candidates = [
        ChordLabelCandidate(label="G", score=0.7, acoustic_rank=1, decoder_selected=True),
        ChordLabelCandidate(label="C", score=0.68, acoustic_rank=2),
        ChordLabelCandidate(label="Am", score=0.5, acoustic_rank=3),
    ]
    estimated.chords[1].label_candidates = [
        ChordLabelCandidate(label="Am", score=0.8, acoustic_rank=1),
        ChordLabelCandidate(label="C", score=0.75, acoustic_rank=2, decoder_selected=True),
        ChordLabelCandidate(label="Em", score=0.4, acoustic_rank=3),
    ]

    chord_report = evaluate_quality_layers(estimated, reference)["chord"]

    assert chord_report["acoustic_top1_acceptable_majmin_coverage"] == pytest.approx(0.5)
    assert chord_report["acoustic_top3_acceptable_majmin_coverage"] == pytest.approx(1)
    assert chord_report["decoder_override_event_ratio"] == pytest.approx(0.5)
