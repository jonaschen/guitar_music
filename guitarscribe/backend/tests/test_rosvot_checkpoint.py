import pytest
from scripts.evaluate_rosvot_checkpoint import decode_events


def test_rest_advances_timeline_and_touching_repetitions_stay_separate():
    notes,rests,end=decode_events({'pitches':[0,60,60,0,62], 'note_durs':[.5,.25,.25,.5,.125]})
    assert notes==[dict(start=.5,end=.75,midi=60),dict(start=.75,end=1.,midi=60),dict(start=1.5,end=1.625,midi=62)]
    assert rests==[dict(start=0,end=.5,midi=0),dict(start=1,end=1.5,midi=0)]
    assert end==1.625


def test_parser_does_not_extend_or_delete_short_predicted_events():
    notes,rests,end=decode_events({'pitches':[65], 'note_durs':[.005]})
    assert notes==[dict(start=0,end=.005,midi=65)]
    assert rests==[] and end==.005


@pytest.mark.parametrize('raw',[
    {'pitches':[60], 'note_durs':[]},
    {'pitches':[60], 'note_durs':[0]},
    {'pitches':[60], 'note_durs':[float('nan')]},
    {'pitches':[60.5], 'note_durs':[.2]},
])
def test_invalid_events_fail_without_repair(raw):
    with pytest.raises(ValueError):decode_events(raw)
