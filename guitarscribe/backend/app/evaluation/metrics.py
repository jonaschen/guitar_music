"""Small, dependency-free metrics for GuitarScribe golden annotations."""

from __future__ import annotations

from typing import Any, Iterable

from ..models.analysis import ChordEvent, MelodyNote
from ..models.score import SongScore


def bpm_relative_error(estimated: float, expected: float) -> float:
    """Return absolute BPM error relative to the annotated tempo."""
    if expected <= 0:
        raise ValueError("Expected BPM must be greater than zero")
    return abs(estimated - expected) / expected


def beat_f_measure(estimated: Iterable[float], expected: Iterable[float], tolerance_seconds: float = 0.07) -> float:
    """Greedily match one detected beat to one annotated beat within tolerance."""
    predicted = sorted(float(value) for value in estimated)
    reference = sorted(float(value) for value in expected)
    if not predicted and not reference:
        return 1.0
    matched: set[int] = set()
    true_positives = 0
    for value in predicted:
        candidates = [
            (abs(value - target), index)
            for index, target in enumerate(reference)
            if index not in matched and abs(value - target) <= tolerance_seconds
        ]
        if candidates:
            _, index = min(candidates)
            matched.add(index)
            true_positives += 1
    if true_positives == 0:
        return 0.0
    precision = true_positives / len(predicted)
    recall = true_positives / len(reference)
    return 2 * precision * recall / (precision + recall)


def chord_symbol_recall(estimated: Iterable[ChordEvent], expected: Iterable[dict[str, Any]]) -> float:
    """Score an annotated chord when the strongest overlapping estimate matches."""
    reference = list(expected)
    if not reference:
        return 1.0
    predictions = list(estimated)
    correct = 0
    for annotation in reference:
        start, end = float(annotation["start"]), float(annotation["end"])
        overlaps = [
            (min(end, chord.end) - max(start, chord.start), chord)
            for chord in predictions
            if chord.start < end and start < chord.end
        ]
        if overlaps and max(overlaps, key=lambda item: item[0])[1].symbol == annotation["symbol"]:
            correct += 1
    return correct / len(reference)


def melody_pitch_accuracy(
    estimated: Iterable[MelodyNote], expected: Iterable[dict[str, Any]],
    tolerance_seconds: float = 0.12,
    tolerance_semitones: int = 0,
) -> float:
    """One-to-one onset/pitch accuracy against monophonic reference notes."""
    predictions = list(estimated)
    reference = list(expected)
    if not reference:
        return 1.0
    matched: set[int] = set()
    correct = 0
    for annotation in reference:
        candidates = [
            (abs(note.start - float(annotation["start"])), index, note)
            for index, note in enumerate(predictions)
            if index not in matched and abs(note.start - float(annotation["start"])) <= tolerance_seconds
        ]
        if candidates:
            _, index, note = min(candidates)
            matched.add(index)
            if abs(note.midi - int(annotation["midi"])) <= tolerance_semitones:
                correct += 1
    return correct / len(reference)


def evaluate_score(score: SongScore, annotation: dict[str, Any]) -> dict[str, float]:
    """Calculate the standard golden-fixture metrics for one SongScore."""
    return {
        "bpm_relative_error": round(bpm_relative_error(score.analysis.bpm, float(annotation["bpm"])), 6),
        "beat_f_measure": round(beat_f_measure((beat.time for beat in score.beats), annotation.get("beats", [])), 6),
        "chord_symbol_recall": round(chord_symbol_recall(score.chords, annotation.get("chords", [])), 6),
        "melody_pitch_accuracy": round(melody_pitch_accuracy(score.melody, annotation.get("melody", [])), 6),
    }
