"""Canonical playback event compilation and Standard MIDI File export."""

from __future__ import annotations

import hashlib
import json
import struct
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.score import SongScore


class PlaybackEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    track: Literal["guitar", "melody", "metronome"]
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    pitches: tuple[int, ...] = ()
    # Per-pitch offsets and velocities make a guitar event an explicit strum,
    # rather than leaving each consumer to invent its own ordering.
    pitch_offsets: tuple[float, ...] = ()
    pitch_velocities: tuple[int, ...] = ()
    velocity: int = Field(default=96, ge=1, le=127)
    stroke: str | None = None
    source_id: str | None = None


class PlaybackManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision: str
    duration_seconds: float
    bpm: float
    time_signature: str
    events: tuple[PlaybackEvent, ...]


def compile_playback_manifest(score: SongScore) -> PlaybackManifest:
    events: list[PlaybackEvent] = []
    bpm = max(score.analysis.bpm, 1)

    for note in score.melody:
        events.append(PlaybackEvent(
            id=f"melody:{note.id}", track="melody", start=max(0, note.start),
            end=max(note.start + 0.01, note.end), pitches=(note.midi,),
            velocity=96, source_id=note.id,
        ))

    for index, beat in enumerate(score.beats):
        events.append(PlaybackEvent(
            id=f"metronome:{index}", track="metronome", start=max(0, beat.time),
            end=max(0, beat.time) + 0.05, pitches=(84 if beat.beat == 1 else 76,),
            velocity=112 if beat.beat == 1 else 88, source_id=str(index),
        ))

    pattern = score.rhythm.display
    if pattern:
        step_seconds = 60.0 / bpm * (4.0 / max(score.rhythm.subdivision, 1))
        for chord in score.chords:
            pitches = _selected_voicing_pitches(score, chord)
            slot = 0
            event_time = max(0, chord.start)
            while event_time < chord.end - 0.001:
                stroke = pattern[slot % len(pattern)]
                if stroke and pitches:
                    ordered_pitches = pitches if stroke != "U" else tuple(reversed(pitches))
                    offsets, velocities = _strum_profile(stroke, len(ordered_pitches))
                    events.append(PlaybackEvent(
                        id=f"guitar:{chord.id}:{slot}", track="guitar",
                        start=event_time, end=min(chord.end, event_time + step_seconds * 0.8),
                        pitches=ordered_pitches, pitch_offsets=offsets, pitch_velocities=velocities,
                        velocity=velocities[0], stroke=stroke, source_id=chord.id,
                    ))
                slot += 1
                event_time = chord.start + slot * step_seconds

    events.sort(key=lambda event: (event.start, event.track, event.id))
    revision_payload = {
        "bpm": score.analysis.bpm, "meter": score.analysis.time_signature,
        "key_context": score.key_context.model_dump(mode="json"),
        "notation_capo": score.analysis.capo,
        "guitar": score.guitar.model_dump(mode="json"),
        "chords": [
            (
                chord.id, chord.start, chord.end, chord.symbol, chord.shape_symbol, chord.voicing_id,
                [(voicing.id, voicing.frets) for voicing in chord.available_voicings],
            )
            for chord in score.chords
        ],
        "melody": [(note.id, note.start, note.end, note.midi) for note in score.melody],
        "rhythm": score.rhythm.model_dump(mode="json"),
    }
    revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return PlaybackManifest(
        revision=revision, duration_seconds=score.song.duration_seconds, bpm=bpm,
        time_signature=score.analysis.time_signature, events=tuple(events),
    )


def _selected_voicing_pitches(score: SongScore, chord) -> tuple[int, ...]:
    selected = next(
        (voicing for voicing in chord.available_voicings if voicing.id == chord.voicing_id),
        chord.available_voicings[0] if chord.available_voicings else None,
    )
    if selected is None:
        return ()
    capo = score.analysis.capo
    return tuple(
        tuning + fret + capo
        for tuning, fret in zip(score.guitar.tuning, selected.frets)
        if fret is not None
    )


def _strum_profile(stroke: str, string_count: int) -> tuple[tuple[float, ...], tuple[int, ...]]:
    """Return a short, deterministic low-to-high or high-to-low strum profile.

    Pitch order is already arranged by the caller for the requested stroke. A
    12 ms string spread is audible but still comfortably within a sixteenth at
    typical tempos; lower strings receive a slightly stronger attack.
    """
    base_velocity = 98 if stroke == "D" else 86
    offsets = tuple(round(index * 0.012, 3) for index in range(string_count))
    velocities = tuple(max(1, base_velocity - index * 2) for index in range(string_count))
    return offsets, velocities


def _varlen(value: int) -> bytes:
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(parts))


def export_midi(score: SongScore, ticks_per_beat: int = 480) -> bytes:
    manifest = compile_playback_manifest(score)
    tempo = max(1, round(60_000_000 / manifest.bpm))
    # Format 0 still supports multiple MIDI channels. Keep the detected melody
    # on channel 0 and put the playable, selected guitar voicing on channel 1
    # so a sparse or unavailable melody does not produce an empty MIDI file.
    events: list[tuple[int, int, bytes]] = [
        (0, 0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
        (0, 2, bytes([0xC0, 81])),  # lead synth for melody
        (0, 2, bytes([0xC1, 24])),  # nylon guitar for chord accompaniment
    ]
    for event in manifest.events:
        if event.track not in {"melody", "guitar"}:
            continue
        start = max(0, round(event.start * manifest.bpm / 60 * ticks_per_beat))
        end = max(start + 1, round(event.end * manifest.bpm / 60 * ticks_per_beat))
        channel = 0 if event.track == "melody" else 1
        for pitch_index, pitch in enumerate(event.pitches):
            pitch_offset = event.pitch_offsets[pitch_index] if pitch_index < len(event.pitch_offsets) else 0.0
            velocity = event.pitch_velocities[pitch_index] if pitch_index < len(event.pitch_velocities) else event.velocity
            pitch_start = start + max(0, round(pitch_offset * manifest.bpm / 60 * ticks_per_beat))
            events.extend([
                (pitch_start, 1, bytes([0x90 | channel, pitch, velocity])),
                (end, 0, bytes([0x80 | channel, pitch, 0])),
            ])
    events.sort(key=lambda event: (event[0], event[1]))
    track = bytearray()
    previous = 0
    for tick, _, payload in events:
        track.extend(_varlen(tick - previous))
        track.extend(payload)
        previous = tick
    song_end = max(previous, round(manifest.duration_seconds * manifest.bpm / 60 * ticks_per_beat))
    track.extend(_varlen(song_end - previous))
    track.extend(b"\xff\x2f\x00")
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_beat) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
