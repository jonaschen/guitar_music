"""Audibility-only review copies with one gain across A/B; no timing changes."""
import numpy as np


def focus_mix(source, a, b):
    waves=[np.asarray(x,dtype=np.float64) for x in (source,a,b)]
    if not waves[0].size or any(x.ndim!=1 or x.shape!=waves[0].shape or not np.isfinite(x).all() for x in waves):
        raise ValueError('Requires aligned, finite mono source and A/B mixes')
    source,a,b=waves
    # Existing packets use an identical source track and master gain in both mixes.
    # Subtraction retains PCM rounding noise (at most one LSB), not new analysis.
    solo_a,solo_b=a-source,b-source
    outputs={'source-focus':source*.5,'a-focus':source*.5+solo_a,'b-focus':source*.5+solo_b,
             'a-solo':solo_a,'b-solo':solo_b}
    gain=min(1.,.95/max(1e-12,*(float(np.max(np.abs(x))) for x in outputs.values())))
    return {k:v*gain for k,v in outputs.items()},gain
