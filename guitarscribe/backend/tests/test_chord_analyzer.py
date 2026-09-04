import pytest
from app.analyzers.chords.chromagram import ChromagramChordAnalyzer
from app.analyzers.chords.chordino import ChordinoChordAnalyzer

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
