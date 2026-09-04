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
