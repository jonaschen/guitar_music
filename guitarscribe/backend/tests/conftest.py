import pytest
import numpy as np
import soundfile as sf
from pathlib import Path
from app.models.audio import NormalizedAudio
from app.models.analysis import BeatAnalysis, BeatInfo, ChordAnalysis, ChordEvent

def generate_test_audio(path, sr=44100, duration=8.0, bpm=120):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = np.zeros_like(t)
    
    chords = [
        (0.0, 2.0, [261.63, 329.63, 392.00]),
        (2.0, 4.0, [196.00, 246.94, 293.66]),
        (4.0, 6.0, [220.00, 261.63, 329.63]),
        (6.0, 8.0, [174.61, 220.00, 261.63]),
    ]
    
    for start, end, freqs in chords:
        mask = (t >= start) & (t < end)
        for freq in freqs:
            audio[mask] += 0.2 * np.sin(2 * np.pi * freq * t[mask])
    
    melody_notes = [
        (0.5, 1.0, 523.25),
        (1.0, 1.5, 493.88),
        (2.5, 3.0, 392.00),
        (3.0, 3.5, 440.00),
        (4.5, 5.0, 329.63),
        (5.5, 6.0, 349.23),
        (6.5, 7.0, 261.63),
        (7.0, 7.5, 293.66),
    ]
    for start, end, freq in melody_notes:
        mask = (t >= start) & (t < end)
        audio[mask] += 0.3 * np.sin(2 * np.pi * freq * t[mask])
    
    audio = audio / np.max(np.abs(audio)) * 0.9
    sf.write(str(path), audio, sr, subtype='PCM_16')
    return path

@pytest.fixture
def sample_wav(tmp_path):
    wav_path = tmp_path / "test.wav"
    generate_test_audio(wav_path)
    return wav_path

@pytest.fixture
def normalized_audio(sample_wav):
    return NormalizedAudio(
        path=sample_wav,
        sample_rate=44100,
        channels=1,
        duration_seconds=8.0,
        bit_depth=16
    )

@pytest.fixture
def sample_beat_analysis():
    return BeatAnalysis(
        bpm=120.0,
        beats=[
            BeatInfo(time=0.0, beat=1, measure=1),
            BeatInfo(time=0.5, beat=2, measure=1),
            BeatInfo(time=1.0, beat=3, measure=1),
            BeatInfo(time=1.5, beat=4, measure=1),
        ],
        engine="test"
    )

@pytest.fixture
def sample_chord_analysis():
    return ChordAnalysis(
        chords=[
            ChordEvent(id="1", start=0.0, end=1.9, symbol="C"),
            ChordEvent(id="2", start=1.9, end=2.1, symbol="C"),
            ChordEvent(id="3", start=2.1, end=4.0, symbol="Gmaj7"),
        ],
        engine="test"
    )
