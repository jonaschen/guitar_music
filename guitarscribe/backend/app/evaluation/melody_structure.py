"""Reference-free structural diagnostics, not melody recognition accuracy."""

from collections import defaultdict
from math import isfinite

from ..models.analysis import MelodyNote


def inspect_melody_structure(notes: list[MelodyNote], start: float, end: float) -> dict:
    """Measure half-open intervals without silently choosing a lead voice.

    Clip to the requested excerpt and count even same-pitch overlaps: these
    are still multiple note events, not proof of distinct musical voices.
    Never mutate notes or infer correctness from monophony.
    """
    if not isfinite(start) or not isfinite(end) or start < 0 or end <= start:
        raise ValueError("Expected a finite, positive-length excerpt")
    changes: dict[float, int] = defaultdict(int)
    note_count = 0
    for note in notes:
        left, right = max(start, note.start), min(end, note.end)
        if right <= left:
            continue
        changes[left] += 1
        changes[right] -= 1
        note_count += 1
    active = peak = 0
    previous = start
    voiced = overlap = 0.0
    windows: list[dict] = []
    for time, delta in sorted(changes.items()):
        length = time - previous
        if active:
            voiced += length
        if active > 1 and length > 0:
            overlap += length
            if windows and windows[-1]["end"] == previous:
                windows[-1]["end"] = time
            else:
                windows.append({"start": previous, "end": time})
        active += delta
        peak = max(peak, active)
        previous = time
    return {
        "note_count": note_count,
        "voiced_seconds": round(voiced, 6),
        "overlap_seconds": round(overlap, 6),
        "overlap_fraction_of_voiced": overlap / voiced if voiced else 0.0,
        "peak_simultaneous_events": peak,
        "overlap_windows": windows,
        "recognition_accuracy": None,
    }
