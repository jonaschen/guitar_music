import numpy as np

from scripts.diagnose_synthetic_transcription import match_notes, render


def test_one_long_prediction_cannot_explain_two_repeated_reference_notes():
    reference=[dict(start=0,end=.5,midi=60),dict(start=.5,end=1,midi=60)]
    result=match_notes(reference,[dict(start=0,end=1,midi=60)])
    assert result['matched']==1
    assert result['missing']==1
    assert result['offset_errors_seconds']==[.5]
    assert result['offset_within_100ms']==0


def test_matching_reports_extra_wrong_pitch_and_late_notes():
    result=match_notes([dict(start=0,end=1,midi=60)],
        [dict(start=0,end=1,midi=72),dict(start=.2,end=1,midi=60)])
    assert result['matched']==0 and result['missing']==1 and result['extra']==2


def test_legal_short_note_is_preserved_by_independent_renderer():
    note=dict(start=1,end=1.075,midi=60)
    first=render([note]); second=render([note])
    assert np.array_equal(first,second)
    assert np.max(np.abs(first))>.1
    assert np.count_nonzero(first[:22050])==0
    assert np.count_nonzero(first[round(1.075*22050):])==0
