import numpy as np
import pytest

from app.evaluation.reference_timing import reference_timing_metrics


def measure(est, down=None, ref=None, **kwargs):
    ref = np.arange(0, 20, .5) if ref is None else ref
    return reference_timing_metrics(ref, est, ref[::4], ref[::4] if down is None else down,
                                    start=kwargs.get("start", 0), end=kwargs.get("end", 20))


@pytest.mark.parametrize("step,ratio", [(1, .5), (.25, 2)])
def test_alternate_tempo_cannot_masquerade_as_correct_tempo(step, ratio):
    report = measure(np.arange(0, 20, step))
    assert report["beat_aml_total"] > .95
    assert report["beat_cml_total"] < .1
    assert report["beat_count_ratio"] == ratio


def test_wrong_bar_phase_has_perfect_beats_but_wrong_downbeats():
    report = measure(np.arange(0, 20, .5), np.arange(.5, 20, 2))
    assert report["beat_cml_total"] == 1
    assert report["beat_f_measure"] == 1
    assert report["downbeat_f_measure"] == 0


def test_excerpt_ignores_outside_predictions_and_does_not_trim_first_five_seconds():
    report = measure(np.arange(0, 20, .5), start=1, end=4)
    assert report["beat_f_measure"] == 1
    assert report["reference_beat_count"] == report["estimated_beat_count"] == 6
    assert report["reference_downbeat_count"] == 1
    assert report["first_downbeat_phase_error_seconds"] == 0


def test_dropouts_lower_continuity_even_with_right_remaining_timestamps():
    ref = np.arange(0, 20, .5)
    report = measure(ref[(ref < 7) | (ref >= 11)])
    assert report["beat_cml_continuous"] < .6
    assert report["beat_cml_total"] < .9


def test_missing_reference_is_unknown_not_a_pass():
    report = measure([], down=[], ref=[])
    assert report["beat_f_measure"] == "not_annotated"
    assert report["beat_cml_total"] == "not_annotated"
    assert report["beat_count_ratio"] == "not_annotated"


def test_missing_estimate_is_a_failure_when_reference_exists():
    report = measure([], down=[])
    assert report["beat_f_measure"] == report["beat_cml_total"] == 0
    assert report["downbeat_f_measure"] == 0


@pytest.mark.parametrize("bad", [[1, 1], [2, 1], [float("nan")], [-1], [float("inf")]])
def test_invalid_timestamps_are_rejected_not_silently_sorted(bad):
    with pytest.raises(ValueError):
        measure(bad)
