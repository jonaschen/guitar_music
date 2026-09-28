import numpy as np
import pytest
import soundfile as sf

from app.evaluation.pitch_contour import render_pitch_contour


def test_contour_preserves_pitch_and_silence_at_absolute_time(tmp_path):
    path = tmp_path / "contour.wav"
    values = [440, 440, None, 660, 660]
    render_pitch_contour(values, 0.1, 40, 40, 40.6, path)
    audio, sr = sf.read(path)
    assert len(audio) == round(0.6 * sr)
    assert not np.any(audio[int(0.2 * sr):int(0.3 * sr)])
    assert not np.any(audio[int(0.5 * sr):])
    for left, right, expected in [(0.02, 0.18, 440), (0.32, 0.48, 660)]:
        samples = audio[int(left * sr):int(right * sr)]
        spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
        frequency = np.fft.rfftfreq(len(samples), 1 / sr)[np.argmax(spectrum)]
        assert abs(frequency - expected) < 5
    assert max(abs(audio)) <= 0.301
    assert values == [440, 440, None, 660, 660]


def test_contour_keeps_fractional_pitch_not_rounded_notes(tmp_path):
    path = tmp_path / "fractional.wav"
    render_pitch_contour([450] * 10, 0.1, 0, 0, 1, path)
    audio, sr = sf.read(path)
    peak = np.argmax(np.abs(np.fft.rfft(audio)))
    assert np.fft.rfftfreq(len(audio), 1 / sr)[peak] == 450


def test_empty_and_invalid_contours(tmp_path):
    path = tmp_path / "empty.wav"
    render_pitch_contour([], 0.1, 0, 0, 1, path)
    assert not np.any(sf.read(path)[0])
    for values, hop in [([float("nan")], 0.1), ([0], 0.1), ([9000], 0.1), ([440], 0)]:
        with pytest.raises(ValueError):
            render_pitch_contour(values, hop, 0, 0, 1, path)
