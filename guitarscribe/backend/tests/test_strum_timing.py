import pytest

from app.evaluation.strum_timing import FirstStrumDelay, apply_first_strum_delays
from app.exporters.midi import PlaybackEvent, PlaybackManifest, export_manifest_midi, export_midi, compile_playback_manifest
from app.models.score import SongScore


def fixture():
    return PlaybackManifest(revision="base", duration_seconds=4, bpm=120, time_signature="4/4", events=(
        PlaybackEvent(id="old", track="guitar", start=0, end=1, sustain_end=1, pitches=(48,), source_id="c"),
        PlaybackEvent(id="new", track="guitar", start=1, end=1.5, sustain_end=3, pitches=(55, 59), pitch_offsets=(0, .012), source_id="g"),
        PlaybackEvent(id="melody", track="melody", start=1, end=2, pitches=(72,), source_id="n"),
        PlaybackEvent(id="repeat", track="guitar", start=1.5, end=2, sustain_end=3, pitches=(55,), source_id="g"),
    ))


def adjust(m, **kwargs):
    return apply_first_strum_delays(m, [FirstStrumDelay(source_id="g", expected_start=1, delay_seconds=.15, **kwargs)], expected_revision="base")


def test_local_adjustment_preserves_other_attacks_and_updates_release():
    original = fixture()
    before = original.model_dump_json()
    updated = adjust(original)
    events = {e.id: e for e in updated.events}
    assert events["new"].start == 1.15
    assert events["old"].end == events["old"].sustain_end == 1.15
    assert events["repeat"] == original.events[3]
    assert events["melody"] == original.events[2]
    assert events["new"].pitch_offsets == original.events[1].pitch_offsets
    assert original.model_dump_json() == before
    assert updated.revision != original.revision
    assert PlaybackManifest.model_validate_json(updated.model_dump_json()) == updated


@pytest.mark.parametrize("source,start,delay,revision", [("g", 1, .15, "stale"), ("missing", 1, .15, "base"), ("g", 1.5, .15, "base"), ("g", 1, .5, "base")])
def test_rejects_stale_anchors_nonfirst_strokes_and_collisions(source, start, delay, revision):
    with pytest.raises(ValueError):
        apply_first_strum_delays(fixture(), [FirstStrumDelay(source_id=source, expected_start=start, delay_seconds=delay)], expected_revision=revision)


def test_duplicate_adjustment_is_rejected():
    change = FirstStrumDelay(source_id="g", expected_start=1, delay_seconds=.15)
    with pytest.raises(ValueError, match="Duplicate"):
        apply_first_strum_delays(fixture(), [change, change], expected_revision="base")


def test_default_midi_path_is_unchanged():
    score = SongScore()
    assert export_midi(score) == export_manifest_midi(compile_playback_manifest(score))


def test_adjusted_midi_contains_same_notes_with_later_guitar_onset():
    # Tiny format-0 reader for the emitted stream; verifies tick positions, not byte substrings.
    data = export_manifest_midi(adjust(fixture()))
    pos, tick, notes = 22, 0, []
    def varlen():
        nonlocal pos
        value = 0
        while True:
            byte = data[pos]; pos += 1
            value = (value << 7) | (byte & 127)
            if byte < 128:
                return value
    while pos < len(data):
        tick += varlen()
        status = data[pos]; pos += 1
        if status == 255:
            pos += 1
            length = varlen(); pos += length
        elif status & 240 == 192:
            pos += 1
        else:
            pitch, velocity = data[pos:pos+2]; pos += 2
            if status & 240 == 144:
                notes.append((status & 15, pitch, tick, velocity))
    assert [(ch, pitch, tick) for ch, pitch, tick, _ in notes] == [
        (1, 48, 0), (0, 72, 960), (1, 55, 1104), (1, 59, 1116), (1, 55, 1440),
    ]
