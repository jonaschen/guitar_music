"""Immutable experimental harmony overlay; no beat or source-audio changes."""
import hashlib
import json
from math import isfinite

from app.exporters.midi import PlaybackManifest


def _time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value >= 0


def overlay_harmony(manifest: PlaybackManifest, spans: list[dict], moves: dict,
                    expected_revision: str) -> PlaybackManifest:
    if manifest.revision != expected_revision:
        raise ValueError("Stale manifest revision")
    ids = [event.id for event in manifest.events]
    if len(ids) != len(set(ids)):
        raise ValueError("Event IDs must be unique")
    for i, span in enumerate(spans):
        if (set(span) != {"start", "end", "reference_source_id"}
                or not _time(span["start"]) or not _time(span["end"])
                or span["end"] <= span["start"] or span["end"] > manifest.duration_seconds
                or not isinstance(span["reference_source_id"], str) or not span["reference_source_id"]):
            raise ValueError("Invalid harmony span")
        if i and spans[i - 1]["end"] != span["start"]:
            raise ValueError("Spans must be ordered, contiguous and nonoverlapping")
    guitar = sorted((event for event in manifest.events if event.track == "guitar"), key=lambda e: e.start)
    by_id = {event.id: event for event in guitar}
    if any(key not in by_id or not _time(value) for key, value in moves.items()):
        raise ValueError("Moves must target existing guitar events with finite nonnegative times")
    templates = {}
    for event in guitar:
        key = (event.source_id, event.stroke)
        # Repeated strokes can have different metrical accents. Select the
        # earliest original same-stroke template deterministically.
        templates.setdefault(key, event)
    for span in spans:
        if not any(event.source_id == span["reference_source_id"] for event in guitar):
            raise ValueError("Unknown reference source")
    starts = [moves.get(event.id, event.start) for event in guitar]
    if any(time >= manifest.duration_seconds for time in starts):
        raise ValueError("Guitar start outside performance")
    if any(right <= left for left, right in zip(starts, starts[1:])):
        raise ValueError("Moves cross or collide with guitar attacks")
    if moves and not spans:
        raise ValueError("Moves require an overlay span")
    for event, start in zip(guitar, starts):
        if start != event.start and not any(span["start"] <= start < span["end"] for span in spans):
            raise ValueError("Moved attack must land inside overlay")

    changed = {}
    for i, (event, start) in enumerate(zip(guitar, starts)):
        span = next((s for s in spans if s["start"] <= start < s["end"]), None)
        updates = {}
        if span is not None:
            key = (span["reference_source_id"], event.stroke)
            if key not in templates:
                raise ValueError("Missing same-stroke reference template")
            if event.source_id == span["reference_source_id"]:
                pitches, offsets, velocities = event.pitches, event.pitch_offsets, event.pitch_velocities
            else:
                template = templates[key]
                pitches, offsets = template.pitches, template.pitch_offsets
                ratio = event.velocity / template.velocity
                velocities = tuple(max(1, min(127, round(
                    (template.pitch_velocities[j] if j < len(template.pitch_velocities)
                     else template.velocity) * ratio))) for j in range(len(pitches)))
            updates = dict(start=start, end=min(starts[i + 1] if i + 1 < len(starts) else span["end"], span["end"]),
                           sustain_end=span["end"], source_id=span["reference_source_id"],
                           pitches=pitches, pitch_offsets=offsets, pitch_velocities=velocities)
        else:
            # Clip an outside voice at the first overlay boundary it crosses.
            boundary = next((s["start"] for s in spans if s["start"] > start), None)
            if boundary is not None:
                if event.end > boundary:
                    updates["end"] = boundary
                if event.sustain_end is not None and event.sustain_end > boundary:
                    updates["sustain_end"] = boundary
        updated = event.model_copy(update=updates)
        if updates:
            offsets = [updated.pitch_offsets[j] if j < len(updated.pitch_offsets) else 0
                       for j in range(len(updated.pitches))]
            if (not updated.pitches or any(not _time(offset) for offset in offsets)
                    or updated.start + max(offsets, default=0) >= updated.end
                    or (updated.sustain_end is not None and updated.end > updated.sustain_end)):
                raise ValueError("Overlay clips or collides with a strum's string attacks")
        changed[event.id] = updated
    events = tuple(sorted((changed.get(e.id, e) for e in manifest.events),
                          key=lambda e: (e.start, e.track, e.id)))
    payload = dict(base=manifest.revision, operation="harmony-overlay-v2-accent-preserving", spans=spans, moves=moves)
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]
    return manifest.model_copy(update=dict(revision=revision, events=events))
