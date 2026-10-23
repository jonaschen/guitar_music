from copy import deepcopy

import pytest

from app.evaluation.harmony_overlay import overlay_harmony
from app.exporters.midi import PlaybackEvent, PlaybackManifest


def fixture():
    def guitar(id, start, source, stroke, pitches):
        return PlaybackEvent(id=id, track="guitar", start=start, end=start + .8,
                             sustain_end=5, source_id=source, stroke=stroke, pitches=pitches,
                             pitch_offsets=(0, .02), pitch_velocities=(90, 70), velocity=85)
    return PlaybackManifest(revision="base", duration_seconds=6, bpm=120, time_signature="4/4", events=(
        guitar("pre", 0, "c", "D", (48, 60)),
        guitar("d", 1, "c", "D", (48, 60)),
        guitar("u", 2, "c", "U", (60, 48)),
        guitar("gd", 4, "g", "D", (55, 67)),
        guitar("gu", 5, "g", "U", (67, 55)),
        PlaybackEvent(id="mel", track="melody", start=1, end=3, pitches=(72,)),
        PlaybackEvent(id="click", track="metronome", start=1, end=1.1, pitches=(84,)),
    ))


def test_maps_up_down_templates_clips_prior_voice_and_preserves_inputs():
    original = fixture()
    before = original.model_dump_json()
    spans = [dict(start=.5, end=3, reference_source_id="g")]
    moves = {"d": 1.15}
    snapshot = deepcopy((spans, moves))
    result = overlay_harmony(original, spans, moves, "base")
    events = {event.id: event for event in result.events}
    assert events["d"].pitches == (55, 67)
    assert events["u"].pitches == (67, 55)
    assert events["d"].start == 1.15 and events["d"].end == 2
    assert events["u"].end == events["u"].sustain_end == 3
    assert events["d"].source_id == "g" and events["d"].velocity == 85
    assert events["d"].pitch_offsets == (0, .02)
    assert events["pre"].end == events["pre"].sustain_end == .5
    for id in ("gd", "gu", "mel", "click"):
        assert events[id] == next(e for e in original.events if e.id == id)
    assert original.model_dump_json() == before
    assert (spans, moves) == snapshot
    assert result.revision != original.revision


@pytest.mark.parametrize("moves", [{"d": 2}, {"d": 2.1}, {"mel": 1.2}, {"d": float("nan")}, {"d": 1.99}])
def test_rejects_crossing_collision_invalid_and_string_collision(moves):
    with pytest.raises(ValueError):
        overlay_harmony(fixture(), [dict(start=.5, end=3, reference_source_id="g")], moves, "base")


def test_rejects_stale_and_discontinuous_spans():
    with pytest.raises(ValueError, match="Stale"):
        overlay_harmony(fixture(), [], {}, "old")
    with pytest.raises(ValueError, match="contiguous"):
        overlay_harmony(fixture(), [dict(start=.5, end=2, reference_source_id="g"),
                                    dict(start=2.1, end=3, reference_source_id="c")], {}, "base")


def test_rejects_clipping_preceding_string_attack():
    with pytest.raises(ValueError, match="string attacks"):
        overlay_harmony(fixture(), [dict(start=.01, end=3, reference_source_id="g")], {}, "base")


def test_same_source_preserves_individual_stroke_accent_and_mapping():
    original = fixture()
    original = original.model_copy(update={"events": tuple(
        e.model_copy(update=dict(pitches=(50, 62), pitch_offsets=(0, .03),
                                 pitch_velocities=(52, 41), velocity=50)) if e.id == "d" else e
        for e in original.events)})
    result = overlay_harmony(original, [dict(start=.5, end=3, reference_source_id="c")], {}, "base")
    event = next(e for e in result.events if e.id == "d")
    assert event.pitches == (50, 62)
    assert event.pitch_offsets == (0, .03)
    assert event.pitch_velocities == (52, 41)
    assert event.velocity == 50


def test_changed_source_scales_template_velocities_and_clamps():
    original = fixture()
    original = original.model_copy(update={"events": tuple(
        e.model_copy(update=dict(velocity=127)) if e.id == "d" else
        e.model_copy(update=dict(velocity=1)) if e.id == "u" else
        e.model_copy(update=dict(velocity=50, pitch_velocities=(100, 40))) if e.id == "gd" else
        e.model_copy(update=dict(velocity=100, pitch_velocities=(10, 1))) if e.id == "gu" else e
        for e in original.events)})
    result = overlay_harmony(original, [dict(start=.5, end=3, reference_source_id="g")], {}, "base")
    events = {e.id: e for e in result.events}
    assert events["d"].pitch_velocities == (127, 102)
    assert events["d"].velocity == 127
    assert events["u"].pitch_velocities == (1, 1)
    assert events["u"].velocity == 1
