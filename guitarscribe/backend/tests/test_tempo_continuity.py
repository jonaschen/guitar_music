import pytest
from app.analyzers.beats.tempo_continuity import tempo_reference


def sequence(periods):
    values=[0.]
    for p in periods:values.append(values[-1]+p)
    return values


def test_stable_tempo_reference_preserves_slow_drift():
    r=tempo_reference(sequence([.5,.51,.49,.5]*20))
    assert r['eligible'] and r['support_fraction']==pytest.approx(1)
    assert r['period_seconds']==pytest.approx(.5)
    assert r['min_bpm']==pytest.approx(60/(.5*1.15))


def test_duration_weighting_does_not_let_short_double_density_segment_outvote_duration():
    r=tempo_reference(sequence([1.]*100+[.5]*50))
    assert r['eligible'] and r['period_seconds']==1
    assert r['support_fraction']==.8


def test_equal_time_at_two_tempos_is_not_forced_into_one():
    r=tempo_reference(sequence([1.]*40+[.5]*80))
    assert not r['eligible'] and r['reason']=='no_dominant_tempo'


@pytest.mark.parametrize('beats',[[0,1],[0]*18,[float('nan')]*18,[-1]+list(range(20))])
def test_bad_or_short_input_is_rejected(beats):
    assert not tempo_reference(beats)['eligible']
