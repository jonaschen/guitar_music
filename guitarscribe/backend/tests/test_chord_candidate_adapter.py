import pytest

from app.analyzers.chords.canonical_adapter import CanonicalChordAnalyzerAdapter
from app.models.analysis import ChordAnalysis, ChordEvent, ChordLabelCandidate
from app.models.candidates import AnalyzerRun, TimingCandidate, TimingResult


@pytest.mark.asyncio
async def test_chord_adapter_uses_canonical_timing_and_round_trips_regions(normalized_audio):
    class LegacyAnalyzer:
        parameters = {"decoder_change_threshold": 0.12}

        async def analyze(self, audio, beats):
            assert beats.bpm == 120
            assert [beat.time for beat in beats.beats] == [0, 0.5, 1, 1.5]
            return ChordAnalysis(
                chords=[ChordEvent(
                    id="legacy", start=0, end=2, symbol="Am", confidence=0.8,
                    label_candidates=[
                        ChordLabelCandidate(label="Am", score=0.8, acoustic_rank=1, decoder_selected=True),
                        ChordLabelCandidate(label="C", score=0.6, acoustic_rank=2),
                    ],
                )],
                key="A",
                mode="minor",
                confidence=0.75,
                engine="legacy-test",
                engine_version="2",
            )

    timing = TimingResult(
        run=AnalyzerRun(engine="timing-test", engine_version="1"),
        candidates=[TimingCandidate(bpm=120, beats=[0, 0.5, 1, 1.5], downbeats=[0])],
    )
    adapter = CanonicalChordAnalyzerAdapter(LegacyAnalyzer())

    result = await adapter.analyze_candidates(normalized_audio, timing)
    projected = adapter.project(result)

    assert result.run.parameters["timing_engine"] == "timing-test"
    assert result.run.parameters["decoder_change_threshold"] == 0.12
    assert result.regions[0].label == "Am"
    assert [candidate.label for candidate in result.regions[0].label_candidates] == ["Am", "C"]
    assert projected.key == "A"
    assert projected.mode == "minor"
    assert projected.chords[0].symbol == "Am"
    assert projected.chords[0].label_candidates[0].decoder_selected is True
    assert projected.parameters["decoder_change_threshold"] == 0.12
