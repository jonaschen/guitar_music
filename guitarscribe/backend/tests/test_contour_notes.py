import pytest

from app.evaluation.contour_notes import decode_contour_notes


def decode(values):
    return decode_contour_notes(values, [0.9] * len(values), hop_seconds=0.02)


def test_stable_semitone_change_is_not_merged_like_vibrato():
    notes = decode([60.0] * 15 + [61.0] * 15)
    assert [n.midi for n in notes] == [60, 61]
    assert notes[0].end == pytest.approx(0.3)
    assert notes[1].start == pytest.approx(0.3)


def test_representative_pitch_uses_float_contour_not_per_frame_rounding():
    # Most frames round up, but their floating-point evidence is near a tie.
    values = [60.0] * 4 + [60.50000000001] * 6
    before = list(values)
    notes = decode(values)
    assert [n.midi for n in notes] == [60]
    assert values == before


def test_transition_evidence_can_include_a_half_semitone_bridge():
    # A minimum segment duration is not a minimum stable-plateau duration.
    # Do not require this ambiguous rising contour to become a single C.
    notes = decode([60.0] * 6 + [60.50000000001] * 5 + [61.0] * 2)
    assert [n.midi for n in notes] == [60, 61]
    assert all(n.end - n.start >= 0.1 - 1e-9 for n in notes)
    assert notes[0].end == notes[1].start


def test_vibrato_rest_and_short_unvoiced_runs():
    values = [60.0, 60.4, 59.6] * 10 + [None] * 5 + [64.0] * 10
    notes = decode(values)
    assert [n.midi for n in notes] == [60, 64]
    assert notes[0].end == pytest.approx(0.6)
    assert notes[1].start == pytest.approx(0.7)
    assert decode([None, 60.0, None]) == []


def test_no_confidence_promotion_or_out_of_range_pitch():
    notes = decode_contour_notes([69.0] * 10, [0.1] * 10, hop_seconds=0.02)
    assert notes[0].confidence == pytest.approx(0.1)
    assert decode([float("nan"), 130.0, -1.0, None]) == []
    with pytest.raises(ValueError):
        decode_contour_notes([], [], hop_seconds=0)
