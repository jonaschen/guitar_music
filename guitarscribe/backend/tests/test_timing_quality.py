from app.evaluation.timing_quality import timing_quality


def test_missing_downbeat_and_density_switch_are_distinct_failures():
    beats=[i*.5 for i in range(81)];downs=beats[::4]
    assert timing_quality(beats,downs,41)['engineering_pass']
    assert 'inconsistent_bars' in timing_quality(beats,downs[:4]+downs[5:],41)['issues']
    beats += [40+i*.25 for i in range(1,81)]
    downs += [40+i for i in range(1,21)]
    report=timing_quality(beats,downs,61)
    assert 'inconsistent_bars' not in report['issues']
    assert 'adjacent_density_switch' in report['issues']
    assert 'window_density_switch' in report['issues']
    assert not report['musical_accuracy_evaluated']


def test_audio_edge_cannot_pass_engineering_gate():
    report=timing_quality([i*.5 for i in range(17)],[0,2,4,6,8],8)
    assert 'outside_audio' in report['issues']
