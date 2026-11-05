import pytest
from app.evaluation.chord_decoder_trace import summarize


def trace():
    dictionary=[{'index':i,'label':label,'weights':[0]*24}for i,label in enumerate(('C','G','N'))]
    return {'dictionary':dictionary,'frames':[
        {'sec':0,'nsec':0,'emission':[.8,.1,.1],'salience':[1]*3,'local':0,'hmm':1,'ties':[0]},
        {'sec':1,'nsec':0,'emission':[.1,.8,.1],'salience':[1]*3,'local':1,'hmm':0,'ties':[1]},
        {'sec':4,'nsec':0,'emission':[.1,.8,.1],'salience':[1]*3,'local':1,'hmm':0,'ties':[1]}]}


def test_frame_durations_are_weighted_and_final_frame_not_invented():
    s=summarize(trace(),[{'start':0,'end':5,'reference_label':'C'}],0,5)
    assert s['four_way_seconds']['local_correct_hmm_wrong']==1
    assert s['four_way_seconds']['local_wrong_hmm_correct']==3
    assert s['uncovered_seconds']==1
    assert s['positive_margin_hmm_harm_seconds']==1


def test_absent_full_chord_is_excluded_even_when_root_exists():
    s=summarize(trace(),[{'start':0,'end':5,'reference_label':'C:7'}],0,5)
    assert s['eligible_seconds']==0
    assert s['no_strict_candidate_seconds']==4


def test_invalid_argmax_or_normalization_is_rejected():
    t=trace();t['frames'][0]['local']=1
    with pytest.raises(ValueError):summarize(t,[],0,5)
    t=trace();t['frames'][0]['emission']=[.8,.8,.8]
    with pytest.raises(ValueError):summarize(t,[],0,5)
