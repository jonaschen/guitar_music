from app.evaluation import bpm_absolute_error, chord_symbol_recall
from app.models.analysis import ChordEvent


def test_bpm_absolute_error():
    assert bpm_absolute_error(120, 118.5) == 1.5


def test_chord_symbol_recall_requires_symbol_and_timing_match():
    expected = [ChordEvent(id="c", start=0, end=2, symbol="C"), ChordEvent(id="g", start=2, end=4, symbol="G")]
    actual = [ChordEvent(id="c", start=0.1, end=2, symbol="C"), ChordEvent(id="wrong", start=2, end=4, symbol="Am")]

    assert chord_symbol_recall(expected, actual) == 0.5
