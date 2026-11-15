"""Independent-reference metrics. No reference means no accuracy claim."""
from collections import defaultdict

from .song_structure import normalize_sections

UNRESOLVED = {'unknown', 'start', 'end'}


def _boundary_score(predicted, reference, tolerance):
    # Sorted equal-radius intervals: earliest feasible one-to-one matching maximizes
    # match count. Recording endpoints are excluded before this function is called.
    i = j = matched = 0
    while i < len(predicted) and j < len(reference):
        if abs(predicted[i] - reference[j]) <= tolerance:
            matched += 1
            i += 1
            j += 1
        elif predicted[i] < reference[j]:
            i += 1
        else:
            j += 1
    return _boundary_counts(matched, len(predicted), len(reference))


def _boundary_counts(matched, prediction_count, reference_count):
    if not reference_count:
        return dict(matched=0, prediction_count=prediction_count, reference_count=0,
                    precision=None, recall=None, f1=None)
    precision = matched / prediction_count if prediction_count else 0.
    recall = matched / reference_count
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.
    return dict(matched=matched, prediction_count=prediction_count, reference_count=reference_count,
                precision=precision, recall=recall, f1=f1)


def compare_structure(raw: list[dict], reference: dict, duration: float, audio_sha256: str) -> dict:
    """Score names by overlap duration, boundaries separately at fixed 0.5/3 s.

    Annotation provenance is mandatory but its independence cannot be proved by
    software; the supplied evidence still needs human review. Unannotated reference
    time is excluded from accuracy and separately lowers reference coverage.
    """
    if (reference.get('audio_sha256') != audio_sha256
            or reference.get('independent_of_candidate') is not True
            or not reference.get('annotator') or not reference.get('evidence')):
        raise ValueError('A source-matched independent reference with provenance is required')
    predicted = normalize_sections(raw, duration)
    truth = normalize_sections(reference['sections'], duration)
    confusion = defaultdict(float)
    seconds = defaultdict(float)
    instances = defaultdict(int)
    omissions = 0
    for actual in truth:
        if actual['label'] in UNRESOLVED:
            continue
        label = actual['label']
        seconds[label] += actual['end'] - actual['start']
        instances[label] += 1
        correct_overlap = 0.
        for estimated in predicted:
            overlap = max(0., min(actual['end'], estimated['end']) - max(actual['start'], estimated['start']))
            if overlap:
                confusion[(label, estimated['label'])] += overlap
                if estimated['label'] == label:
                    correct_overlap += overlap
        if label == 'chorus' and correct_overlap == 0:
            omissions += 1
    annotated = sum(seconds.values())
    if not annotated:
        raise ValueError('Reference contains no annotated semantic labels')
    # Exclude boundaries touching unknown annotation. Candidate boundaries inside
    # continuous known annotation remain false positives if they do not match.
    known_spans = []
    for section in truth:
        if section['label'] not in UNRESOLVED:
            if known_spans and known_spans[-1][1] == section['start']:
                known_spans[-1][1] = section['end']
            else:
                known_spans.append([section['start'], section['end']])
    actual_boundaries = [a['end'] for a, b in zip(truth, truth[1:])
                         if a['label'] not in UNRESOLVED and b['label'] not in UNRESOLVED]
    predicted_boundaries = [s['end'] for s in predicted[:-1]
                            if any(start < s['end'] < end for start, end in known_spans)]
    boundaries = {}
    for tolerance in [.5, 3.]:
        matches = sum(_boundary_score([b for b in predicted_boundaries if start < b < end],
                                      [b for b in actual_boundaries if start < b < end],
                                      tolerance)['matched'] for start, end in known_spans)
        boundaries[str(tolerance)] = _boundary_counts(matches, len(predicted_boundaries), len(actual_boundaries))
    return dict(audio_sha256=audio_sha256, reference_coverage=annotated / duration,
                label_accuracy=sum(value for (a, p), value in confusion.items() if a == p) / annotated,
                recall={label: confusion[(label, label)] / seconds[label] if seconds[label] else None
                        for label in ['verse', 'chorus']},
                reference_seconds=dict(seconds), reference_instances=dict(instances),
                confusion_seconds=[dict(reference=a, predicted=p, seconds=value)
                                   for (a, p), value in sorted(confusion.items()) if value],
                whole_chorus_omissions=omissions,
                boundaries=boundaries,
                correction_fraction=None, quality_gate='not_decided',
                note='Correction effort and dataset-level gates still require separate evidence.')


def assess_reports(reports: list[dict], gate: dict) -> dict:
    """Apply fixed gates to one candidate's references, never production readiness.

    The caller must group source-verified compare_structure outputs from the same
    protocol/model/version. This numeric reducer does not select experiment runs.
    """
    import math
    if not reports:
        return dict(status='awaiting_reference', checks={}, ready_as_default=False)
    checks = {}

    def check(name, value, threshold, maximum=False, rate=False):
        if value is None:
            checks[name] = None
        elif (not isinstance(value, (int, float)) or not math.isfinite(value)
              or value < 0 or rate and value > 1):
            checks[name] = False
        else:
            checks[name] = value <= threshold if maximum else value >= threshold

    sources = [r.get('audio_sha256') for r in reports]
    checks['unique_recordings'] = all(sources) and len(set(sources)) == len(sources)
    for index, report in enumerate(reports):
        prefix = f'song_{index + 1}.'
        for field, threshold in [
                ('reference_coverage', 'full_song_annotation_coverage_min'),
                ('label_accuracy', 'duration_weighted_label_accuracy_per_song_min')]:
            check(prefix + field, report.get(field), gate[threshold], rate=True)
        for label in ['verse', 'chorus']:
            # A genuinely absent reference class is N/A for this song; dataset
            # minimum amounts below still require both classes in the evidence.
            if report['reference_seconds'].get(label, 0) > 0:
                check(prefix + label + '_recall', report['recall'].get(label),
                      gate['verse_chorus_recall_per_song_min'], rate=True)
        check(prefix + 'whole_chorus_omissions', report.get('whole_chorus_omissions'),
              gate['whole_chorus_omissions_max'], maximum=True)
        check(prefix + 'boundary_f1_3s', report['boundaries']['3.0'].get('f1'),
              gate['boundary_f1_3s_min'], rate=True)
        check(prefix + 'correction_fraction', report.get('correction_fraction'),
              gate['section_correction_fraction_max'], maximum=True, rate=True)
    for label in ['verse', 'chorus']:
        check(label + '_reference_seconds', sum(r['reference_seconds'].get(label, 0) for r in reports),
              gate['verse_and_chorus_min_seconds_each'])
        check(label + '_reference_instances', sum(r['reference_instances'].get(label, 0) for r in reports),
              gate['verse_and_chorus_min_instances_each_across_reference_set'])
    status = ('failed' if False in checks.values() else 'awaiting_human' if None in checks.values()
              else 'passed_on_reference_set')
    return dict(status=status, checks=checks, ready_as_default=False,
                note='Reference-set result only; held-out evidence and product adoption are separate decisions.')
