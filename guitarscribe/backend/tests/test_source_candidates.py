import numpy as np
import pytest

from app.evaluation.source_candidates import select_path, spectral_candidates, RATE


def test_path_keeps_silence_and_uses_only_observed_candidates():
    frames = [[(440,1),(880,.9)],[(440,.9),(880,1)],[],[(660,1)]]
    result = select_path(frames)
    assert result[0] == result[1]
    assert result[2] is None and result[3] == 660
    assert all(hz is None or hz in [p for p,_ in row] for hz,row in zip(result,frames))
    alternate = select_path(frames,result)
    assert alternate[0] != result[0]
    assert alternate[2] is None


def test_spectral_path_recovers_synthetic_tone_above_stronger_bass():
    times = np.arange(RATE)/RATE
    samples = .6*np.sin(2*np.pi*110*times)+.2*np.sin(2*np.pi*440*times)
    frames = spectral_candidates(samples)
    chosen = select_path(frames)
    assert np.median([hz for hz in chosen[5:-5] if hz is not None]) == pytest.approx(440,abs=2)
    assert all(len(row)<=6 for row in frames)
    assert all(196<=hz<=1568 for row in frames for hz,_ in row)


def test_spectral_silence_does_not_invent_melody():
    frames = spectral_candidates(np.zeros(RATE))
    assert all(not row for row in frames)
    assert all(hz is None for hz in select_path(frames))
