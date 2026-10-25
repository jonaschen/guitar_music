"""Fixed, experimental audio-onset supplement to G; never a production decoder.

No labels, beats or reference events are accepted. Audio-supported inward edge
trimming is bounded by the known pYIN analysis window, never beat quantization.
"""
from math import isfinite

import numpy as np
from scipy.signal import find_peaks

from .conservative_notes import decode_bounded
from ..models.analysis import MelodyNote
from ..models.melody_contour import MelodyContour

RMS_WINDOW_SECONDS = .008
ENERGY_HOP_SECONDS = .002
VALLEY_DEPTH_DB = 4.0
SUPPORT_SECONDS = .040
ONSET_NEIGHBOUR_HOPS = 2
BRIDGE_MAX_FRAMES = 2
ANCHOR_MIN_FRAMES = 3
EDGE_MAX_SEARCH_SECONDS = 2048 / 22050 / 2 + 512 / 22050
SILENCE_BELOW_LOCAL_PEAK_DB = 30.0
SILENCE_MIN_SECONDS = .008


def _audio_energy(samples: np.ndarray, sample_rate: int):
    width = max(1, round(RMS_WINDOW_SECONDS * sample_rate))
    # Centred RMS sampled by independently rounded positions (no hop drift).
    padded = np.pad(samples * samples, (width // 2, width - width // 2))
    sums = np.r_[0.0, np.cumsum(padded)]
    indices = np.rint(np.arange(int(np.ceil(len(samples) / sample_rate / ENERGY_HOP_SECONDS)))
                      * ENERGY_HOP_SECONDS * sample_rate).astype(int)
    energy = np.maximum(0, (sums[indices + width] - sums[indices]) / width)
    return indices, energy


def _audio_onsets(samples: np.ndarray, sample_rate: int, source_start: float) -> list[float]:
    """Energy valley supported on both sides, not F0 changes or silence gaps."""
    indices, energy = _audio_energy(samples, sample_rate)
    if not len(energy) or energy.max() <= 0:
        return []
    db = 10 * np.log10(np.maximum(energy, energy.max() * 1e-12))
    radius = max(1, round(SUPPORT_SECONDS / ENERGY_HOP_SECONDS))
    peaks, _ = find_peaks(-db, prominence=VALLEY_DEPTH_DB)
    onsets = []
    for index in peaks:
        # A fully silent RMS window is a gap, not evidence of a reattack.
        if energy[index] <= energy.max() * 1e-8:
            continue
        left = db[max(0, index-radius):index]
        right = db[index+1:min(len(db), index+radius+1)]
        if len(left) and len(right) and min(left.max(), right.max()) - db[index] >= VALLEY_DEPTH_DB:
            onsets.append(source_start + indices[index] / sample_rate)
    return onsets


def decode_onset_aware(contour: MelodyContour, samples: np.ndarray,
                       sample_rate: int) -> list[MelodyNote]:
    """Return a separate onset-aware candidate using fixed parameters.

    samples[0] corresponds to contour.source_start, not an external file offset.
    Audio must cover the contour duration; stereo is averaged to mono. Existing
    contour rests are retained; clear audio silence can only shrink edges. Only a
    touching, monotone <=2-frame bridge near an audio valley may be reassigned;
    a >=3-frame anchor is required on each side, using original G notes once.
    Adjacent same-pitch reattacks can be split by independently detected valleys.
    """
    if (not isinstance(sample_rate, (int, float)) or isinstance(sample_rate, bool)
            or not isfinite(sample_rate) or sample_rate <= 0):
        raise ValueError("Positive finite sample rate required")
    audio = np.asarray(samples, dtype=float)
    if audio.ndim not in (1, 2) or (audio.ndim == 2 and not audio.shape[1]):
        raise ValueError("Audio must be mono or frames-by-channels")
    if not np.isfinite(audio).all():
        raise ValueError("Audio contains nonfinite samples")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    required = round((contour.source_end - contour.source_start) * sample_rate)
    if len(audio) < required:
        raise ValueError("Audio does not cover contour duration")
    onsets = _audio_onsets(audio[:required], sample_rate, contour.source_start)
    energy_indices, energy = _audio_energy(audio[:required], sample_rate)
    energy_times = contour.source_start + energy_indices / sample_rate
    notes = decode_bounded(contour)
    result = [note.model_copy(deep=True) for note in notes]
    removed = set()
    hop = contour.hop_seconds
    for i in range(1, len(notes)-1):
        left, middle, right = notes[i-1:i+2]
        if (left.end != middle.start or middle.end != right.start
                or middle.end-middle.start > BRIDGE_MAX_FRAMES*hop+1e-9
                or min(left.end-left.start, right.end-right.start) < ANCHOR_MIN_FRAMES*hop-1e-9
                or (middle.midi-left.midi)*(right.midi-middle.midi) <= 0):
            continue
        nearby = [t for t in onsets if middle.start-ONSET_NEIGHBOUR_HOPS*hop <= t
                  <= middle.end+ONSET_NEIGHBOUR_HOPS*hop
                  and result[i-1].start < t < result[i+1].end]
        # Multiple plausible attacks are ambiguous; preserve the bridge.
        if len(nearby) != 1:
            continue
        boundary = nearby[0]
        result[i-1] = result[i-1].model_copy(update={"end": boundary})
        result[i+1] = result[i+1].model_copy(update={"start": boundary})
        removed.add(i)
    output = []
    for i, note in enumerate(result):
        if i in removed:
            continue
        start, end = note.start, note.end
        inside = (energy_times >= start) & (energy_times < end)
        local = energy[inside]
        if len(local) and local.max() > 0:
            threshold = local.max() * 10 ** (-SILENCE_BELOW_LOCAL_PEAK_DB / 10)
            active = np.flatnonzero(inside & (energy >= threshold))
            if len(active):
                first, last = energy_times[active[0]], energy_times[active[-1]] + ENERGY_HOP_SECONDS
                if SILENCE_MIN_SECONDS <= first-start <= EDGE_MAX_SEARCH_SECONDS:
                    start = float(first)
                if SILENCE_MIN_SECONDS <= end-last <= EDGE_MAX_SEARCH_SECONDS:
                    end = float(last)
        boundaries = [start, *(t for t in onsets if start < t < end), end]
        for start, end in zip(boundaries, boundaries[1:]):
            output.append(note.model_copy(update={"id": f"onset-{len(output)+1}", "start": start, "end": end}))
    return output
