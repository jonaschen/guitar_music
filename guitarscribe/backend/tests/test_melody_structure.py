import pytest

from app.evaluation.melody_structure import inspect_melody_structure
from app.models.analysis import MelodyNote


def note(identity, start, end, pitch=60):
    return MelodyNote(id=identity, start=start, end=end, midi=pitch, note="C4")


def test_overlap_from_different_onsets_is_reported_without_mutation():
    notes = [note("a", 0, 3), note("b", 1, 2), note("c", 1.5, 2.5)]
    before = [n.model_dump() for n in notes]
    report = inspect_melody_structure(list(reversed(notes)), 0, 4)
    assert report["voiced_seconds"] == 3
    assert report["overlap_seconds"] == 1.5
    assert report["peak_simultaneous_events"] == 3
    assert report["overlap_windows"] == [{"start": 1, "end": 2.5}]
    assert report["recognition_accuracy"] is None
    assert [n.model_dump() for n in notes] == before


def test_boundaries_clipping_and_empty_excerpts():
    notes = [note("a", 0, 1), note("b", 1, 2), note("c", 5, 6)]
    report = inspect_melody_structure(notes, 0.5, 1.5)
    assert report["note_count"] == 2
    assert report["voiced_seconds"] == 1
    assert report["overlap_seconds"] == 0
    assert report["peak_simultaneous_events"] == 1
    assert inspect_melody_structure(notes, 3, 4)["peak_simultaneous_events"] == 0
    assert inspect_melody_structure([], 0, 1)["recognition_accuracy"] is None


@pytest.mark.parametrize("start,end", [(1, 1), (2, 1), (-1, 1), (0, float("inf"))])
def test_invalid_excerpt_is_rejected(start, end):
    with pytest.raises(ValueError):
        inspect_melody_structure([], start, end)
