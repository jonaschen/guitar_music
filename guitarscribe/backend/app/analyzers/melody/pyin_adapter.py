"""Monophonic vocal melody extraction for a source-separated vocal stem."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

import numpy as np

from ...models.analysis import BeatAnalysis, MelodyAnalysis, MelodyMode, MelodyNote
from ...models.audio import NormalizedAudio
from .basic_pitch_adapter import MODE_PROFILES, midi_to_note_name

PYIN_HOP_LENGTH = 512
PYIN_RESOLUTION = 0.5
PYIN_THRESHOLDS = 32


def frames_to_notes(
    midi_values: Sequence[float | None],
    voiced_probabilities: Sequence[float | None],
    *,
    hop_seconds: float,
    min_duration: float = 0.10,
) -> list[MelodyNote]:
    """Turn pYIN frames into stable semitone note spans.

    A one-semitone tolerance absorbs normal vocal vibrato.  Unvoiced frames
    deliberately terminate a note: invented bridges sound worse than a short
    rest in a practice transcription.
    """
    events: list[tuple[int, int, list[int], list[float]]] = []
    start: int | None = None
    pitches: list[int] = []
    probabilities: list[float] = []

    def finish(end: int) -> None:
        nonlocal start, pitches, probabilities
        if start is not None and pitches and (end - start) * hop_seconds >= min_duration:
            events.append((start, end, pitches, probabilities))
        start, pitches, probabilities = None, [], []

    for index, raw_midi in enumerate(midi_values):
        if raw_midi is None or not np.isfinite(raw_midi):
            finish(index)
            continue
        pitch = int(round(float(raw_midi)))
        raw_probability = voiced_probabilities[index] if index < len(voiced_probabilities) else 0.0
        probability = float(raw_probability) if raw_probability is not None and np.isfinite(raw_probability) else 0.0
        if start is None:
            start, pitches, probabilities = index, [pitch], [probability]
        elif abs(pitch - round(median(pitches))) <= 1:
            pitches.append(pitch)
            probabilities.append(probability)
        else:
            finish(index)
            start, pitches, probabilities = index, [pitch], [probability]
    finish(len(midi_values))

    notes: list[MelodyNote] = []
    for index, (start, end, pitches, probabilities) in enumerate(events, start=1):
        pitch = int(round(median(pitches)))
        # Downstream processing applies a 0.4 confidence floor. pYIN's voiced
        # probability is useful but can be conservative on breathy vocals.
        confidence = max(0.45, min(0.95, sum(probabilities) / max(1, len(probabilities))))
        notes.append(MelodyNote(
            id=f"pyin-{index}", start=start * hop_seconds, end=end * hop_seconds,
            midi=pitch, note=midi_to_note_name(pitch), confidence=confidence,
        ))
    return notes


class PyinVocalMelodyAnalyzer:
    """Trace one fundamental-frequency line instead of polyphonic note events."""

    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis, mode: MelodyMode = MelodyMode.VOCAL) -> MelodyAnalysis:
        if mode != MelodyMode.VOCAL:
            raise ValueError("pYIN vocal analyzer only supports vocal mode")
        import librosa

        profile = MODE_PROFILES[MelodyMode.VOCAL]
        samples, sample_rate = librosa.load(str(audio.path), sr=None, mono=True)
        # The downstream score is quantized to musical grid points and MIDI
        # semitones, so pYIN's 0.1-cent-like default resolution is wasted work
        # on multi-minute songs. These values keep vocal contours while making
        # optional source-separated analysis practical on CPU.
        hop_length = PYIN_HOP_LENGTH
        frequencies, _voiced, probabilities = librosa.pyin(
            samples,
            fmin=profile["minimum_frequency"],
            fmax=profile["maximum_frequency"],
            sr=sample_rate,
            hop_length=hop_length,
            frame_length=2048,
            resolution=PYIN_RESOLUTION,
            n_thresholds=PYIN_THRESHOLDS,
        )
        midi = librosa.hz_to_midi(frequencies)
        notes = frames_to_notes(midi, probabilities, hop_seconds=hop_length / sample_rate)
        warnings = [] if notes else ["pYIN found no stable voiced melody in the isolated vocal stem."]
        return MelodyAnalysis(
            notes=notes, mode=mode, confidence=0.75, engine="pyin_vocal",
            engine_version=getattr(librosa, "__version__", "unknown"), warnings=warnings,
        )
