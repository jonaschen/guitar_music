import pytest
import numpy as np
from app.analyzers.chords.chromagram import ChromagramChordAnalyzer, _decode_region_sequence, decode_beat_synchronous_chords, estimate_key_from_chords, get_chord_templates, normalize_low_confidence_qualities
from app.analyzers.chords.chordino import ChordinoChordAnalyzer
from app.models.analysis import BeatAnalysis, BeatInfo, ChordEvent

@pytest.mark.asyncio
async def test_chromagram_analyzer(normalized_audio, sample_beat_analysis):
    analyzer = ChromagramChordAnalyzer()
    analysis = await analyzer.analyze(normalized_audio, sample_beat_analysis)
    
    assert len(analysis.chords) > 0
    assert analysis.key != ""
    assert analysis.engine == "chromagram"
    
    for c in analysis.chords:
        assert c.start < c.end
        assert len(c.symbol) > 0

@pytest.mark.asyncio
async def test_chordino_analyzer(normalized_audio, sample_beat_analysis):
    analyzer = ChordinoChordAnalyzer()
    try:
        import vamp
        analysis = await analyzer.analyze(normalized_audio, sample_beat_analysis)
        assert len(analysis.chords) > 0
        assert analysis.engine == "chordino"
    except ImportError:
        with pytest.raises((ImportError, RuntimeError)):
            await analyzer.analyze(normalized_audio, sample_beat_analysis)


def test_chromagram_decoder_aggregates_frames_into_beat_aligned_events():
    _, labels = get_chord_templates()
    frame_times = np.arange(0, 2, 0.25)
    similarities = np.zeros((len(labels), len(frame_times)))
    similarities[labels.index("C"), :4] = 0.8
    similarities[labels.index("G"), 4:6] = 0.8
    similarities[labels.index("C"), 6:] = 0.8
    beats = BeatAnalysis(
        bpm=120,
        beats=[BeatInfo(time=time, beat=index % 4 + 1, measure=1) for index, time in enumerate([0.0, 0.5, 1.0, 1.5])],
    )

    events = decode_beat_synchronous_chords(similarities, frame_times, beats, 2.0, labels)

    assert [(event.symbol, event.start, event.end) for event in events] == [
        ("C", 0.0, 1.0), ("G", 1.0, 1.5), ("C", 1.5, 2.0),
    ]


def test_chromagram_decoder_does_not_turn_small_argmax_flips_into_changes():
    _, labels = get_chord_templates()
    frame_times = np.arange(0, 1, 0.25)
    similarities = np.zeros((len(labels), len(frame_times)))
    similarities[labels.index("C"), :2] = 0.50
    similarities[labels.index("G"), :2] = 0.49
    similarities[labels.index("C"), 2:] = 0.49
    similarities[labels.index("G"), 2:] = 0.50
    beats = BeatAnalysis(
        bpm=120,
        beats=[BeatInfo(time=0.0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1)],
    )

    events = decode_beat_synchronous_chords(similarities, frame_times, beats, 1.0, labels)

    assert [(event.symbol, event.start, event.end) for event in events] == [("C", 0.0, 1.0)]


def test_sequence_decoder_rejects_brief_low_margin_outlier():
    _, labels = get_chord_templates()
    c_index = labels.index("C")
    g_index = labels.index("G")
    regions = []
    for start, end, c_score, g_score in [(0, 1, 0.8, 0.1), (1, 1.5, 0.49, 0.5), (1.5, 2.5, 0.8, 0.1)]:
        scores = np.zeros(len(labels))
        scores[c_index], scores[g_index] = c_score, g_score
        regions.append((start, end, scores))

    decoded = _decode_region_sequence(regions, labels, "C", "major")

    assert [label for _, _, label, _ in decoded] == ["C", "C", "C"]


def test_sequence_decoder_leaves_silence_as_no_chord_gap():
    _, labels = get_chord_templates()
    frame_times = np.arange(0, 1.5, 0.25)
    similarities = np.zeros((len(labels), len(frame_times)))
    similarities[labels.index("C"), :2] = 0.8
    similarities[labels.index("G"), 4:] = 0.8
    beats = BeatAnalysis(
        bpm=120,
        beats=[BeatInfo(time=time, beat=index + 1, measure=1) for index, time in enumerate([0.0, 0.5, 1.0])],
    )

    events = decode_beat_synchronous_chords(similarities, frame_times, beats, 1.5, labels)

    assert [(event.symbol, event.start, event.end) for event in events] == [
        ("C", 0.0, 0.5), ("G", 1.0, 1.5),
    ]


def test_chromagram_key_estimate_prefers_duration_weighted_diatonic_key():
    events = [
        ChordEvent(id="c", start=0, end=4, symbol="C"),
        ChordEvent(id="g", start=4, end=6, symbol="G"),
        ChordEvent(id="am", start=6, end=8, symbol="Am"),
        ChordEvent(id="f", start=8, end=10, symbol="F"),
    ]

    assert estimate_key_from_chords(events) == ("C", "major")


def test_low_confidence_parallel_minor_is_normalized_for_lead_sheet():
    events = [
        ChordEvent(id="bb-1", start=0, end=1, symbol="Bb", confidence=0.7),
        ChordEvent(id="bbm", start=1, end=2, symbol="Bbm", confidence=0.48),
        ChordEvent(id="bb-2", start=2, end=3, symbol="Bb", confidence=0.7),
        ChordEvent(id="gm", start=3, end=4, symbol="Gm", confidence=0.48),
    ]

    normalized = normalize_low_confidence_qualities(events, "C", "minor")

    assert [(event.symbol, event.start, event.end) for event in normalized] == [
        ("Bb", 0, 3), ("Gm", 3, 4),
    ]
