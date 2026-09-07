import pytest
import numpy as np
import soundfile as sf

from app.analyzers.melody.pyin_adapter import PYIN_HOP_LENGTH, PYIN_RESOLUTION, PYIN_THRESHOLDS, PyinVocalMelodyAnalyzer, frames_to_notes
from app.models.analysis import BeatAnalysis, MelodyMode
from app.models.audio import NormalizedAudio


def test_pyin_cpu_profile_matches_the_semitone_score_resolution():
    assert PYIN_HOP_LENGTH == 512
    assert PYIN_RESOLUTION == 0.5
    assert PYIN_THRESHOLDS == 32


def test_pyin_frames_merge_vibrato_but_split_a_real_pitch_change():
    notes = frames_to_notes(
        [60.0, 60.4, 59.6, 62.0, 62.2, None, 64.0, 64.0],
        [0.8] * 8,
        hop_seconds=0.05,
    )

    assert [note.midi for note in notes] == [60, 62, 64]
    assert [point for note in notes for point in (note.start, note.end)] == pytest.approx(
        [0.0, 0.15, 0.15, 0.25, 0.3, 0.4]
    )
    assert all(note.confidence >= 0.45 for note in notes)


def test_pyin_frames_do_not_create_notes_from_short_or_unvoiced_noise():
    notes = frames_to_notes([None, 60.0, None], [0.0, 0.9, 0.0], hop_seconds=0.05)

    assert notes == []


@pytest.mark.asyncio
async def test_pyin_analyzes_a_short_monophonic_voice_like_fixture(tmp_path):
    sample_rate = 22050
    time = np.arange(sample_rate * 2) / sample_rate
    path = tmp_path / "voice.wav"
    sf.write(path, 0.5 * np.sin(2 * np.pi * 440 * time), sample_rate)
    audio = NormalizedAudio(path=path, sample_rate=sample_rate, channels=1, duration_seconds=2.0)

    analysis = await PyinVocalMelodyAnalyzer().analyze(audio, BeatAnalysis(bpm=120))

    assert analysis.engine == "pyin_vocal"
    assert analysis.mode == MelodyMode.VOCAL
    assert analysis.notes
