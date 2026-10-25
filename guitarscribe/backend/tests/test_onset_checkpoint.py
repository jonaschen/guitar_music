from scripts.evaluate_onset_candidate import gate


def test_matched_short_note_with_wrong_duration_does_not_pass_checkpoint():
    reference=[dict(start=1,end=1.075,midi=60)]
    result=gate(reference,[dict(start=.975,end=1.1,midi=60)])
    assert result['metrics']['matched']==1
    assert result['metrics']['offset_within_100ms']==1
    assert not result['passed']
    assert '75ms_note_duration_outside_50_to_100ms' in result['failure_reasons']


def test_merging_repeated_notes_cannot_pass_despite_same_pitch_coverage():
    reference=[dict(start=0,end=.5,midi=60),dict(start=.5,end=1,midi=60)]
    result=gate(reference,[dict(start=0,end=1,midi=60)])
    assert not result['passed']
    assert result['metrics']['missing']==1
    assert 'offset_error_over_50ms' in result['failure_reasons']
