import numpy as np
import pytest
from app.analyzers.melody.basic_pitch_adapter import BasicPitchMelodyAnalyzer, _parse_note_event

@pytest.mark.asyncio
async def test_basic_pitch_analyzer(normalized_audio, sample_beat_analysis):
    analyzer = BasicPitchMelodyAnalyzer()
    
    try:
        import basic_pitch
        analysis = await analyzer.analyze(normalized_audio, sample_beat_analysis)
        
        assert analysis.engine == "basic_pitch"
        assert analysis.notes or analysis.warnings
        
        for n in analysis.notes:
            assert 20 <= n.midi <= 108
            assert len(n.note) >= 2
    except ImportError:
        with pytest.raises((ImportError, RuntimeError)):
            await analyzer.analyze(normalized_audio, sample_beat_analysis)


def test_basic_pitch_sequence_amplitude_is_not_used_as_confidence():
    parsed = _parse_note_event((0.0, 0.4, 60, 0.12, [0]))

    assert parsed is not None
    assert parsed[0] == 0.0
    assert parsed[1] == pytest.approx(0.4)
    assert parsed[2:] == (60, 0.65)


def test_basic_pitch_accepts_numpy_note_values():
    parsed = _parse_note_event((np.float32(0), np.float32(0.4), np.int64(60), np.float32(0.12)))

    assert parsed is not None
    assert parsed[0] == 0.0
    assert parsed[1] == pytest.approx(0.4)
    assert parsed[2:] == (60, 0.65)
