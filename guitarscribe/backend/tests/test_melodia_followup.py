import pytest
from app.evaluation.melodia_followup import compare_frames


def test_half_open_split_separates_new_notes_from_tail_regression():
    baseline=[None,440,440,660]
    candidate=[440,None,880,660]
    assert compare_frames(baseline,candidate,0,2,offset=0,hop=1)==dict(
        frames=2,baseline_voiced=1,candidate_voiced=1,added=1,dropped=1,changed_over_half_semitone=0)
    assert compare_frames(baseline,candidate,2,4,offset=0,hop=1)==dict(
        frames=2,baseline_voiced=2,candidate_voiced=2,added=0,dropped=0,changed_over_half_semitone=1)
    with pytest.raises(ValueError,match="counts"):
        compare_frames(baseline,[],0,4)
