"""Monophonic vocal melody extraction for a source-separated vocal stem."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median
import hashlib

import numpy as np

from ...models.analysis import BeatAnalysis, MelodyAnalysis, MelodyMode, MelodyNote
from ...models.audio import NormalizedAudio
from ...models.melody_contour import MelodyContour
from .basic_pitch_adapter import MODE_PROFILES, midi_to_note_name

PYIN_HOP_LENGTH = 512
PYIN_SAMPLE_RATE = 22050
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

    Brief semitone excursions are treated as vibrato, but a sustained
    semitone change gets its own note, backdated to the first changed frame.
    Unvoiced frames terminate notes; no beat grid is used here.
    """
    if not np.isfinite(hop_seconds) or not np.isfinite(min_duration) or hop_seconds <= 0 or min_duration <= 0:
        raise ValueError("Frame timing must be finite and positive")
    events: list[tuple[int, int, list[int], list[float]]] = []
    start: int | None = None
    pitches: list[int] = []
    probabilities: list[float] = []
    pending: list[tuple[int, int, float]] = []

    def absorb_pending() -> None:
        pitches.extend(value for _, value, _ in pending)
        probabilities.extend(probability for _, _, probability in pending)
        pending.clear()

    def finish(end: int) -> None:
        nonlocal start, pitches, probabilities
        if start is not None and pitches and (end - start) * hop_seconds >= min_duration - 1e-9:
            events.append((start, end, pitches, probabilities))
        start, pitches, probabilities = None, [], []

    for index, raw_midi in enumerate(midi_values):
        if raw_midi is None or not np.isfinite(raw_midi):
            absorb_pending()
            finish(index)
            continue
        pitch = int(round(float(raw_midi)))
        raw_probability = voiced_probabilities[index] if index < len(voiced_probabilities) else 0.0
        probability = float(raw_probability) if raw_probability is not None and np.isfinite(raw_probability) else 0.0
        if start is None:
            start, pitches, probabilities = index, [pitch], [probability]
        elif pitch == round(median(pitches)):
            absorb_pending()
            pitches.append(pitch)
            probabilities.append(probability)
        else:
            if pending and pending[-1][1] != pitch:
                absorb_pending()
            pending.append((index, pitch, probability))
            if abs(pitch - round(median(pitches))) > 1 or len(pending) * hop_seconds >= min_duration - 1e-9:
                boundary = pending[0][0]
                finish(boundary)
                start = boundary
                absorb_pending()
    absorb_pending()
    finish(len(midi_values))

    notes: list[MelodyNote] = []
    for index, (start, end, pitches, probabilities) in enumerate(events, start=1):
        pitch = int(round(median(pitches)))
        # Preserve pYIN's voiced probability.  A previous artificial 0.45
        # floor accidentally promoted weak stem leakage above the downstream
        # 0.4 acceptance threshold, making accompaniment artifacts sound like
        # a melody.  A small lower clamp only keeps the serialized value sane.
        confidence = max(0.05, min(0.95, sum(probabilities) / max(1, len(probabilities))))
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
        # Demucs stems may be 44.1 kHz stereo. Match the validated audition's
        # time window/hop in seconds instead of silently halving them.
        samples, sample_rate = librosa.load(str(audio.path), sr=PYIN_SAMPLE_RATE, mono=True)
        # Keep the tested CPU profile unchanged. Preserve floating-point F0
        # separately; notation conversion must not become the playback source.
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
        digest = hashlib.sha256()
        with audio.path.open("rb") as source:
            for chunk in iter(lambda: source.read(65536), b""):
                digest.update(chunk)
        contour = MelodyContour(
            source_artifact_sha256=digest.hexdigest(), source_artifact_kind="audio",
            source_start=0, source_end=len(samples) / sample_rate,
            hop_seconds=hop_length / sample_rate,
            frequencies_hz=tuple(float(hz) if np.isfinite(hz) else None for hz in frequencies),
            voiced_probabilities=tuple(float(p) if np.isfinite(p) else None for p in probabilities),
        )
        notes = frames_to_notes(midi, probabilities, hop_seconds=hop_length / sample_rate)
        warnings = [] if notes else ["pYIN found no stable voiced melody in the isolated vocal stem."]
        return MelodyAnalysis(
            notes=notes, contour=contour, mode=mode, confidence=0.75, engine="pyin_vocal",
            engine_version=getattr(librosa, "__version__", "unknown"), warnings=warnings,
        )
