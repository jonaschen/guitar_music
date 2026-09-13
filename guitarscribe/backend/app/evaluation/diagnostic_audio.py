"""Small, deterministic audio renders used to audit melody pipeline stages."""

from pathlib import Path

import numpy as np
import soundfile as sf

from ..models.analysis import MelodyNote


def render_melody_diagnostic(
    notes: list[MelodyNote], duration_seconds: float, output_path: Path, sample_rate: int = 16000
) -> None:
    """Render note candidates as a neutral sine track for stage A/B testing."""
    frame_count = max(1, int(duration_seconds * sample_rate))
    audio = np.zeros(frame_count, dtype=np.float32)
    for note in notes:
        start = max(0, min(frame_count, int(note.start * sample_rate)))
        end = max(start, min(frame_count, int(note.end * sample_rate)))
        if end <= start:
            continue
        frequency = 440.0 * (2.0 ** ((note.midi - 69) / 12.0))
        times = np.arange(end - start, dtype=np.float32) / sample_rate
        tone = np.sin(2 * np.pi * frequency * times).astype(np.float32)
        attack = min(len(tone) // 2, max(1, int(sample_rate * 0.01)))
        release = min(len(tone) // 2, max(1, int(sample_rate * 0.03)))
        if attack:
            tone[:attack] *= np.linspace(0, 1, attack, dtype=np.float32)
        if release:
            tone[-release:] *= np.linspace(1, 0, release, dtype=np.float32)
        audio[start:end] += tone * max(0.08, min(0.35, note.confidence * 0.35))
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 0.8:
        audio *= 0.8 / peak
    sf.write(str(output_path), audio, sample_rate, subtype="PCM_16")
