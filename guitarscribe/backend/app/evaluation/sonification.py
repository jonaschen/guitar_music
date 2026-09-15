"""Deterministic, layered audio renders for human quality review."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, Sequence

import numpy as np
import soundfile as sf

from .annotations import QualityAnnotation
from ..models.score import SongScore


_ROOT_TO_MIDI = {"C": 60, "D": 62, "E": 64, "F": 65, "G": 67, "A": 69, "B": 71}
_CHORD = re.compile(r"^([A-G])([#b]?)(.*)$")


def _frames(start: float, end: float, excerpt_start: float, sample_rate: int, frame_count: int) -> tuple[int, int]:
    first = max(0, min(frame_count, int((start - excerpt_start) * sample_rate)))
    last = max(first, min(frame_count, int((end - excerpt_start) * sample_rate)))
    return first, last


def _add_tone(audio: np.ndarray, first: int, last: int, frequency: float, gain: float, sample_rate: int) -> None:
    if last <= first:
        return
    times = np.arange(last - first, dtype=np.float32) / sample_rate
    tone = np.sin(2 * np.pi * frequency * times).astype(np.float32)
    edge = min(len(tone) // 2, max(1, int(sample_rate * 0.005)))
    if edge:
        envelope = np.linspace(0, 1, edge, dtype=np.float32)
        tone[:edge] *= envelope
        tone[-edge:] *= envelope[::-1]
    audio[first:last] += tone * gain


def _write(output_path: Path, audio: np.ndarray, sample_rate: int) -> None:
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 0.9:
        audio *= 0.9 / peak
    sf.write(str(output_path), audio, sample_rate, subtype="PCM_16")


def render_timing_sonification(
    beats: Iterable[float],
    downbeats: Iterable[float],
    excerpt_start: float,
    excerpt_end: float,
    output_path: Path,
    sample_rate: int = 16000,
) -> None:
    """Render beat clicks at 1 kHz and downbeat accents at 1.5 kHz."""
    frame_count = max(1, int((excerpt_end - excerpt_start) * sample_rate))
    audio = np.zeros(frame_count, dtype=np.float32)
    for point in beats:
        first, last = _frames(point, point + 0.035, excerpt_start, sample_rate, frame_count)
        _add_tone(audio, first, last, 1000, 0.32, sample_rate)
    for point in downbeats:
        first, last = _frames(point, point + 0.065, excerpt_start, sample_rate, frame_count)
        _add_tone(audio, first, last, 1500, 0.5, sample_rate)
    _write(output_path, audio, sample_rate)


def _chord_midis(label: str) -> tuple[int, ...]:
    compact = label.strip().replace("♯", "#").replace("♭", "b").split("/", 1)[0]
    if compact in {"", "N", "NC", "N.C."}:
        return ()
    match = _CHORD.match(compact)
    if not match:
        return ()
    root_name, accidental, quality = match.groups()
    root = _ROOT_TO_MIDI[root_name] + (1 if accidental == "#" else -1 if accidental == "b" else 0)
    quality = quality.lower().lstrip(":")
    if quality.startswith("dim"):
        intervals = (0, 3, 6)
    elif quality.startswith("aug") or quality.startswith("+"):
        intervals = (0, 4, 8)
    elif quality.startswith("m") and not quality.startswith("maj"):
        intervals = (0, 3, 7)
    elif quality.startswith("sus2"):
        intervals = (0, 2, 7)
    elif quality.startswith("sus"):
        intervals = (0, 5, 7)
    else:
        intervals = (0, 4, 7)
    return tuple(root + interval - 12 for interval in intervals)


def render_chord_sonification(
    regions: Sequence[object],
    excerpt_start: float,
    excerpt_end: float,
    output_path: Path,
    sample_rate: int = 16000,
) -> None:
    """Render chord regions as quiet sustained triads; N.C. remains silent."""
    frame_count = max(1, int((excerpt_end - excerpt_start) * sample_rate))
    audio = np.zeros(frame_count, dtype=np.float32)
    for region in regions:
        first, last = _frames(float(region.start), float(region.end), excerpt_start, sample_rate, frame_count)
        label = str(getattr(region, "label", getattr(region, "symbol", "N")))
        for midi in _chord_midis(label):
            frequency = 440.0 * (2.0 ** ((midi - 69) / 12.0))
            _add_tone(audio, first, last, frequency, 0.12, sample_rate)
    _write(output_path, audio, sample_rate)


def render_note_sonification(
    notes: Sequence[object],
    excerpt_start: float,
    excerpt_end: float,
    output_path: Path,
    sample_rate: int = 16000,
) -> None:
    """Render a monophonic note layer without confidence-dependent loudness."""
    frame_count = max(1, int((excerpt_end - excerpt_start) * sample_rate))
    audio = np.zeros(frame_count, dtype=np.float32)
    for note in notes:
        first, last = _frames(float(note.start), float(note.end), excerpt_start, sample_rate, frame_count)
        frequency = 440.0 * (2.0 ** ((float(note.midi) - 69) / 12.0))
        _add_tone(audio, first, last, frequency, 0.3, sample_rate)
    _write(output_path, audio, sample_rate)


def render_quality_sonifications(
    score: SongScore, annotation: QualityAnnotation, output_directory: Path
) -> dict[str, str]:
    """Render reference/estimated pairs for each independently reviewed layer."""
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "reference_timing": output_directory / "reference-timing.wav",
        "estimated_timing": output_directory / "estimated-timing.wav",
        "reference_chords": output_directory / "reference-chords.wav",
        "estimated_chords": output_directory / "estimated-chords.wav",
        "reference_melody": output_directory / "reference-melody.wav",
        "estimated_melody": output_directory / "estimated-melody.wav",
    }
    start, end = annotation.excerpt_start, annotation.excerpt_end
    render_timing_sonification(
        [point.time for point in annotation.beats],
        [point.time for point in annotation.downbeats],
        start,
        end,
        paths["reference_timing"],
    )
    render_timing_sonification(
        [beat.time for beat in score.beats],
        [beat.time for beat in score.beats if beat.beat == 1],
        start,
        end,
        paths["estimated_timing"],
    )
    render_chord_sonification(annotation.chords, start, end, paths["reference_chords"])
    render_chord_sonification(score.chords, start, end, paths["estimated_chords"])
    render_note_sonification(annotation.melody, start, end, paths["reference_melody"])
    render_note_sonification(score.melody, start, end, paths["estimated_melody"])
    return {name: path.name for name, path in paths.items()}
