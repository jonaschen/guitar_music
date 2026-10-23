from copy import deepcopy

import pytest

from app.evaluation.lyric_anchor_audit import audit_anchors


def inputs():
    score = {"beats": [{"time": 10, "measure": 3, "beat": 2},
                        {"time": 11, "measure": 3, "beat": 3}],
             "chords": [{"id": "a", "start": 10, "end": 11, "symbol": "C", "voicing_id": "c"},
                        {"id": "b", "start": 11, "end": 12, "symbol": "C", "voicing_id": "c"},
                        {"id": "g", "start": 12, "end": 14, "symbol": "G", "voicing_id": "g"}]}
    manifest = {"revision": "r", "events": [
        {"id": "a1", "track": "guitar", "source_id": "a", "start": 10.2, "pitches": [60]},
        {"id": "b1", "track": "guitar", "source_id": "b", "start": 11, "pitches": [60]},
        {"id": "g1", "track": "guitar", "source_id": "g", "start": 12.2,
         "pitches": [67, 71], "pitch_offsets": [.02, .04]}]}
    return score, manifest


def test_clip_conversion_signed_error_merged_boundary_and_associated_stroke():
    score, manifest = inputs()
    before = deepcopy((score, manifest))
    report = audit_anchors(score, manifest, [dict(anchor_index=0, raw_seconds=2.1,
                          seconds=2.25, reviewed=True, skipped=False)], 10)
    row = report["rows"][0]
    assert row["analysis_time"] == 12.25
    assert row["nearest_beat"]["beat"] == 3
    assert row["nearest_beat"]["signed_error_seconds"] == 1.25
    assert row["nearest_chord_boundary"]["label"] == "G"
    assert row["nearest_chord_boundary"]["first_guitar_stroke"]["time"] == pytest.approx(12.22)
    assert row["nearest_first_guitar_stroke"]["signed_error_seconds"] == pytest.approx(.03)
    merged = audit_anchors(score, manifest, [dict(seconds=1, raw_seconds=1)], 10)["rows"][0]
    assert merged["nearest_chord_boundary"]["source_ids"] == ["a", "b"]
    assert merged["nearest_first_guitar_stroke"]["time"] == 10.2
    assert (score, manifest) == before


def test_null_skipped_and_empty_references_do_not_invent_comparisons():
    observations = [dict(anchor_index=0, raw_seconds=1, seconds=None, reviewed=False, skipped=False),
                    dict(anchor_index=1, raw_seconds=2, seconds=2, reviewed=True, skipped=True),
                    dict(anchor_index=2, raw_seconds=0, seconds=0, reviewed=False, skipped=False)]
    report = audit_anchors({}, {}, observations, 10)
    assert report["counts"] == dict(total=3, compared=1, skipped=1, missing=1, reviewed=1)
    assert [r["analysis_time"] for r in report["rows"]] == [None, None, 10]
    assert all(r["nearest_beat"] is None and r["nearest_chord_boundary"] is None
               and r["nearest_first_guitar_stroke"] is None for r in report["rows"])


def test_voicing_change_and_gap_remain_boundaries_and_absent_stroke_stays_null():
    score, _ = inputs()
    score["chords"][1]["voicing_id"] = "other"
    score["chords"][2]["start"] = 12.5
    row = audit_anchors(score, {}, [dict(seconds=1)], 10)["rows"][0]
    assert row["nearest_chord_boundary"]["time"] == 11
    assert row["nearest_chord_boundary"]["first_guitar_stroke"] is None
    assert row["nearest_first_guitar_stroke"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_mark_is_rejected(value):
    with pytest.raises(ValueError):
        audit_anchors({}, {}, [dict(seconds=value)], 0)
