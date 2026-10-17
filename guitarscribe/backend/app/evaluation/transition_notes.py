"""Isolated hypothesis: short monotone F0 transitions are not separate notes.

No production decoder changes, no duration deletion, no rest filling. Parameters
are deliberately fixed for this experiment, not calibrated music accuracy.
"""
from math import log2
import numpy as np
from ..models.analysis import MelodyNote
from ..models.melody_contour import MelodyContour


def repair_transitions(notes: list[MelodyNote], contour: MelodyContour,
                       attack_times: list[float]) -> tuple[list[MelodyNote], list[dict]]:
    """Reassign only low-confidence, one/two-frame monotone bridge notes.

    Stable neighbours mean >=3 frames, not verified musical notes. All bridge
    notes must have confidence <.6; a bridge totals <=5 frames. Detected attacks
    veto the whole bridge. Legato ornaments may still be mistaken for a glide.
    Boundaries are selected from source frames by minimum pitch error to the
    two existing endpoint pitches. No new pitches or silent frames are created.
    """
    result = [n.model_copy(deep=True) for n in notes]
    changes = []
    removed = set()
    hop = contour.hop_seconds
    for i, left in enumerate(notes):
        if left.end-left.start < 3*hop-1e-8:
            continue
        j = i+1
        while j < len(notes) and notes[j].end-notes[j].start <= 2*hop+1e-8 and notes[j-1].end == notes[j].start:
            j += 1
        if j == i+1 or j == len(notes):
            continue
        right = notes[j]
        bridge = notes[i+1:j]
        delta = right.midi-left.midi
        if (right.start != bridge[-1].end or right.end-right.start < 3*hop-1e-8
                or right.start-left.end > 5*hop+1e-8 or delta == 0
                or any(n.confidence is None or n.confidence >= .6 for n in bridge)):
            continue
        path = [left, *bridge, right]
        if not all((b.midi-a.midi)*delta > 0 for a,b in zip(path,path[1:])):
            continue
        if any(left.end-hop/2 <= t <= right.start+hop/2 for t in attack_times):
            continue
        first = round((left.end-contour.source_start)/hop)
        last = round((right.start-contour.source_start)/hop)
        frames = contour.frequencies_hz[first:last]
        if not frames or any(hz is None for hz in frames):
            continue
        pitches = np.array([69+12*log2(hz/440) for hz in frames])
        # Global split, not independent assignment: exactly one boundary survives.
        left_cost = np.r_[0, np.cumsum((pitches-left.midi)**2)]
        right_cost = np.r_[np.cumsum(((pitches-right.midi)**2)[::-1])[::-1], 0]
        split = int(np.argmin(left_cost+right_cost))
        boundary = contour.source_start+(first+split)*hop
        # Reuse exact original endpoints, avoiding floating-point micro-rests.
        if split == 0: boundary = left.end
        if split == len(frames): boundary = right.start
        result[i] = result[i].model_copy(update={"end":boundary})
        result[j] = result[j].model_copy(update={"start":boundary})
        removed.update(range(i+1,j))
        changes.append(dict(start=left.end,end=right.start,boundary=boundary,
                            left_id=left.id,right_id=right.id,
                            removed_ids=[n.id for n in bridge],
                            pitches=[n.midi for n in path],
                            left_end_shift=boundary-left.end,
                            right_start_shift=boundary-right.start,
                            reassigned_frames=len(frames),
                            max_source_error_semitones=float(max(
                                np.abs(pitches[:split]-left.midi).max(initial=0),
                                np.abs(pitches[split:]-right.midi).max(initial=0))),
                            reason="low_confidence_monotone_transition"))
    return [n for i,n in enumerate(result) if i not in removed], changes


def detect_attacks(audio: np.ndarray, sample_rate: int, hop_seconds: float) -> list[float]:
    """Conservative veto: spectral growth accompanied by local energy growth.

    Fixed 23ms-scale windows aligned to contour frames. This only protects
    possible attacks; absence is not proof that a musical onset did not occur.
    """
    if sample_rate <= 0 or hop_seconds <= 0:
        raise ValueError("Positive audio timing required")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if not np.isfinite(audio).all():
        raise ValueError("Nonfinite audio")
    hop = max(1, round(sample_rate*hop_seconds))
    width = 2*hop
    padded = np.pad(audio, (hop, width))
    spectra, energies = [], []
    for frame_index in range(int(np.ceil(len(audio)/(sample_rate*hop_seconds)))):
        index = round(frame_index*sample_rate*hop_seconds)
        frame = padded[index:index+width]
        energies.append(float(np.sqrt(np.mean(frame**2))))
        spectra.append(np.abs(np.fft.rfft(frame*np.hanning(width))))
    if len(spectra) < 4:
        return []
    spectrum = np.array(spectra)
    flux = np.maximum(0,np.diff(spectrum,axis=0)).sum(axis=1)
    flux = np.r_[0,flux]
    energy = np.array(energies)
    attacks = []
    for i in range(2,len(energy)-1):
        local = flux[max(0,i-10):min(len(flux),i+11)]
        threshold = np.median(local)+2*np.median(np.abs(local-np.median(local)))
        if (flux[i] > max(threshold,1e-8) and flux[i] >= flux[i-1] and flux[i] > flux[i+1]
                and energy[i] > max(1e-5,1.25*min(energy[i-2:i]))):
            attacks.append(round(i*sample_rate*hop_seconds)/sample_rate)
    return attacks
