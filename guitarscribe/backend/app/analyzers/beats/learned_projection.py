"""Conservative projection of detected downbeats; never invent a first-bar phase."""
from bisect import bisect_left
from math import isfinite
from numbers import Real
from statistics import median

from ...models.analysis import BeatAnalysis, BeatInfo


def project_learned_beats(beats: list[float], downbeats: list[float], engine_version: str) -> BeatAnalysis:
    for name, times in [('beats', beats), ('downbeats', downbeats)]:
        if len(times)<2 or any(isinstance(t,bool) or not isinstance(t,Real) or not isfinite(t) or t<0 for t in times):
            raise ValueError(f'{name} requires at least two finite nonnegative times')
        if any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError(f'{name} must be strictly increasing')
    indices=[]
    for time in downbeats:
        pos=bisect_left(beats,time)
        matches=[i for i in [pos-1,pos] if 0<=i<len(beats) and abs(beats[i]-time)<=1e-6]
        if len(matches)!=1:raise ValueError('Downbeat must identify exactly one detected beat')
        indices.append(matches[0])
    gaps={b-a for a,b in zip(indices,indices[1:])}
    if len(gaps)!=1 or next(iter(gaps)) not in (3,4):
        raise ValueError('Inconsistent meter or missing beats/downbeats; explicit review required')
    meter=next(iter(gaps));first=indices[0]
    numbered=[(i-first)%meter+1 for i in range(len(beats))]
    if [i for i,n in enumerate(numbered) if n==1]!=indices:
        raise ValueError('Projection would invent an unobserved downbeat at an edge')
    return BeatAnalysis(bpm=60/median(b-a for a,b in zip(beats,beats[1:])),
        time_signature=f'{meter}/4',
        beats=[BeatInfo(time=float(t),beat=numbered[i],measure=(i-first)//meter+1,confidence=0)
               for i,t in enumerate(beats)],
        downbeat_indices=indices,confidence=0,engine='beat-this',engine_version=engine_version,
        warnings=['Model confidence is not calibrated. Only consistent 3/4 or 4/4 projections supported; quarter-note beat unit assumed.',
                  'Measure 0 contains pickup beats before the first detected downbeat.'])
