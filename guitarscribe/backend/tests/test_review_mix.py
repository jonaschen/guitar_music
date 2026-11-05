import numpy as np
import pytest
from app.evaluation.review_mix import focus_mix


def test_focus_changes_balance_not_auxiliary_onsets_or_ab_gain():
    source=np.array([.1,.2,-.2,.1,0]);a=source+np.array([0,.3,0,0,0]);b=source+np.array([0,0,0,.2,0])
    result,gain=focus_mix(source,a,b)
    assert gain==1
    np.testing.assert_allclose(result['a-focus']-result['source-focus'],result['a-solo'])
    np.testing.assert_allclose(result['b-focus']-result['source-focus'],result['b-solo'])
    assert np.flatnonzero(result['a-solo']).tolist()==[1]
    assert np.flatnonzero(result['b-solo']).tolist()==[3]
    assert source[1]==.2


def test_common_headroom_handles_cancellation_without_independent_normalization():
    source=np.array([.9,-.9]);a=-source;b=np.zeros(2)
    result,gain=focus_mix(source,a,b)
    assert gain<1 and max(np.max(np.abs(x)) for x in result.values())<=.95+1e-12
    np.testing.assert_allclose(result['a-solo'],2*result['b-solo'])


@pytest.mark.parametrize('bad',[np.array([]),np.array([1]),np.array([np.nan,0]),np.zeros((2,2))])
def test_invalid_or_unaligned_audio_is_rejected(bad):
    with pytest.raises(ValueError):focus_mix(np.zeros(2),bad,np.zeros(2))
