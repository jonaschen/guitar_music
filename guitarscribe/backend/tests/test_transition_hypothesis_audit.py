import numpy as np

from scripts.audit_transition_hypotheses import analyze


def test_short_preference_flip_is_reported_but_not_sustained():
    times=np.arange(0,4,.01)
    # A 180ms excursion can pass the original 120ms crossing detector.
    # A real new state starts later and persists.
    new=((times>=1)&(times<1.18))|(times>=2.5)
    sim=np.stack([np.where(new,.2,.8),np.where(new,.8,.2)])
    row=analyze(sim,times,['G','C'],{'name':'test','from':'G','to':'C','search':[.8,2.8]})
    early=[s for s in row['sustained_support'] if s['time']<1.3]
    later=[s for s in row['sustained_support'] if s['time']>2.3]
    assert early and later
    assert all(s['new_post_fraction']<.75 for s in early)
    assert all(s['new_post_fraction']>.9 and s['old_pre_fraction']>.9 for s in later)


def test_no_transition_does_not_invent_a_boundary():
    times=np.arange(0,4,.01)
    sim=np.stack([np.full(times.shape,.8),np.full(times.shape,.2)])
    row=analyze(sim,times,['G','C'],{'name':'test','from':'G','to':'C','search':[1,3]})
    assert row['crossings']==[] and row['sustained_support']==[]
