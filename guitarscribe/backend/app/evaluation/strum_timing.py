"""Explicit, immutable performance candidates; never alters a saved score or beat grid."""
import hashlib
import json

from pydantic import BaseModel, Field, model_validator

from app.exporters.midi import PlaybackManifest


class FirstStrumDelay(BaseModel):
    source_id: str
    expected_start: float = Field(ge=0, allow_inf_nan=False)
    delay_seconds: float = Field(gt=0, le=0.5, allow_inf_nan=False)


def apply_first_strum_delays(
    manifest: PlaybackManifest, adjustments: list[FirstStrumDelay], *, expected_revision: str,
) -> PlaybackManifest:
    """Delay selected first strums and prior harmony releases, keeping later attacks fixed.

    Anchors must match the exact compiled performance. Reject stale selections and
    changes that would collide with the next attack; do not silently clamp or snap.
    This is an evaluation operation, not an automatic chord correction.
    """
    if manifest.revision != expected_revision:
        raise ValueError("Performance changed; regenerate timing candidate")
    if not adjustments:
        return manifest
    moves = {}
    guitar = sorted((event for event in manifest.events if event.track == "guitar"), key=lambda event: event.start)
    for change in adjustments:
        first = next((event for event in guitar if event.source_id == change.source_id), None)
        if first is None or first.start != change.expected_start:
            raise ValueError("First strum anchor no longer matches")
        if first.start in moves:
            raise ValueError("Duplicate first strum adjustment")
        if sum(event.start == first.start for event in guitar) != 1:
            raise ValueError("Ambiguous simultaneous guitar attacks")
        moves[first.start] = first.start + change.delay_seconds

    events = []
    for event in manifest.events:
        if event.track != "guitar":
            events.append(event)
            continue
        start = moves.get(event.start, event.start)
        end = moves.get(event.end, event.end)
        sustain = moves.get(event.sustain_end, event.sustain_end)
        if start != event.start:
            following = next((other.start for other in guitar if other.start > event.start), None)
            latest_string = start + max(event.pitch_offsets, default=0)
            if latest_string >= end or (following is not None and latest_string >= following):
                raise ValueError("Delayed strum would overlap the next attack")
            if sustain is not None and latest_string >= sustain:
                raise ValueError("Delayed strum would outlast its harmony")
        events.append(event.model_copy(update={"start": start, "end": end, "sustain_end": sustain}))
    events.sort(key=lambda event: (event.start, event.track, event.id))
    digest = hashlib.sha256(json.dumps({
        "base": manifest.revision,
        "operation": "explicit-first-strum-delay-v1",
        "adjustments": [change.model_dump() for change in adjustments],
    }, sort_keys=True).encode()).hexdigest()[:16]
    return manifest.model_copy(update={"revision": digest, "events": tuple(events)})


class LocalGuitarTiming(BaseModel):
    """Local spacing change followed by constant displacement, for evaluation only."""
    anchor: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    spacing: float = Field(ge=0.9, le=1.1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered_window(self):
        if self.end <= self.anchor:
            raise ValueError("Local timing end must be after its anchor")
        return self

    def at(self, time: float) -> float:
        if time <= self.anchor:
            return time
        if time < self.end:
            return self.anchor + (time - self.anchor) * self.spacing
        # Never reset accumulated displacement abruptly at the exit boundary.
        return time + (self.end - self.anchor) * (self.spacing - 1)


def apply_local_guitar_timing(
    manifest: PlaybackManifest, timing: LocalGuitarTiming, *, expected_revision: str,
) -> PlaybackManifest:
    """Preserve Y inside its window; continue at original spacing with an explicit offset.

    This continuation is a new hypothesis, NOT a human-approved whole-song correction.
    No beat, source, melody or global BPM is changed. Consumers must label the
    downstream displacement and verify it before integrating a saved-score feature.
    """
    if manifest.revision != expected_revision:
        raise ValueError("Performance changed; regenerate timing candidate")
    if timing.end > manifest.duration_seconds:
        raise ValueError("Local timing window exceeds source performance")
    if timing.spacing == 1:
        return manifest
    events = []
    for event in manifest.events:
        if event.track != "guitar":
            events.append(event)
            continue
        start, end = timing.at(event.start), timing.at(event.end)
        sustain = None if event.sustain_end is None else timing.at(event.sustain_end)
        latest_string = start + max(event.pitch_offsets, default=0)
        if latest_string >= end or (sustain is not None and latest_string >= sustain):
            raise ValueError("Local timing would truncate a strum")
        events.append(event.model_copy(update={"start": start, "end": end, "sustain_end": sustain}))
    events.sort(key=lambda event: (event.start, event.track, event.id))
    duration = max([manifest.duration_seconds, *(e.sustain_end or e.end for e in events)])
    digest = hashlib.sha256(json.dumps({
        "base": manifest.revision, "operation": "local-spacing-with-carried-offset-v1",
        "timing": timing.model_dump(),
    }, sort_keys=True).encode()).hexdigest()[:16]
    return manifest.model_copy(update={"revision": digest, "events": tuple(events), "duration_seconds": duration})
