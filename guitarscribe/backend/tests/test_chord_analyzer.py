import pytest
import numpy as np
from app.analyzers.chords.chromagram import ChordDecoderConfig, ChromagramChordAnalyzer, _decode_region_sequence, decode_beat_synchronous_chords, estimate_key_from_chords, get_chord_templates, normalize_low_confidence_qualities
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
    assert all(len(event.label_candidates) >= 3 for event in events)
    assert all(sum(candidate.decoder_selected for candidate in event.label_candidates) == 1 for event in events)
    assert events[0].label_candidates[0].label == "C"
    assert events[0].label_candidates[0].acoustic_rank == 1


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
    assert {candidate.label for candidate in events[0].label_candidates[:2]} == {"C", "G"}


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


def test_chord_decoder_parameters_are_named_for_reproducible_bakeoffs():
    config = ChordDecoderConfig(change_threshold=0.2, no_chord_threshold=0.22)

    assert ChromagramChordAnalyzer(config).parameters == {
        "decoder_change_threshold": 0.2,
        "decoder_no_chord_threshold": 0.22,
        "decoder_base_change_penalty": 0.04,
        "decoder_short_event_change_penalty": 0.05,
        "decoder_circle_fifths_bonus": 0.015,
        "decoder_tonal_prior_scale": 1.0,
        "decoder_duration_weighted_emissions": False,
    }


def test_duration_weighting_does_not_let_short_tail_override_sustained_evidence():
    labels = ['C', 'G', 'N']
    regions = [(0, 4, np.array([.7, .6, 0])),
               (4, 4.1, np.array([.1, .9, 0]))]
    config = ChordDecoderConfig(tonal_prior_scale=0, circle_fifths_bonus=0,
                                duration_weighted_emissions=True)
    result = _decode_region_sequence(regions, labels, 'C', 'major', config)
    assert result[0][2] == 'C'
    # Preserve observation intervals even if the decoder chooses to sustain.
    assert [(r[0], r[1]) for r in result] == [(0, 4), (4, 4.1)]


def test_duration_weighting_preserves_strong_short_chord_between_long_chords():
    config = ChordDecoderConfig(duration_weighted_emissions=True)
    regions = [(0, 4, np.array([.9, .1, 0])),
               (4, 4.25, np.array([.1, .9, 0])),
               (4.25, 8.25, np.array([.9, .1, 0]))]
    result = _decode_region_sequence(regions, ['C', 'G', 'N'], 'C', 'major', config)
    assert [r[2] for r in result] == ['C', 'G', 'C']


def test_splitting_identical_sustained_evidence_preserves_weighted_path():
    config = ChordDecoderConfig(duration_weighted_emissions=True)
    c = np.array([.7, .6, 0])
    tail = (4, 4.1, np.array([.1, .9, 0]))
    whole = _decode_region_sequence([(0, 4, c), tail], ['C', 'G', 'N'], 'C', 'major', config)
    split = _decode_region_sequence([(0, 2, c), (2, 4, c), tail], ['C', 'G', 'N'], 'C', 'major', config)
    assert [r[2] for r in split] == [whole[0][2], whole[0][2], whole[1][2]]


def test_duration_weighted_confidence_uses_unweighted_margin():
    config = ChordDecoderConfig(duration_weighted_emissions=True)
    short = _decode_region_sequence([(0, .2, np.array([.9, .1, 0]))], ['C', 'G', 'N'], 'C', 'major', config)
    long = _decode_region_sequence([(0, 4, np.array([.9, .1, 0]))], ['C', 'G', 'N'], 'C', 'major', config)
    assert short[0][2:] == long[0][2:]


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
