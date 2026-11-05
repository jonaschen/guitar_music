"""Reference-only timing metrics. Regularity and model agreement are not truth."""

from __future__ import annotations

import mir_eval
import numpy as np


def _events(values, start: float, end: float) -> np.ndarray:
    events = np.asarray(list(values), dtype=float)
    if events.ndim != 1 or not np.all(np.isfinite(events)):
        raise ValueError("Timing events must be finite, one-dimensional seconds")
    if np.any(events < 0) or np.any(np.diff(events) <= 0):
        raise ValueError("Timing events must be nonnegative, unique and increasing")
    return events[(events >= start) & (events < end)]


def reference_timing_metrics(reference_beats, estimated_beats, reference_downbeats,
                             estimated_downbeats, *, start: float, end: float) -> dict:
    """Compare the same half-open excerpt, without shifting or rescaling either side.

    AML tolerates alternate metrical levels; it must never replace CML or be used
    as a product acceptance score. No default five-second trim is applied.
    Missing annotations remain unknown, including an explicitly empty excerpt.
    """
    if not np.isfinite([start, end]).all() or start < 0 or end <= start:
        raise ValueError("Invalid evaluation interval")
    ref = _events(reference_beats, start, end)
    est = _events(estimated_beats, start, end)
    ref_down = _events(reference_downbeats, start, end)
    est_down = _events(estimated_downbeats, start, end)
    result = {
        "beat_f_measure": float(mir_eval.beat.f_measure(ref, est)) if len(ref) and len(est) else (0.0 if len(ref) else "not_annotated"),
        "downbeat_f_measure": float(mir_eval.beat.f_measure(ref_down, est_down)) if len(ref_down) and len(est_down) else (0.0 if len(ref_down) else "not_annotated"),
        "reference_beat_count": len(ref), "estimated_beat_count": len(est),
        "reference_downbeat_count": len(ref_down), "estimated_downbeat_count": len(est_down),
        "beat_count_ratio": len(est) / len(ref) if len(ref) else "not_annotated",
    }
    keys = ("beat_cml_continuous", "beat_cml_total", "beat_aml_continuous", "beat_aml_total")
    if len(ref) < 2:
        result.update(dict.fromkeys(keys, "insufficient_reference" if len(ref) else "not_annotated"))
    elif len(est) < 2:
        result.update(dict.fromkeys(keys, 0.0))
    else:
        result.update(zip(keys, map(float, mir_eval.beat.continuity(ref, est))))
    if len(ref_down) and len(est_down):
        result["first_downbeat_phase_error_seconds"] = float(np.min(abs(est_down - ref_down[0])))
    return result
