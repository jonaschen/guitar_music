"""Product-path regressions: postprocessing must not undo decoder decisions."""

import pytest

from app.models.analysis import BeatAnalysis, BeatInfo, ChordComplexity, ChordEvent, ChordLabelCandidate
from app.postprocess.chords import ChordPostProcessor


def process(events, complexity=ChordComplexity.FULL):
    beats = BeatAnalysis(bpm=120, beats=[
        BeatInfo(time=index * 0.5, beat=index % 4 + 1, measure=1)
        for index in range(5)
    ])
    return ChordPostProcessor().process(events, beats, complexity, "C", "major")


def test_short_borrowed_chord_survives_full_postprocess_with_evidence():
    events = [
        ChordEvent(id="c1", start=0, end=0.9, symbol="C", confidence=0.9),
        ChordEvent(id="fm", start=0.9, end=1.1, symbol="Fm", confidence=0.45,
                   label_candidates=[ChordLabelCandidate(label="Fm", score=0.5,
                                                        acoustic_rank=1, decoder_selected=True)]),
        ChordEvent(id="c2", start=1.1, end=2, symbol="C", confidence=0.9),
    ]
    original = [event.model_dump() for event in events]
    result = process(events)
    assert [(event.symbol, event.start, event.end) for event in result] == [
        ("C", 0, 0.9), ("Fm", 0.9, 1.1), ("C", 1.1, 2),
    ]
    assert result[1].roman_numeral == "iv"
    assert result[1].needs_review
    assert {"short_event", "isolated_outlier", "low_confidence_modal_mixture"} <= set(result[1].review_reasons)
    assert result[1].label_candidates == events[1].label_candidates
    assert [event.model_dump() for event in events] == original


def test_same_chord_on_both_sides_of_silence_keeps_gap():
    result = process([
        ChordEvent(id="before", start=0, end=0.9, symbol="C"),
        ChordEvent(id="after", start=1.1, end=2, symbol="C"),
    ])
    assert [(event.start, event.end) for event in result] == [(0, 0.9), (1.1, 2)]


def test_low_confidence_dominant_return_is_reviewed_not_removed():
    result = process([
        ChordEvent(id="c1", start=0, end=0.5, symbol="C", confidence=0.9),
        ChordEvent(id="g", start=0.5, end=1, symbol="G", confidence=0.52),
        ChordEvent(id="c2", start=1, end=2, symbol="C", confidence=0.9),
    ])
    assert [event.symbol for event in result] == ["C", "G", "C"]
    assert "isolated_outlier" in result[1].review_reasons


@pytest.mark.parametrize("symbol", ["Cmaj7", "Am7", "G7", "Bdim", "Caug", "Am", "Cmaj7/E"])
def test_standard_complexity_preserves_supported_chord_quality(symbol):
    result = process([ChordEvent(id="chord", start=0, end=2, symbol=symbol)], ChordComplexity.STANDARD)
    assert result[0].symbol == symbol
