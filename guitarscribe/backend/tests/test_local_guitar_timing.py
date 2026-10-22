import pytest
from pydantic import ValidationError

from app.evaluation.strum_timing import LocalGuitarTiming, apply_local_guitar_timing
from app.exporters.midi import PlaybackEvent, PlaybackManifest


def manifest_fixture():
    return PlaybackManifest(
        revision="source-revision",
        duration_seconds=4.8,
        bpm=120,
        time_signature="4/4",
        events=(
            PlaybackEvent(
                id="guitar-before",
                track="guitar",
                start=0.5,
                end=0.75,
                sustain_end=0.8,
                pitches=(48, 52),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="D",
                source_id="chord-before",
            ),
            PlaybackEvent(
                id="guitar-at-anchor",
                track="guitar",
                start=1,
                end=1.25,
                sustain_end=1.3,
                pitches=(50, 57),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="D",
                source_id="chord-a",
            ),
            PlaybackEvent(
                id="guitar-inside",
                track="guitar",
                start=1.5,
                end=1.75,
                sustain_end=1.9,
                pitches=(52, 59),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="U",
                source_id="chord-b",
            ),
            PlaybackEvent(
                id="guitar-crosses-end",
                track="guitar",
                start=2.8,
                end=3.4,
                sustain_end=3.5,
                pitches=(48, 55),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="D",
                source_id="chord-c",
            ),
            PlaybackEvent(
                id="guitar-at-end",
                track="guitar",
                start=3,
                end=3.2,
                sustain_end=3.25,
                pitches=(45, 52),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="U",
                source_id="chord-d",
            ),
            PlaybackEvent(
                id="guitar-after",
                track="guitar",
                start=4.6,
                end=4.7,
                sustain_end=4.75,
                pitches=(43, 50),
                pitch_offsets=(0, 0.012),
                pitch_velocities=(90, 88),
                velocity=90,
                stroke="D",
                source_id="chord-after",
            ),
            PlaybackEvent(
                id="melody-inside",
                track="melody",
                start=1.5,
                end=1.9,
                pitches=(72,),
                source_id="note-inside",
            ),
            PlaybackEvent(
                id="metronome-after",
                track="metronome",
                start=4.6,
                end=4.65,
                pitches=(76,),
                source_id="beat-after",
            ),
        ),
    )


def apply(manifest, *, spacing=1.04, anchor=1, end=3, expected_revision="source-revision"):
    timing = LocalGuitarTiming(anchor=anchor, end=end, spacing=spacing)
    return apply_local_guitar_timing(manifest, timing, expected_revision=expected_revision)


def by_id(manifest):
    return {event.id: event for event in manifest.events}


def test_maps_guitar_event_times_piecewise_and_keeps_post_region_spacing():
    source = manifest_fixture()
    mapped = by_id(apply(source))

    # Before the anchor stays fixed; the region is scaled about its anchor.
    assert mapped["guitar-before"].start == source.events[0].start
    assert mapped["guitar-at-anchor"].start == 1
    assert mapped["guitar-inside"].start == pytest.approx(1.52)
    assert mapped["guitar-inside"].end == pytest.approx(1.78)
    assert mapped["guitar-inside"].sustain_end == pytest.approx(1.936)
    assert mapped["guitar-crosses-end"].start == pytest.approx(2.872)
    assert mapped["guitar-crosses-end"].end == pytest.approx(3.48)
    assert mapped["guitar-crosses-end"].sustain_end == pytest.approx(3.58)

    # The map is continuous at end; post-region times keep their spacing by
    # receiving the fixed total delta rather than being connected to a later beat.
    assert mapped["guitar-at-end"].start == pytest.approx(3.08)
    assert mapped["guitar-after"].start == pytest.approx(4.68)
    assert mapped["guitar-after"].end == pytest.approx(4.78)
    assert mapped["guitar-after"].sustain_end == pytest.approx(4.83)
    assert mapped["guitar-after"].end - mapped["guitar-after"].start == pytest.approx(
        source.events[5].end - source.events[5].start
    )


