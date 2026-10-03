import pytest
import numpy as np
import soundfile as sf

from app.analyzers.melody.pyin_adapter import PYIN_HOP_LENGTH, PYIN_RESOLUTION, PYIN_THRESHOLDS, PYIN_SAMPLE_RATE, PyinVocalMelodyAnalyzer, frames_to_notes
from app.models.analysis import BeatAnalysis, MelodyMode
from app.models.audio import NormalizedAudio


def test_pyin_cpu_profile_matches_the_semitone_score_resolution():
    assert PYIN_HOP_LENGTH == 512
    assert PYIN_RESOLUTION == 0.5
    assert PYIN_THRESHOLDS == 32
    assert PYIN_SAMPLE_RATE == 22050


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


def test_pyin_frames_preserve_low_voiced_probability_for_downstream_filtering():
    notes = frames_to_notes([60.0, 60.0, 60.0], [0.12, 0.18, 0.15], hop_seconds=0.05)

    assert len(notes) == 1
    assert notes[0].confidence == pytest.approx(0.15)


def test_sustained_semitone_motion_is_not_flattened_into_one_note():
    notes = frames_to_notes([64.] * 8 + [65.] * 8 + [64.] * 8, [.9] * 24, hop_seconds=.025)
    assert [n.midi for n in notes] == [64, 65, 64]
    assert [t for n in notes for t in (n.start, n.end)] == pytest.approx([0, .2, .2, .4, .4, .6])


def test_brief_semitone_vibrato_does_not_make_many_short_notes():
    notes = frames_to_notes([64., 64., 65., 64., 63., 64.] * 8, [.9] * 48, hop_seconds=.025)
    assert len(notes) == 1
    assert notes[0].midi == 64
    assert notes[0].end == pytest.approx(1.2)


@pytest.mark.parametrize("hop,duration", [(0,.1), (.02,0), (float("nan"),.1), (.02,float("inf"))])
def test_frame_decoder_rejects_invalid_timing(hop,duration):
    with pytest.raises(ValueError,match="finite and positive"):
        frames_to_notes([60.]*10,[.9]*10,hop_seconds=hop,min_duration=duration)


def test_source_timed_processing_preserves_repeated_notes_rests_and_off_grid_boundaries():
    from app.postprocess.melody import MelodyPostProcessor
    values = [64.] * 8 + [None] * 2 + [64.] * 8 + [65.] * 8
    notes = frames_to_notes(values, [.9] * len(values), hop_seconds=.02322)
    original = [n.model_dump() for n in notes]
    result = MelodyPostProcessor().process_source_timed(notes)
    assert [n.model_dump() for n in result] == original
    assert len(result) == 3
    assert result[1].start - result[0].end == pytest.approx(.04644)
    result[0].end = .1
    assert [n.model_dump() for n in notes] == original


@pytest.mark.asyncio
@pytest.mark.parametrize("sample_rate", [22050, 44100])
async def test_pyin_analyzes_a_short_monophonic_voice_like_fixture(tmp_path, sample_rate):
    time = np.arange(sample_rate * 2) / sample_rate
    path = tmp_path / "voice.wav"
    sf.write(path, 0.5 * np.sin(2 * np.pi * 440 * time), sample_rate)
    audio = NormalizedAudio(path=path, sample_rate=sample_rate, channels=1, duration_seconds=2.0)

    analysis = await PyinVocalMelodyAnalyzer().analyze(audio, BeatAnalysis(bpm=120))

    assert analysis.engine == "pyin_vocal"
    assert analysis.mode == MelodyMode.VOCAL
    assert analysis.notes
    assert analysis.contour is not None
    assert analysis.contour.source_artifact_kind == "audio"
    assert analysis.contour.source_end == 2
    assert analysis.contour.hop_seconds == PYIN_HOP_LENGTH / PYIN_SAMPLE_RATE
    assert any(hz is not None for hz in analysis.contour.frequencies_hz)
    assert "contour" not in analysis.model_dump()
