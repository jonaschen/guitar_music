"""Conservative eligibility checks for a fixed decoder fallback, not accuracy scores.

No correction, deletion, phase selection, or tempo stretching happens here.
The caller must keep the primary grid whenever it projects successfully.
"""
from math import isfinite

from .learned_projection import project_learned_beats
from .pulse_intervals import describe_pulse_intervals
from .timing_diagnostics import describe_observations

POLICY = 'fixed-dbn-recovery-v1'
MATCH_TOLERANCE = .070  # Same 70 ms peak neighbourhood used by the minimal decoder.


def check_recovery(primary_beats, primary_downbeats, beats, downbeats, duration, version):
    primary = describe_observations(primary_beats, primary_downbeats)
    report = dict(policy=POLICY, eligible=False, reasons=[], match_tolerance_seconds=MATCH_TOLERANCE,
                  preserved_spans=[], musical_verdict='unconfirmed')
    if not isfinite(duration) or duration <= 0:
        report['reasons'].append('invalid_duration')
        return None, report
    try:
        projected = project_learned_beats(beats, downbeats, version)
    except ValueError as error:
        report['reasons'].append('inconsistent_candidate')
        report['projection_error'] = str(error)
        return None, report
    if beats[-1] >= duration:
        report['reasons'].append('candidate_outside_audio')
    # A structurally legal half/double-density change must never pass silently.
    # Legitimate variable-tempo music can also be rejected: no auto-repair here.
    if describe_pulse_intervals(beats)['deviations']:
        report['reasons'].append('candidate_pulse_density_ambiguity')
    spans = primary['structurally_consistent_spans']
    if not spans:
        report['reasons'].append('no_continuous_primary_reference')
    for span in spans:
        detail = dict(span)
        for name, before, after in [('beats', primary_beats, beats), ('downbeats', primary_downbeats, downbeats)]:
            original = [t for t in before if span['start'] <= t <= span['end']]
            candidate = [t for t in after if span['start']-MATCH_TOLERANCE <= t <= span['end']+MATCH_TOLERANCE]
            matches = len(original) == len(candidate) and all(abs(a-b) <= MATCH_TOLERANCE for a, b in zip(original, candidate))
            detail[name+'_preserved'] = matches
            if not matches and 'continuous_primary_'+name+'_changed' not in report['reasons']:
                report['reasons'].append('continuous_primary_'+name+'_changed')
        report['preserved_spans'].append(detail)
    report['eligible'] = not report['reasons']
    return (projected if report['eligible'] else None), report
