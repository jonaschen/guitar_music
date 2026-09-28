"""Audition raw F0 independently of note selection, quantization and merging."""

from pathlib import Path

import numpy as np
import soundfile as sf


def render_pitch_contour(frequencies: list[float | None], hop_seconds: float,
                         source_offset: float, start: float, end: float,
                         output: Path, sample_rate: int = 16000) -> None:
    """Preserve frame-level pitch, including bends, without inventing gap pitches.

    Frames denote left boundaries. Only interpolate to an adjacent voiced
    frame; an unvoiced frame is silence. A short fade bounds each voiced run.
    This is an F0 diagnostic, not a score or an accuracy claim.
    """
    if not all(np.isfinite(v) for v in (hop_seconds, source_offset, start, end)) or hop_seconds <= 0 or start < 0 or end <= start or sample_rate <= 0:
        raise ValueError("Invalid contour timing")
    if any(value is not None and (not np.isfinite(value) or value <= 0 or value >= sample_rate / 2) for value in frequencies):
        raise ValueError("Frequencies must be voiced Hz below Nyquist or None")
    values = np.array([np.nan if value is None else value for value in frequencies], dtype=float)
    times = start + np.arange(round((end - start) * sample_rate)) / sample_rate
    positions = (times - source_offset) / hop_seconds
    indices = np.floor(positions + 1e-9).astype(int)
    valid = (indices >= 0) & (indices < len(values))
    hz = np.zeros(len(times))
    if len(values):
        safe = np.clip(indices, 0, len(values) - 1)
        voiced = valid & np.isfinite(values[safe])
        hz[voiced] = values[safe[voiced]]
        following = np.minimum(safe + 1, len(values) - 1)
        interpolate = voiced & (safe + 1 < len(values)) & np.isfinite(values[following])
        fraction = np.clip(positions - indices, 0, 1)
        hz[interpolate] += fraction[interpolate] * (values[following[interpolate]] - values[safe[interpolate]])
    else:
        voiced = np.zeros(len(times), dtype=bool)
    gain = voiced.astype(float)
    boundaries = np.diff(np.r_[False, voiced, False].astype(int))
    for left, right in zip(np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1)):
        fade = min((right - left) // 2, max(1, round(sample_rate * 0.005)))
        if fade:
            gain[left:left + fade] *= np.linspace(0, 1, fade)
            gain[right - fade:right] *= np.linspace(1, 0, fade)
    phase = 2 * np.pi * np.cumsum(hz) / sample_rate
    audio = 0.3 * gain * np.sin(phase)
    sf.write(output, audio, sample_rate, subtype="PCM_16")
