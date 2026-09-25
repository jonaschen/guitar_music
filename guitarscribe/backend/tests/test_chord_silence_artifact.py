import numpy as np
import pytest

from app.analyzers.chords.chromagram import decode_beat_synchronous_chords, get_chord_templates
from app.analyzers.chords.canonical_adapter import CanonicalChordAnalyzerAdapter
from app.models.analysis import BeatAnalysis, BeatInfo, ChordAnalysis, ChordComplexity, RhythmSuggestion
from app.models.candidates import AnalyzerRun, ChordResult, TimingCandidate, TimingResult
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest
from app.postprocess.chords import ChordPostProcessor


@pytest.mark.asyncio
@pytest.mark.parametrize("use_beats", [True, False])
async def test_silence_survives_artifact_round_trip_but_does_not_play(use_beats):
    _, labels = get_chord_templates()
    times = np.arange(0, 1.5, 0.25)
    evidence = np.zeros((len(labels), len(times)))
    evidence[labels.index("C"), :2] = 0.8
    evidence[labels.index("C"), 4:] = 0.8
    beats = BeatAnalysis(bpm=120, beats=[
        BeatInfo(time=time, beat=index + 1, measure=1)
        for index, time in enumerate([0, 0.5, 1])
    ] if use_beats else [])
    raw = decode_beat_synchronous_chords(evidence, times, beats, 1.5, labels, preserve_regions=True)
    assert [(event.symbol, event.start, event.end) for event in raw] == [
        ("C", 0, 0.5), ("N", 0.5, 1), ("C", 1, 1.5),
    ]

    class Analyzer:
        async def analyze(self, audio, timing):
            return ChordAnalysis(chords=[event for event in raw if event.symbol != "N"], raw_regions=raw)

    adapter = CanonicalChordAnalyzerAdapter(Analyzer())
    timing = TimingResult(run=AnalyzerRun(engine="test"), candidates=[TimingCandidate(bpm=120)])
    artifact = await adapter.analyze_candidates(None, timing)
    restored = ChordResult.model_validate_json(artifact.model_dump_json())
    assert [region.label for region in restored.regions] == ["C", "N", "C"]
    silence = restored.regions[1]
    assert any(candidate.label == "N" and candidate.decoder_selected for candidate in silence.label_candidates)

    projected = adapter.project(restored)
    chords = ChordPostProcessor().process(projected.chords, beats, ChordComplexity.FULL)
    assert [(event.start, event.end) for event in chords] == [(0, 0.5), (1, 1.5)]
    # Canonical projection has no voicings; playback must resolve them itself.
    playback = compile_playback_manifest(SongScore(chords=chords, rhythm=RhythmSuggestion(display=["D"])))
    guitar = [event for event in playback.events if event.track == "guitar"]
    assert guitar
    assert all(event.end <= 0.5 or event.start >= 1 for event in guitar)


def test_raw_regions_keep_evidence_when_decoder_selects_same_label():
    _, labels = get_chord_templates()
    evidence = np.zeros((len(labels), 4))
    evidence[labels.index("C")] = 0.8
    evidence[labels.index("G"), :2] = 0.7
    evidence[labels.index("F"), 2:] = 0.7
    beats = BeatAnalysis(bpm=120, beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1)])
    regions = decode_beat_synchronous_chords(evidence, np.arange(4) * 0.25, beats, 1, labels, preserve_regions=True)
    assert len(regions) == 2
    assert [region.symbol for region in regions] == ["C", "C"]
    assert regions[0].label_candidates[1].label == "G"
    assert regions[1].label_candidates[1].label == "F"
