"""Layered mir_eval report for legally annotated quality excerpts."""

from __future__ import annotations

from typing import Any
import re

import mir_eval
import numpy as np

from .annotations import QualityAnnotation
from ..models.analysis import MelodyNote
from ..models.score import SongScore


_CHORD_LABEL = re.compile(r"^([A-G](?:#|b)?)(.*)$")


def _mir_eval_chord_label(label: str) -> str:
    """Translate common lead-sheet spelling into mir_eval's Harte syntax."""
    compact = label.strip().replace("♯", "#").replace("♭", "b")
    if compact in {"", "N", "NC", "N.C.", "no_chord"}:
        return "N"
    if ":" in compact:
        return compact
    compact = compact.split("/", 1)[0]
    match = _CHORD_LABEL.match(compact)
    if not match:
        return "X"
    root, suffix = match.groups()
    quality = {
        "": "maj",
        "m": "min",
        "min": "min",
        "maj": "maj",
        "7": "7",
        "maj7": "maj7",
        "M7": "maj7",
        "m7": "min7",
        "min7": "min7",
        "dim": "dim",
        "dim7": "dim7",
        "aug": "aug",
        "+": "aug",
        "sus2": "sus2",
        "sus4": "sus4",
        "sus": "sus4",
    }.get(suffix)
    return f"{root}:{quality}" if quality else "X"


def _boundary_scores(reference: list[float], estimated: list[float], tolerance: float = 0.25) -> dict[str, float]:
    if not reference:
        value = 1.0 if not estimated else 0.0
        return {"precision": value, "recall": 1.0, "f_measure": value}
    if not estimated:
        return {"precision": 1.0, "recall": 0.0, "f_measure": 0.0}
    matched: set[int] = set()
    true_positives = 0
    for boundary in estimated:
        choices = [
            (abs(boundary - target), index)
            for index, target in enumerate(reference)
            if index not in matched and abs(boundary - target) <= tolerance
        ]
        if choices:
            _, index = min(choices)
            matched.add(index)
            true_positives += 1
    precision = true_positives / len(estimated)
    recall = true_positives / len(reference)
    f_measure = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f_measure": f_measure}


def _note_contour(notes: list[MelodyNote] | list[Any], start: float, end: float, step: float = 0.01):
    times = np.arange(start, end, step)
    frequencies = np.zeros_like(times)
    for note in notes:
        active = (times >= note.start) & (times < note.end)
        frequencies[active] = 440.0 * (2.0 ** ((float(note.midi) - 69.0) / 12.0))
    return times, frequencies


def evaluate_quality_layers(score: SongScore, annotation: QualityAnnotation) -> dict[str, Any]:
    """Return separate timing/chord/melody metrics with no synthetic overall score."""
    reference_beats = np.asarray([point.time for point in annotation.beats], dtype=float)
    estimated_beats = np.asarray([beat.time for beat in score.beats], dtype=float)
    reference_downbeats = np.asarray([point.time for point in annotation.downbeats], dtype=float)
    estimated_downbeats = np.asarray([beat.time for beat in score.beats if beat.beat == 1], dtype=float)
    timing: dict[str, float | str] = {
        "beat_f_measure": float(mir_eval.beat.f_measure(reference_beats, estimated_beats)) if len(reference_beats) else "not_annotated",
        "downbeat_f_measure": float(mir_eval.beat.f_measure(reference_downbeats, estimated_downbeats)) if len(reference_downbeats) else "not_annotated",
    }
    if annotation.tempo_bpm is not None:
        timing["bpm_relative_error"] = abs(score.analysis.bpm - annotation.tempo_bpm) / annotation.tempo_bpm
    if len(reference_downbeats) and len(estimated_downbeats):
        timing["first_downbeat_phase_error_seconds"] = float(abs(reference_downbeats[0] - estimated_downbeats[np.argmin(abs(estimated_downbeats - reference_downbeats[0]))]))

    chord: dict[str, float | str] = {"status": "not_annotated"}
    if annotation.chords:
        reference_intervals = np.asarray([[region.start, region.end] for region in annotation.chords], dtype=float)
        reference_labels = [_mir_eval_chord_label(region.label) for region in annotation.chords]
        estimated_regions = [event for event in score.chords if event.start < annotation.excerpt_end and event.end > annotation.excerpt_start]
        estimated_intervals = np.asarray([[event.start, event.end] for event in estimated_regions], dtype=float)
        estimated_labels = [_mir_eval_chord_label(event.symbol) for event in estimated_regions]
        if len(estimated_intervals):
            estimated_intervals, estimated_labels = mir_eval.util.adjust_intervals(
                estimated_intervals,
                estimated_labels,
                t_min=float(reference_intervals[0, 0]),
                t_max=float(reference_intervals[-1, 1]),
                start_label="N",
                end_label="N",
            )
            mir_scores = mir_eval.chord.evaluate(reference_intervals, reference_labels, estimated_intervals, estimated_labels)
            boundaries = _boundary_scores(
                [region.start for region in annotation.chords[1:]],
                [event.start for event in estimated_regions[1:]],
            )
            fragmentation_ratio = len(estimated_regions) / len(annotation.chords)
            review_count = sum(event.needs_review for event in estimated_regions)
            excerpt_minutes = max(annotation.excerpt_end - annotation.excerpt_start, 1e-6) / 60
            chord = {
                "majmin_weighted_accuracy": float(mir_scores["majmin"]),
                "root_weighted_accuracy": float(mir_scores["root"]),
                "boundary_precision": boundaries["precision"],
                "boundary_recall": boundaries["recall"],
                "boundary_f_measure": boundaries["f_measure"],
                "reference_event_count": len(annotation.chords),
                "estimated_event_count": len(estimated_regions),
                "excess_event_count": max(0, len(estimated_regions) - len(annotation.chords)),
                "estimated_events_per_minute": len(estimated_regions) / excerpt_minutes,
                "fragmentation_ratio": fragmentation_ratio,
                "over_fragmented": fragmentation_ratio > 1.25,
                "review_event_count": review_count,
                "review_event_ratio": review_count / len(estimated_regions),
            }
        else:
            chord = {
                "status": "no_estimated_chords",
                "reference_event_count": len(annotation.chords),
                "estimated_event_count": 0,
                "fragmentation_ratio": 0.0,
                "over_fragmented": False,
                "review_event_count": 0,
                "review_event_ratio": 0.0,
            }

    melody: dict[str, float | str] = {"status": "not_annotated"}
    if annotation.melody:
        ref_time, ref_frequency = _note_contour(annotation.melody, annotation.excerpt_start, annotation.excerpt_end)
        est_time, est_frequency = _note_contour(score.melody, annotation.excerpt_start, annotation.excerpt_end)
        mir_scores = mir_eval.melody.evaluate(ref_time, ref_frequency, est_time, est_frequency)
        melody = {
            "voicing_recall": float(mir_scores["Voicing Recall"]),
            "voicing_false_alarm": float(mir_scores["Voicing False Alarm"]),
            "raw_pitch_accuracy": float(mir_scores["Raw Pitch Accuracy"]),
            "raw_chroma_accuracy": float(mir_scores["Raw Chroma Accuracy"]),
            "overall_accuracy": float(mir_scores["Overall Accuracy"]),
        }

    return {
        "schema_version": "1.1",
        "recording_id": annotation.recording_id,
        "timing": timing,
        "chord": chord,
        "melody": melody,
        "human_review": {
            "required": True,
            "listening_notes": annotation.listening_notes,
            "error_tags": annotation.error_tags,
        },
    }
