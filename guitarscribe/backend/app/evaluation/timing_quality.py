"""Common, uncalibrated timing checks for offline comparisons, not accuracy."""
from ..analyzers.beats.learned_projection import project_learned_beats
from ..analyzers.beats.timing_diagnostics import describe_observations
from ..services.analysis_health import pulse_density_summary


def timing_quality(beats, downbeats, duration, version='offline'):
    report = describe_observations(beats, downbeats)
    issues = []
    try:
        projection = project_learned_beats(beats, downbeats, version)
        report['projection'] = projection.model_dump(mode='json')
    except ValueError as error:
        issues.append('inconsistent_bars')
        report['projection_error'] = str(error)
    if beats and beats[-1] >= duration:
        issues.append('outside_audio')
    if report['pulse_intervals']['deviations']:
        issues.append('pulse_density_deviations')
    if report['aligned_observations']:
        density = pulse_density_summary(beats, duration)
        report['density'] = density
        if density['octave_density_changes']:
            issues.append('window_density_switch')
        gaps = [b-a for a, b in zip(beats, beats[1:])]
        abrupt = [dict(time=beats[i+1], ratio=b/a) for i, (a, b) in enumerate(zip(gaps, gaps[1:]))
                  if b/a <= .6 or b/a >= 1.75]
        report['adjacent_density_changes'] = abrupt
        if abrupt:
            issues.append('adjacent_density_switch')
    report.update(engineering_pass=not issues, issues=issues, musical_accuracy_evaluated=False)
    return report
