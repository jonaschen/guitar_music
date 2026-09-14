import pytest
from app.analyzers.beats.librosa_beats import LibrosaBeatAnalyzer

@pytest.mark.asyncio
async def test_librosa_beat_analyzer(normalized_audio):
    analyzer = LibrosaBeatAnalyzer()
    analysis = await analyzer.analyze(normalized_audio)
    
    assert 60 <= analysis.bpm <= 200
    assert len(analysis.beats) > 0
    assert analysis.engine == "librosa"
    
    # check sequential measures
    for i in range(1, len(analysis.beats)):
        assert analysis.beats[i].time >= analysis.beats[i-1].time
        
    assert analysis.beats[0].measure == 1
    assert "not downbeats" in analysis.warnings[0]


@pytest.mark.asyncio
async def test_librosa_candidate_adapter_keeps_tempo_and_phase_ambiguity(normalized_audio):
    result = await LibrosaBeatAnalyzer().analyze_candidates(normalized_audio)

    assert result.run.engine == "librosa"
    assert result.run.engine_version
    assert len(result.candidates) == 12
    assert {round(candidate.bpm / result.candidates[0].bpm, 1) for candidate in result.candidates} == {0.5, 1.0, 2.0}
    assert {candidate.phase for candidate in result.candidates} == {0, 1, 2, 3}
    assert all(candidate.downbeats == candidate.beats[candidate.phase::4] for candidate in result.candidates)
    assert result.candidates[0].confidence < 0.5
