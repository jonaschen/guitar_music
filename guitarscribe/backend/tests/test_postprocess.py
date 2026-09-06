import pytest
from app.postprocess.chords import ChordPostProcessor
from app.postprocess.melody import MelodyPostProcessor
from app.models.analysis import BeatInfo, ChordComplexity, MelodyMode, MelodyNote

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


def test_melody_quantizes_to_eighth_note_grid():
    pp = MelodyPostProcessor()
    notes = [MelodyNote(id="1", start=0.13, end=0.62, midi=60, note="C4", confidence=0.9)]
    beats = [BeatInfo(time=0.0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1), BeatInfo(time=1.0, beat=3, measure=1)]

    quantized = pp.process(notes, beats)

    assert quantized[0].start == 0.25
    assert quantized[0].end == 0.5


def test_melody_selects_one_continuous_playable_note_per_grid_slot():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id="low", start=0.0, end=0.5, midi=36, note="C2", confidence=0.9),
        MelodyNote(id="middle", start=0.0, end=0.5, midi=64, note="E4", confidence=0.9),
        MelodyNote(id="high", start=0.0, end=0.5, midi=84, note="C6", confidence=0.9),
        MelodyNote(id="next", start=0.5, end=1.0, midi=65, note="F4", confidence=0.9),
        MelodyNote(id="jump", start=0.5, end=1.0, midi=83, note="B5", confidence=0.9),
    ]

    selected = pp.process(notes, [BeatInfo(time=0.0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1), BeatInfo(time=1.0, beat=3, measure=1)])

    assert [note.id for note in selected] == ["middle", "next"]


def test_melody_quantization_extends_collapsed_note_to_next_grid_slot():
    pp = MelodyPostProcessor()
    note = MelodyNote(id="1", start=0.27, end=0.36, midi=60, note="C4", confidence=0.9)
    beats = [BeatInfo(time=0.0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1), BeatInfo(time=1.0, beat=3, measure=1)]

    quantized = pp.process([note], beats)

    assert quantized[0].start == 0.25
    assert quantized[0].end == 0.5


def test_melody_skips_out_of_range_and_implausible_jumps():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id="base", start=0.0, end=0.5, midi=60, note="C4", confidence=0.9),
        MelodyNote(id="jump", start=0.5, end=1.0, midi=84, note="C6", confidence=0.9),
        MelodyNote(id="sub", start=1.0, end=1.5, midi=30, note="F#1", confidence=0.9),
    ]

    selected = pp.select_monophonic_line(notes)

    assert [note.id for note in selected] == ["base"]


def test_melody_quality_discloses_full_mix_limit_and_sparse_output():
    pp = MelodyPostProcessor()
    notes = [MelodyNote(id="one", start=0.0, end=0.5, midi=60, note="C4", confidence=0.9)]

    confidence, warnings = pp.assess_quality(notes, duration_seconds=60.0, mode=MelodyMode.VOCAL)

    assert confidence < 0.5
    assert any("without source separation" in warning for warning in warnings)
    assert any("sparse" in warning for warning in warnings)


def test_mix_melody_quality_has_lower_confidence_ceiling():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id=str(index), start=index * 0.5, end=index * 0.5 + 0.4, midi=60 + index % 3, note="C4", confidence=0.9)
        for index in range(60)
    ]

    confidence, _ = pp.assess_quality(notes, duration_seconds=60.0, mode=MelodyMode.MIX)

    assert confidence == 0.58


def test_vocal_mode_prefers_upper_lead_region_without_selecting_highest_candidate():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id=str(midi), start=0.0, end=0.5, midi=midi, note="note", confidence=0.9)
        for midi in [55, 60, 64, 67, 72]
    ]

    selected = pp.select_monophonic_line(notes, MelodyMode.VOCAL)

    assert [note.midi for note in selected] == [67]


def test_mix_mode_keeps_median_candidate_region():
    pp = MelodyPostProcessor()
    notes = [
        MelodyNote(id=str(midi), start=0.0, end=0.5, midi=midi, note="note", confidence=0.9)
        for midi in [48, 55, 60, 64, 72]
    ]

    selected = pp.select_monophonic_line(notes, MelodyMode.MIX)

    assert [note.midi for note in selected] == [60]
