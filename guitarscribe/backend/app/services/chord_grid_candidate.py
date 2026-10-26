"""Separate eighth-note chord score, shared by notation and standard playback.

No inference or beat correction. Preserve short events/gaps that would collapse.
"""
import math
from bisect import bisect_left

from ..models.score import SongScore


def build_chord_grid_candidate(score: SongScore):
    duration=score.song.duration_seconds
    if score.analysis.time_signature!='4/4':raise ValueError('This preview supports a quarter-note beat grid in 4/4 only')
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration')
    if len(score.beats)<2 or any(not math.isfinite(b.time) or b.time<0 for b in score.beats):
        raise ValueError('Requires finite beat grid')
    if any(a.time>=b.time for a,b in zip(score.beats,score.beats[1:])):
        raise ValueError('Beat grid must increase')
    if len({c.id for c in score.chords})!=len(score.chords):raise ValueError('Duplicate chord IDs')
    if any(not math.isfinite(c.start+c.end) or not 0<=c.start<c.end<=duration for c in score.chords):
        raise ValueError('Invalid chord spans')
    if any(a.end>b.start for a,b in zip(score.chords,score.chords[1:])):
        raise ValueError('Chords must be ordered and non-overlapping')
    grid=sorted({b.time for b in score.beats if b.time<=duration} |
                {(a.time+b.time)/2 for a,b in zip(score.beats,score.beats[1:]) if (a.time+b.time)/2<=duration})
    if len(grid)<2:raise ValueError('Insufficient beats within the excerpt')
    def nearest(t):
        # Preserve cropped edges and uncovered intro/outro, without extrapolation.
        if t==0 or t==duration or not grid[0]<=t<=grid[-1]:return t
        i=bisect_left(grid,t)
        return min(grid[max(0,i-1):min(len(grid),i+1)],key=lambda x:(abs(x-t),x))
    edges={0.0,duration}|{t for c in score.chords for t in [c.start,c.end]}
    proposed={t:nearest(t) for t in edges}
    protected={t for c in score.chords if c.edited for t in [c.start,c.end]}
    reasons={t:'manual_boundary' for t in protected}
    for t in protected:proposed[t]=t
    # Nearest-grid mapping may collapse a real short chord/rest. Restore both
    # ends of every conflict, iterating only until no further restoration occurs.
    intervals=[(c.start,c.end) for c in score.chords]
    intervals += [(a.end,b.start) for a,b in zip(score.chords,score.chords[1:]) if a.end<b.start]
    if score.chords:
        if score.chords[0].start>0:intervals.append((0.0,score.chords[0].start))
        if score.chords[-1].end<duration:intervals.append((score.chords[-1].end,duration))
    while True:
        conflicts={t for a,b in intervals if proposed[a]>=proposed[b] for t in [a,b] if proposed[t]!=t}
        if not conflicts:break
        for t in conflicts:proposed[t]=t;reasons[t]='would_collapse_chord_or_rest'
    candidate=score.model_copy(deep=True);changes=[]
    for old,new in zip(score.chords,candidate.chords):
        new.start=proposed[old.start];new.end=proposed[old.end]
        assert new.end>new.start
        if (new.start,new.end)!=(old.start,old.end):
            changes.append(dict(chord_id=old.id,original=[old.start,old.end],candidate=[new.start,new.end]))
    assert all(a.end<=b.start for a,b in zip(candidate.chords,candidate.chords[1:]))
    candidate.provenance.parameters['chord_grid_candidate']='nearest-eighth-v1'
    candidate.analysis.warnings.append('Experimental eighth-note chord timing candidate on the existing beat grid. Original detection retained separately; short chords/rests and manual boundaries may remain unquantized. Melody is unchanged.')
    return candidate,dict(policy='nearest-eighth-v1',changes=changes,
        protected=[dict(time=t,reason=reasons[t]) for t in sorted(reasons)],
        unquantized_edges=sorted(t for t in set(proposed.values()) if t not in grid and t not in {0,duration}),
        applied=False,saved=False,melody_changed=False)
