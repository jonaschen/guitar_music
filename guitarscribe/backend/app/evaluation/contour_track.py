"""Bounded-memory frame-hold audio for the experimental contour track."""

from math import ceil
from pathlib import Path

import numpy as np
import soundfile as sf

from ..models.melody_contour import MelodyContour


def render_contour_track(contour: MelodyContour, output: Path, sample_rate: int = 16000) -> None:
    """Render source-aligned audio with continuous phase and voiced-run fades.

    No note rounding, per-note attacks, interpolation, confidence filtering,
    or gap filling. Write at most 4096 samples at once, including silence.
    """
    if sample_rate <= 0 or any(hz is not None and hz >= sample_rate / 2 for hz in contour.frequencies_hz):
        raise ValueError("Invalid sample rate or frequency above Nyquist")
    total = round(contour.source_end * sample_rate)
    hop = contour.hop_seconds
    # Match render_pitch_contour's floor(position + 1e-9) boundary convention.
    def boundary(index):
        return min(total, max(0, ceil((contour.source_start + index * hop - 1e-9 * hop) * sample_rate)))

    frames = contour.frequencies_hz
    phase_sum = 0.0
    cursor = 0
    with sf.SoundFile(output, "w", samplerate=sample_rate, channels=1, subtype="PCM_16") as stream:
        def silence_until(end):
            nonlocal cursor
            while cursor < end:
                size = min(4096, end - cursor)
                stream.write(np.zeros(size))
                cursor += size

        index = 0
        while index < len(frames):
            if frames[index] is None:
                index += 1
                continue
            first = index
            while index < len(frames) and frames[index] is not None:
                index += 1
            left, right = boundary(first), boundary(index)
            silence_until(left)
            fade = min((right - left) // 2, max(1, round(sample_rate * 0.005)))
            for frame in range(first, index):
                end = boundary(frame + 1)
                hz = frames[frame]
                while cursor < end:
                    size = min(4096, end - cursor)
                    positions = cursor + np.arange(size)
                    gain = np.ones(size)
                    if fade > 1:
                        gain = np.minimum(1, np.minimum((positions - left) / (fade - 1),
                                                       (right - 1 - positions) / (fade - 1)))
                    elif fade == 1:
                        gain[positions == left] = 0
                    sums = phase_sum + hz * np.arange(1, size + 1)
                    stream.write(0.3 * gain * np.sin(2 * np.pi * sums / sample_rate))
                    phase_sum += hz * size
                    cursor += size
        silence_until(total)


def save_contour_artifacts(contour: MelodyContour, directory: Path) -> None:
    """Only publish completed files; no score or existing note artifact changes."""
    sidecar = directory / "melody-contour.json"
    sidecar_temp = directory / "melody-contour.json.tmp"
    sidecar_temp.write_text(contour.model_dump_json(indent=2))
    sidecar_temp.replace(sidecar)
    if any(hz is not None for hz in contour.frequencies_hz):
        temporary = directory / "melody-contour.pending.wav"
        render_contour_track(contour, temporary)
        temporary.replace(directory / "melody-contour.wav")
