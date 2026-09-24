import pytest

from app.evaluation.annotations import QualityAnnotation
from app.evaluation.quality_report import evaluate_quality_layers
from app.models.analysis import ChordEvent
from app.models.score import SongScore


def report(reference, estimated, start=0, end=3):
    annotation = QualityAnnotation(
        recording_id="silence", source_sha256="a" * 64, rights_note="Synthetic test",
        difficulty="easy", excerpt_start=start, excerpt_end=end,
        chords=[dict(start=a, end=b, label=label) for a, b, label in reference],
    )
    score = SongScore(chords=[ChordEvent(id=str(i), start=a, end=b, symbol=label)
                             for i, (a, b, label) in enumerate(estimated)])
    return evaluate_quality_layers(score, annotation)["chord"]


def test_internal_rest_scores_perfectly_including_both_boundaries():
    metrics = report([(0, 1, "C"), (1, 2, "N"), (2, 3, "C")], [(0, 1, "C"), (2, 3, "C")])
    for name in ("majmin_weighted_accuracy", "acceptable_majmin_weighted_accuracy",
                 "boundary_f_measure", "fragmentation_ratio"):
        assert metrics[name] == pytest.approx(1)
    assert metrics["correct_no_chord_seconds"] == 1
    assert metrics["missed_chord_seconds"] == 0
    assert metrics["estimated_event_count"] == 3
    assert "acoustic_top3_acceptable_majmin_coverage" not in metrics


def test_rest_and_missed_chord_are_distinguished():
    metrics = report([(0, 1, "C"), (1, 2, "N"), (2, 3, "G")], [(1, 2, "C"), (2, 3, "G")])
    assert metrics["missed_chord_seconds"] == 1
    assert metrics["false_chord_during_no_chord_seconds"] == 1
    assert metrics["correct_no_chord_seconds"] == 0
    assert metrics["majmin_weighted_accuracy"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("label,accuracy,missed", [("N", 1, 0), ("C", 0, 3)])
def test_empty_output_is_scored_against_reference(label, accuracy, missed):
    metrics = report([(0, 3, label)], [])
    assert metrics["majmin_weighted_accuracy"] == accuracy
    assert metrics["acceptable_majmin_weighted_accuracy"] == accuracy
    assert metrics["missed_chord_seconds"] == missed
    assert metrics["estimated_no_chord_seconds"] == 3


def test_head_and_tail_rests_and_excerpt_clipping():
    reference = [(10, 11, "N"), (11, 12, "C"), (12, 13, "N")]
    metrics = report(reference, [(0, 1, "G"), (11, 12, "C"), (20, 21, "G")], 10, 13)
    assert metrics["majmin_weighted_accuracy"] == 1
    assert metrics["correct_no_chord_seconds"] == 2
    assert metrics["boundary_f_measure"] == 1
    clipped = report([(0, 20, "C")], [(0, 20, "C")], 10, 13)
    assert clipped["acceptable_majmin_weighted_accuracy"] == 1


def test_overlapping_estimates_and_missing_reference_are_rejected():
    with pytest.raises(ValueError, match="Overlapping"):
        report([(0, 3, "C")], [(0, 2, "C"), (1, 3, "G")])
    with pytest.raises(ValueError, match="Reference chords must cover"):
        report([(0, 1, "C"), (2, 3, "G")], [])
