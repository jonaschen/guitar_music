import pytest

from app.analyzers.melody.pyin_adapter import frames_to_notes


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
