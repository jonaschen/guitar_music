import numpy as np
from scripts.check_independent_bass import qualify,assess,alignment


def row(ref,est,category,correct):
    return dict(start=0.,end=1.,reference_label=ref,estimate_label=est,category=category,root_correct=correct)


def test_stability_requires_neighbors_and_confidence_without_padding():
    f=np.ones(5)*55;v=np.ones(5,dtype=bool);p=np.ones(5);r=np.ones(5)
    pc,stable=qualify(f,v,p,r)
    assert pc.tolist()==[9]*5 and stable.tolist()==[False,True,True,True,False]
    p[2]=.89
    assert not qualify(f,v,p,r)[1].any()


def test_trigger_does_not_use_reference_and_nonchord_bass_counts_as_false_positive():
    times=np.arange(11)*.1;pc=np.ones(11,dtype=int)*9;stable=np.ones(11,dtype=bool)
    good,_=assess([row('A:maj7','C#:min','wrong_root',False)],times,pc,stable,1.)
    bad,_=assess([row('C#:min','C#:min','exact_match',True)],times,pc,stable,1.)
    assert abs(good['totals']['flag']-bad['totals']['flag'])<1e-9
    assert good['totals']['true_positive']>.99
    assert bad['totals']['true_positive']==0 and bad['totals']['false_positive']>.99
    assert bad['totals']['flag_nonchord_bass']>.99


def test_legal_inversion_is_not_forced_to_bass_root():
    times=np.arange(11)*.1;pc=np.ones(11,dtype=int)*4;stable=np.ones(11,dtype=bool)
    result,_=assess([row('C:maj/3','C:maj/3','exact_match',True)],times,pc,stable,1.)
    assert result['totals']['stable']>.99 and result['totals']['flag']==0


def test_abstention_stays_in_recall_and_coverage_denominators():
    times=np.arange(11)*.1;pc=np.ones(11,dtype=int)*9;stable=np.zeros(11,dtype=bool)
    d,_=assess([row('A:maj7','C#:min','wrong_root',False)],times,pc,stable,1.)
    assert d['metrics']['recall_all_wrong_root']==0
    assert d['outcome']=='insufficient_pitch_evidence'


def test_inadequate_alignment_coverage_fails_without_fitting_offset():
    result=alignment(np.zeros(4000),np.zeros(4000),(35,180))
    assert not result['passed'] and result['reason']=='length_or_coverage'


def test_triangular_prior_matches_valid_librosa_and_truncates_wide_prior():
    from scripts.check_independent_bass import truncated_triangular_transition
    import librosa
    from scipy.signal import get_window
    for n,width in [(5,3),(8,5),(361,361)]:
        expected=librosa.sequence.transition_local(n,width,window='triangle',wrap=False)
        np.testing.assert_allclose(truncated_triangular_transition(n,width),expected,atol=1e-15)
    actual=truncated_triangular_transition(361,431)
    np.testing.assert_allclose(actual.sum(axis=1),1.,atol=1e-15)
    window=get_window('triangle',431,fftbins=False)
    np.testing.assert_allclose(actual[0,:216],window[215:]/window[215:].sum())
    assert actual[0,216:].sum()==0 and actual[-1,:145].sum()==0


def test_pyin_fixed_prior_compatibility_produces_a_synthetic_track():
    import librosa
    from scripts.check_independent_bass import truncated_triangular_transition
    original=librosa.sequence.transition_local
    def fixed(n_states,width,*,window='triangle',wrap=False):
        if n_states==361 and width==431 and window=='triangle' and not wrap:
            return truncated_triangular_transition(n_states,width)
        return original(n_states,width,window=window,wrap=wrap)
    librosa.sequence.transition_local=fixed
    try:
        wave=.2*np.sin(2*np.pi*55*np.arange(4000)/4000)
        f0,voiced,prob=librosa.pyin(wave,fmin=32.7031956626,fmax=261.625565301,sr=4000,frame_length=1024,hop_length=400,
            center=True,n_thresholds=100,beta_parameters=(2,18),boltzmann_parameter=2,resolution=.1,
            max_transition_rate=35.92,switch_prob=.01,no_trough_prob=.01,fill_na=np.nan)
        assert len(f0)==len(voiced)==len(prob)==11 and np.isfinite(f0).any()
        assert np.nanmedian(np.abs(f0-55))<.5
    finally:librosa.sequence.transition_local=original
