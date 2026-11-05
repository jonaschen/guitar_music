"""Offline Klangio JSON import for evaluation only; never a source of ground truth.

Contracts: api-docs.klang.io/docs/jobs/{beat-tracking-request,
chord-recognition-requests}, checked 2026-11-05. No network or product adapter.
"""
import math

import mir_eval

from ..models.analysis import BeatInfo, ChordEvent
from ..models.score import SongScore


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite numeric timestamp or beat position")
    return float(value)


def import_klangio_results(*, beats, chords, duration: float) -> SongScore:
    """Import timestamps relative to the exact uploaded clip, without rescaling.

    Missing layer is None, an empty beat result is a failed detection. Chord
    gaps are rejected rather than filled with invented silence. N and X remain
    distinct. Partial or unsupported payloads require inspection, not guessing.
    """
    duration = _number(duration)
    if duration <= 0:
        raise ValueError("Clip duration must be positive")
    score = SongScore()
    score.song.duration_seconds = duration
    score.analysis.timing_status = "unmetered"
    score.analysis.bpm = 0
    score.analysis.time_signature = ""
    if beats is not None:
        if not isinstance(beats, list):
            raise ValueError("Beat result must be a JSON array")
        previous = -1.0
        measure = 0
        for row in beats:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError("Beat entries must contain timestamp and beat position")
            time, position = map(_number, row)
            if not previous < time < duration or time < 0:
                raise ValueError("Beat timestamps must increase within the clip")
            if position not in {1, 2, 3, 4}:
                raise ValueError("Unsupported beat position; only documented 3/4 and 4/4 results supported")
            if position == 1:
                measure += 1
            score.beats.append(BeatInfo(time=time, beat=int(position), measure=measure))
            previous = time
    if chords is not None:
        if not isinstance(chords, list) or not chords:
            raise ValueError("Chord result must explicitly cover the clip, including N or X regions")
        cursor = 0.0
        for i, row in enumerate(chords):
            if not isinstance(row, list) or len(row) != 3 or not isinstance(row[2], str):
                raise ValueError("Chord entries must contain start, end and label")
            start, end = map(_number, row[:2])
            label = row[2]
            try:
                mir_eval.chord.validate_chord_label(label)
            except mir_eval.chord.InvalidChordException as exc:
                raise ValueError(f"Unsupported chord label: {label}") from exc
            if start < 0 or abs(start-cursor) > 1e-7 or end <= start or end > duration:
                raise ValueError("Chord intervals must be ordered, continuous and inside the clip")
            score.chords.append(ChordEvent(id=f"external-{i}", start=start, end=end, symbol=label))
            cursor = end
        if abs(cursor-duration) > 1e-7:
            raise ValueError("Partial chord response; clip tail is missing")
    return score
