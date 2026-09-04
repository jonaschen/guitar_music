import pytest
from app.analyzers.melody.basic_pitch_adapter import BasicPitchMelodyAnalyzer

@pytest.mark.asyncio
async def test_basic_pitch_analyzer(normalized_audio, sample_beat_analysis):
    analyzer = BasicPitchMelodyAnalyzer()
    
    try:
        import basic_pitch
        analysis = await analyzer.analyze(normalized_audio, sample_beat_analysis)
        
        assert len(analysis.notes) > 0
        assert analysis.engine == "basic_pitch"
        
        for n in analysis.notes:
            assert 20 <= n.midi <= 108
            assert len(n.note) >= 2
    except ImportError:
        with pytest.raises((ImportError, RuntimeError)):
            await analyzer.analyze(normalized_audio, sample_beat_analysis)
