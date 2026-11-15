import pytest
from app.evaluation.song_structure_metrics import compare_structure


def reference(sections):
    return {'audio_sha256': 'fixed-source', 'independent_of_candidate': True,
            'annotator': 'independent fixture', 'evidence': 'synthetic known intervals', 'sections': sections}


def sections(split=40):
    return [{'start': 0, 'end': split, 'label': 'verse'}, {'start': split, 'end': 80, 'label': 'chorus'}]


def test_perfect_labels_and_internal_boundaries():
    report = compare_structure(sections(), reference(sections()), 80, 'fixed-source')
    assert report['label_accuracy'] == 1
    assert report['recall'] == {'verse': 1, 'chorus': 1}
    assert report['boundaries']['3.0']['f1'] == 1
    assert report['boundaries']['3.0']['reference_count'] == 1


def test_all_chorus_is_not_good_structure_despite_perfect_boundaries():
    candidate = sections()
    candidate[0]['label'] = 'chorus'
    report = compare_structure(candidate, reference(sections()), 80, 'fixed-source')
    assert report['label_accuracy'] == .5
    assert report['recall']['verse'] == 0
    assert report['boundaries']['3.0']['f1'] == 1


@pytest.mark.parametrize('shift,half,three', [(1, 0, 1), (4, 0, 0)])
def test_boundary_tolerances_do_not_count_song_endpoints(shift, half, three):
    report = compare_structure(sections(40 + shift), reference(sections()), 80, 'fixed-source')
    assert report['boundaries']['0.5']['f1'] == half
    assert report['boundaries']['3.0']['f1'] == three


def test_one_prediction_cannot_match_two_reference_boundaries():
    truth = [{'start': 0, 'end': 39, 'label': 'verse'},
             {'start': 39, 'end': 41, 'label': 'bridge'},
             {'start': 41, 'end': 80, 'label': 'chorus'}]
    report = compare_structure(sections(), reference(truth), 80, 'fixed-source')
    assert report['boundaries']['3.0']['matched'] == 1
    assert report['boundaries']['3.0']['recall'] == .5


def test_missing_chorus_and_unknown_candidate_are_counted_as_errors():
    report = compare_structure([{'start': 0, 'end': 80, 'label': 'unknown'}], reference(sections()), 80, 'fixed-source')
    assert report['whole_chorus_omissions'] == 1
    assert report['label_accuracy'] == 0
    assert report['reference_coverage'] == 1


def test_unannotated_time_is_not_false_reference_and_boundary_is_excluded():
    truth = [{'start': 0, 'end': 40, 'label': 'verse'}]
    report = compare_structure(sections(), reference(truth), 80, 'fixed-source')
    assert report['reference_coverage'] == .5
    assert report['label_accuracy'] == 1
    assert report['recall']['chorus'] is None
    assert report['boundaries']['3.0']['reference_count'] == 0
    assert report['boundaries']['3.0']['f1'] is None


@pytest.mark.parametrize('field,value', [('audio_sha256','wrong'), ('independent_of_candidate',False), ('annotator',''), ('evidence','')])
def test_missing_or_nonindependent_reference_rejected(field, value):
    truth = reference(sections());truth[field] = value
    with pytest.raises(ValueError):
        compare_structure(sections(), truth, 80, 'fixed-source')


def test_boundaries_cannot_match_across_separate_annotation_islands():
    truth = [{'start': 0, 'end': 9, 'label': 'verse'}, {'start': 9, 'end': 10, 'label': 'bridge'},
             {'start': 11, 'end': 20, 'label': 'chorus'}]
    candidate = [{'start': 0, 'end': 11.5, 'label': 'verse'}, {'start': 11.5, 'end': 20, 'label': 'chorus'}]
    report = compare_structure(candidate, reference(truth), 20, 'fixed-source')
    assert report['boundaries']['3.0']['matched'] == 0
    assert report['boundaries']['3.0']['prediction_count'] == 1
    assert report['boundaries']['3.0']['reference_count'] == 1
    assert report['boundaries']['3.0']['f1'] == 0


def protocol_gate():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parents[2] / 'docs/evaluation/song-structure-protocol-v2-2026-11-15.json').read_text())['quality_gate']


def good_reports():
    reports = []
    for source in ['source-a', 'source-b']:
        truth = reference(sections());truth['audio_sha256'] = source
        reports.append(compare_structure(sections(), truth, 80, source))
    for report in reports:
        report['correction_fraction'] = .1
    return reports


def test_dataset_gate_needs_references_and_correction_evidence():
    from app.evaluation.song_structure_metrics import assess_reports
    assert assess_reports([], protocol_gate())['status'] == 'awaiting_reference'
    reports = good_reports();reports[0]['correction_fraction'] = None
    assert assess_reports(reports, protocol_gate())['status'] == 'awaiting_human'
    assert assess_reports(reports, protocol_gate())['ready_as_default'] is False


def test_dataset_gate_checks_preregistered_minimum_class_amounts():
    from app.evaluation.song_structure_metrics import assess_reports
    assert assess_reports(good_reports()[:1], protocol_gate())['status'] == 'failed'
    assert assess_reports(good_reports(), protocol_gate())['status'] == 'passed_on_reference_set'
    assert assess_reports(good_reports(), protocol_gate())['ready_as_default'] is False


@pytest.mark.parametrize('field,value', [('label_accuracy', .84), ('reference_coverage', .94),
                                        ('whole_chorus_omissions', 1), ('correction_fraction', .26)])
def test_dataset_gate_does_not_relax_failure_thresholds(field, value):
    from app.evaluation.song_structure_metrics import assess_reports
    reports = good_reports();reports[0][field] = value
    assert assess_reports(reports, protocol_gate())['status'] == 'failed'


def test_dataset_gate_checks_both_semantics_and_boundaries():
    from app.evaluation.song_structure_metrics import assess_reports
    reports = good_reports();reports[0]['recall']['verse'] = .79
    assert assess_reports(reports, protocol_gate())['status'] == 'failed'
    reports = good_reports();reports[0]['boundaries']['3.0']['f1'] = .79
    assert assess_reports(reports, protocol_gate())['status'] == 'failed'


def test_dataset_gate_rejects_duplicate_recordings_as_new_evidence():
    from app.evaluation.song_structure_metrics import assess_reports
    report = good_reports()[0]
    assert assess_reports([report, report], protocol_gate())['status'] == 'failed'