def test_supports_faster_spacing_without_reversing_or_reordering_events():
    source = manifest_fixture()
    mapped = by_id(apply(source, spacing=0.96))

    assert mapped["guitar-inside"].start == pytest.approx(1.48)
    assert mapped["guitar-at-end"].start == pytest.approx(2.92)
    assert mapped["guitar-after"].start == pytest.approx(4.52)
    assert mapped["guitar-after"].end - mapped["guitar-after"].start == pytest.approx(0.1)
    starts = [event.start for event in sorted(mapped.values(), key=lambda event: event.start)]
    assert all(left < right for left, right in zip(starts, starts[1:]))


def test_time_mapping_is_continuous_at_anchor_and_end():
    source = PlaybackManifest(
        revision="source-revision",
        duration_seconds=5,
        bpm=120,
        time_signature="4/4",
        events=tuple(
            PlaybackEvent(
                id=f"g-{time}", track="guitar", start=time, end=time + 0.01,
                pitches=(48,), source_id=f"c-{time}",
            )
            for time in (0.999, 1, 1.001, 2.999, 3, 3.001)
        ),
    )
    mapped = sorted(apply(source).events, key=lambda event: event.start)
    starts = [event.start for event in mapped]

    assert starts[0] == pytest.approx(0.999)
    assert starts[1] == pytest.approx(1)
    assert starts[2] == pytest.approx(1.00104)
    assert starts[3] == pytest.approx(3.07896)
    assert starts[4] == pytest.approx(3.08)
    assert starts[5] == pytest.approx(3.081)
    assert all(left < right for left, right in zip(starts, starts[1:]))


def test_preserves_event_order_and_all_non_guitar_events():
    source = manifest_fixture()
    mapped = apply(source)
    source_guitar_order = [event.id for event in source.events if event.track == "guitar"]
    mapped_guitar_order = [event.id for event in mapped.events if event.track == "guitar"]
    source_non_guitar = [event for event in source.events if event.track != "guitar"]
    mapped_non_guitar = [event for event in mapped.events if event.track != "guitar"]

    assert mapped_guitar_order == source_guitar_order
    assert mapped_non_guitar == source_non_guitar
    assert len(mapped.events) == len(source.events)
    assert all(event.end >= event.start for event in mapped.events)


def test_duration_extends_to_cover_last_mapped_guitar_event():
    source = manifest_fixture()
    mapped = apply(source)
    latest_event_time = max(
        value
        for event in mapped.events
        for value in (event.start, event.end, event.sustain_end)
        if value is not None
    )

    assert mapped.duration_seconds >= latest_event_time
    assert mapped.duration_seconds > source.duration_seconds
    assert mapped.bpm == source.bpm
    assert mapped.time_signature == source.time_signature


def test_does_not_mutate_input_manifest_or_events():
    source = manifest_fixture()
    before = source.model_dump_json()

    mapped = apply(source)

    assert mapped is not source
    assert source.model_dump_json() == before


def test_rejects_stale_manifest_revision():
    source = manifest_fixture()

    with pytest.raises(ValueError):
        apply(source, expected_revision="different-revision")


@pytest.mark.parametrize(
    "values",
    [
        {"anchor": -0.001, "end": 3, "spacing": 1.04},
        {"anchor": 3, "end": 3, "spacing": 1.04},
        {"anchor": 4, "end": 3, "spacing": 1.04},
        {"anchor": 1, "end": 3, "spacing": 0.899},
        {"anchor": 1, "end": 3, "spacing": 1.101},
        {"anchor": 1, "end": 3, "spacing": float("nan")},
    ],
)
def test_rejects_invalid_local_timing(values):
    with pytest.raises(ValidationError):
        LocalGuitarTiming(**values)


def test_preserves_positive_duration_for_event_crossing_region_end():
    source = PlaybackManifest(
        revision="source-revision",
        duration_seconds=4,
        bpm=120,
        time_signature="4/4",
        events=(
            PlaybackEvent(
                id="guitar-crossing",
                track="guitar",
                start=1.9,
                end=3.01,
                pitches=(48,),
                source_id="chord-crossing",
            ),
        ),
    )

    # A valid positive spacing transformation should preserve, not invert,
    # an event that crosses the region end.
    mapped = apply(source)
    assert mapped.events[0].end > mapped.events[0].start

