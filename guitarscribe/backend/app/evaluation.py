from collections.abc import Sequence

from .models.analysis import ChordEvent


def bpm_absolute_error(expected: float, actual: float) -> float:
    return abs(expected - actual)


def chord_symbol_recall(expected: Sequence[ChordEvent], actual: Sequence[ChordEvent], tolerance: float = 0.25) -> float:
    if not expected:
        return 1.0
    matches = sum(
        any(candidate.symbol == reference.symbol and abs(candidate.start - reference.start) <= tolerance for candidate in actual)
        for reference in expected
    )
    return matches / len(expected)
