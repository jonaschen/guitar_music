"""Experimental duration-constrained note decoding from an unchanged F0 contour.

No key/score prior and no beat snapping. Keep the source contour separately:
integer notes cannot represent every bend, and F0 alone cannot identify
repeated same-pitch syllable onsets. Not enabled in the production pipeline.
"""

from math import ceil, isfinite

import numpy as np

from ..analyzers.melody.basic_pitch_adapter import midi_to_note_name
from ..models.analysis import MelodyNote


def decode_contour_notes(midi_values: list[float | None], probabilities: list[float | None],
                         *, hop_seconds: float, min_duration: float = 0.10,
                         transition_cost: float = 1.0) -> list[MelodyNote]:
    """Minimize confidence-weighted pitch error over complete voiced runs.

    Each segment must last at least min_duration. A transition penalty
    discourages splitting vibrato; it does not forbid real semitone motion.
    These defaults are experimental, not a calibrated recognition guarantee.
    Unlike the legacy decoder, emissions use floating-point pitches before
    choosing a representative integer pitch for the whole segment.
    """
    if not all(isfinite(x) for x in (hop_seconds, min_duration, transition_cost)) or hop_seconds <= 0 or min_duration <= 0 or transition_cost < 0:
        raise ValueError("Invalid decoder parameters")
    minimum = max(1, ceil(min_duration / hop_seconds - 1e-9))
    result: list[MelodyNote] = []

    def decode_run(start: int, end: int):
        length = end - start
        if length < minimum:
            return
        values = np.asarray(midi_values[start:end], dtype=float)
        confidence = np.array([
            float(probabilities[i]) if i < len(probabilities) and probabilities[i] is not None
            and isfinite(probabilities[i]) else 0.0 for i in range(start, end)
        ]).clip(0, 1)
        pitches = np.arange(max(0, int(np.floor(values.min()))), min(127, int(np.ceil(values.max()))) + 1)
        errors = (pitches[:, None] - values[None, :]) ** 2 * np.maximum(confidence, 0.05)
        cumulative = np.c_[np.zeros(len(pitches)), np.cumsum(errors, axis=1)]
        costs = np.full(length + 1, np.inf)
        costs[0] = 0
        previous = np.zeros(length + 1, dtype=int)
        selected_pitch = np.zeros(length + 1, dtype=int)
        for right in range(minimum, length + 1):
            lefts = np.arange(right - minimum + 1)
            segments = cumulative[:, right, None] - cumulative[:, lefts]
            best = np.argmin(segments, axis=0)
            totals = costs[lefts] + segments[best, lefts] + np.where(lefts == 0, 0, transition_cost)
            chosen = int(np.argmin(totals))
            costs[right] = totals[chosen]
            previous[right] = chosen
            selected_pitch[right] = pitches[best[chosen]]
        decoded = []
        right = length
        while right:
            left = int(previous[right])
            pitch = int(selected_pitch[right])
            decoded.append((left, right, pitch))
            right = left
        for left, right, pitch in reversed(decoded):
            result.append(MelodyNote(id=f"contour-{len(result)+1}", start=(start+left)*hop_seconds,
                                    end=(start+right)*hop_seconds, midi=pitch, note=midi_to_note_name(pitch),
                                    confidence=float(confidence[left:right].mean())))

    run_start = None
    for index in range(len(midi_values) + 1):
        value = midi_values[index] if index < len(midi_values) else None
        voiced = value is not None and isfinite(value) and 0 <= value <= 127
        if voiced and run_start is None:
            run_start = index
        elif not voiced and run_start is not None:
            decode_run(run_start, index)
            run_start = None
    return result
