"""Read-only evidence for rejected beat grids; never repairs or selects a grid."""
from bisect import bisect_left
from math import isfinite
from .pulse_intervals import describe_pulse_intervals


def describe_observations(beats, downbeats):
    beats, downbeats = list(beats), list(downbeats)
    valid = len(beats) >= 2 and len(downbeats) >= 2 and all(isinstance(t, (int, float)) and not isinstance(t, bool) and isfinite(t) and t >= 0
                for t in [*beats, *downbeats])
    valid = valid and all(b > a for times in (beats, downbeats) for a, b in zip(times, times[1:]))
    indices = []
    if valid:
        for t in downbeats:
            p = bisect_left(beats, t)
            matches = [i for i in (p-1, p) if 0 <= i < len(beats) and abs(beats[i]-t) <= 1e-6]
            if len(matches) != 1:
                valid = False
                break
            indices.append(matches[0])
    gaps = [b-a for a, b in zip(indices, indices[1:])] if valid else []
    spans = []
    i = 0
    while i < len(gaps):
        j = i + 1
        while j < len(gaps) and gaps[j] == gaps[i]:
            j += 1
        # Diagnostic only: four observed full bars, bounded by observed downbeats.
        if gaps[i] in (3, 4) and j-i >= 4:
            spans.append(dict(start=downbeats[i], end=downbeats[j], beats_per_bar=gaps[i], bars=j-i))
        i = j
    clean = lambda values: [float(t) if isinstance(t, (int, float)) and isfinite(t) else None for t in values]
    return dict(schema_version='1.0', beats=clean(beats), downbeats=clean(downbeats),
                aligned_observations=valid, beats_per_downbeat_interval=gaps,
                structurally_consistent_spans=spans, musical_verdict='unconfirmed',
                pulse_intervals=describe_pulse_intervals(beats), automatic_repair=False)


class BeatProjectionError(ValueError):
    def __init__(self, reason, evidence):
        super().__init__(reason)
        self.evidence = evidence
