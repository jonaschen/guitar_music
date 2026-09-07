"""Repeatable quality measurements for legally usable golden fixtures."""

from collections.abc import Sequence

from ..models.analysis import ChordEvent


def bpm_absolute_error(expected: float, actual: float) -> float:
    """Backward-compatible absolute BPM metric used by the original tests."""
    return abs(expected - actual)


def chord_symbol_recall(
    expected: Sequence[ChordEvent], actual: Sequence[ChordEvent], tolerance: float = 0.25
) -> float:
    """Backward-compatible onset/symbol chord recall metric."""
    if not expected:
        return 1.0
    matches = sum(
        any(candidate.symbol == reference.symbol and abs(candidate.start - reference.start) <= tolerance for candidate in actual)
        for reference in expected
    )
    return matches / len(expected)
