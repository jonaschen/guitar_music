"""Minimal Standard MIDI File export for detected melody notes."""

from __future__ import annotations

import struct

from ..models.score import SongScore


def _varlen(value: int) -> bytes:
    parts = [value & 0x7F]
    value >>= 7
    while value:
        parts.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(parts))


def export_midi(score: SongScore, ticks_per_beat: int = 480) -> bytes:
    tempo = max(1, round(60_000_000 / max(score.analysis.bpm, 1)))
    events: list[tuple[int, int, bytes]] = [(0, 0, b"\xff\x51\x03" + tempo.to_bytes(3, "big"))]
    for note in score.melody:
        start = max(0, round(note.start * score.analysis.bpm / 60 * ticks_per_beat))
        end = max(start + 1, round(note.end * score.analysis.bpm / 60 * ticks_per_beat))
        events.extend([(start, 1, bytes([0x90, note.midi, 96])), (end, 0, bytes([0x80, note.midi, 0]))])
    events.sort(key=lambda event: (event[0], event[1]))
    track = bytearray()
    previous = 0
    for tick, _, payload in events:
        track.extend(_varlen(tick - previous))
        track.extend(payload)
        previous = tick
    track.extend(b"\x00\xff\x2f\x00")
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_beat) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
