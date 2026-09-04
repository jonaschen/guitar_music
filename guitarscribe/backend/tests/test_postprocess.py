import pytest
from app.postprocess.chords import ChordPostProcessor
from app.postprocess.melody import MelodyPostProcessor
from app.models.analysis import ChordComplexity, MelodyNote

def test_chord_smooth(sample_chord_analysis, sample_beat_analysis):
    pp = ChordPostProcessor()
    # 1.9 to 2.1 is 0.2 < 0.3, so it should be smoothed
    smoothed = pp.smooth_chords(sample_chord_analysis.chords, sample_beat_analysis)
    assert len(smoothed) == 2

def test_chord_simplify(sample_chord_analysis):
    pp = ChordPostProcessor()
    simplified = pp.simplify(sample_chord_analysis.chords, ChordComplexity.SIMPLE)
    assert simplified[-1].symbol == "G" # Gmaj7 -> G

def test_melody_remove_short():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id="1", start=0.0, end=0.05, midi=60, note="C4", confidence=0.9), # short
        MelodyNote(id="2", start=0.1, end=0.5, midi=62, note="D4", confidence=0.9)
    ]
    filtered = pp.remove_short_notes(notes)
    assert len(filtered) == 1
    assert filtered[0].id == "2"

def test_melody_merge_repeated():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id="1", start=0.0, end=0.5, midi=60, note="C4", confidence=0.9),
        MelodyNote(id="2", start=0.55, end=1.0, midi=60, note="C4", confidence=0.9)
    ]
    merged = pp.merge_repeated(notes)
    assert len(merged) == 1
    assert merged[0].end == 1.0
