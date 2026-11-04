"""Read-only local bar previews; never repair a beat or modify a working score."""
import json
from bisect import bisect_left, bisect_right
from math import isfinite
from statistics import median

from ..analyzers.beats.guarded_recovery import MATCH_TOLERANCE
from ..analyzers.beats.timing_diagnostics import describe_observations

POLICY = 'observed-local-bars-v1'
MIN_BARS = 4


def local_bar_preview(primary, candidate, duration):
    """Keep only runs of four observed bars with decoder agreement and stable density.

    The whole-recording pulse baseline uses the existing recovery guard. Both
    decoders must retain the same ordered beats/downbeats. Unknown gaps stay
    unknown; numbering restarts per region because missing bars aren't counted.
    Agreement is not independent model evidence or proof of musical correctness.
    """
    result = dict(policy=POLICY, regions=[], covered_seconds=0.0,
                  musical_verdict='unconfirmed', playback_changed=False)
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not isfinite(duration) or duration <= 0:
        return result
    if not isinstance(primary, dict) or not isinstance(candidate, dict):
        return result
    a = describe_observations(primary.get('beats', []), primary.get('downbeats', []))
    b = describe_observations(candidate.get('beats', []), candidate.get('downbeats', []))
    if not a['aligned_observations'] or not b['aligned_observations']:
        return result
    beats, downs = a['beats'], a['downbeats']
    baseline = median(y-x for x, y in zip(beats, beats[1:]))
    runs, run = [], []

    def flush():
        if len(run) >= MIN_BARS:
            runs.append(dict(start=run[0]['start'], end=run[-1]['end'],
                             beats_per_bar=len(run[0]['beats'])-1, bars=list(run)))
        run.clear()

    for start, end in zip(downs, downs[1:]):
        first = bisect_left(beats, start)
        observed = beats[first:bisect_right(beats, end)]
        meter = len(observed)-1
        intervals = [y-x for x, y in zip(observed, observed[1:])]
        good = end <= duration and meter in (3, 4) and all(
            .6 < interval/baseline < 1.75 for interval in intervals)
        # Equal counts at two densities can put the global median between them.
        # Split at an abrupt local change as well; never join both regimes into
        # one apparently continuous region just because the median masks it.
        adjacent = ([beats[first]-beats[first-1]] if first else []) + intervals
        good = good and all(.6 < y/x < 1.75 for x, y in zip(adjacent, adjacent[1:]))
        for original, other in [(observed, b['beats']), ([start, end], b['downbeats'])]:
            matched = other[bisect_left(other, start-MATCH_TOLERANCE):bisect_right(other, end+MATCH_TOLERANCE)]
            good = good and len(original) == len(matched) and all(
                abs(x-y) <= MATCH_TOLERANCE for x, y in zip(original, matched))
        if not good or run and len(run[-1]['beats']) != len(observed):
            flush()
        if good:
            run.append(dict(start=start, end=end, beats=observed))
    flush()
    result['regions'] = runs
    result['covered_seconds'] = sum(r['end']-r['start'] for r in runs)
    return result


def preview_for_job(job, directory):
    """Read existing artifacts only, including for old jobs; do not infer or save."""
    score = job.score
    result = local_bar_preview({}, {}, score.song.duration_seconds)
    result.update(job_id=job.id, duration_seconds=score.song.duration_seconds,
                  source_start_seconds=score.song.source_start_seconds)
    if score.analysis.timing_status != 'unmetered':
        result['reason'] = 'full_grid_available'
        return result
    path = directory / 'timing-recovery.json'
    if not path.is_file():
        result['reason'] = 'comparison_unavailable'
        return result
    try:
        evidence = json.loads(path.read_text())
        computed = local_bar_preview(evidence.get('primary'), evidence.get('candidate'), score.song.duration_seconds)
    except (ValueError, TypeError, AttributeError, OSError):
        result['reason'] = 'comparison_unreadable'
        return result
    result.update(computed)
    result['reason'] = 'local_preview_available' if result['regions'] else 'no_agreeing_local_bars'
    return result
