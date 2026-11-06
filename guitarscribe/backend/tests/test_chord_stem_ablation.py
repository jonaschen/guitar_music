"""Acceptance guards must reject harm even when average targets improve."""
import copy
from scripts.run_chord_stem_ablation import decision


def rows():
    result=[]
    for name in ['control'+str(i) for i in range(6)]+['SWD_HU33_'+x for x in ('04','18','21')]:
        baseline=dict(summary=dict(interval=[0.,40.],metrics={k:dict(accuracy=.5,scored_seconds=40.) for k in ('root','majmin')},
                      category_seconds=dict(missed_chord=0.,false_chord=0.)),boundaries=dict(precision=.8,recall=.8))
        candidate=copy.deepcopy(baseline)
        if name.startswith('SWD'):candidate['summary']['metrics']['root']['accuracy']+=.06
        result.append(dict(recording_id=name,baseline=baseline,no_vocals=candidate))
    return result


def test_mean_improvement_cannot_hide_harmed_negative_control():
    data=rows(); assert decision(data)['passed']
    data[0]['no_vocals']['summary']['metrics']['root']['accuracy']-=.021
    assert not decision(data)['passed']


def test_one_big_target_gain_cannot_replace_two_improved_sources():
    data=rows()
    for row in data[-3:]:row['no_vocals']['summary']['metrics']['root']['accuracy']=.5
    data[-1]['no_vocals']['summary']['metrics']['root']['accuracy']=.8
    assert not decision(data)['passed']


def test_missing_sources_coverage_or_boundaries_fail_closed():
    assert not decision(rows()[:-1])['passed']
    data=rows(); data[0]['no_vocals']['summary']['metrics']['root']['scored_seconds']=39.
    assert not decision(data)['passed']
    data=rows();data[0]['no_vocals']['boundaries']['recall']=None
    assert not decision(data)['passed']


def test_missed_chords_and_nonfinite_scores_are_not_averageable():
    data=rows();data[0]['no_vocals']['summary']['category_seconds']['missed_chord']=.251
    assert not decision(data)['passed']
    data=rows();data[0]['no_vocals']['summary']['metrics']['root']['accuracy']=float('nan')
    assert not decision(data)['passed']
