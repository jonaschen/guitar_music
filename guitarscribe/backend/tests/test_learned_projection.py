import pytest
from app.analyzers.beats.learned_projection import project_learned_beats


def test_pickup_preserves_actual_downbeats_and_input():
    beats=[i*.5 for i in range(10)];down=[1,3]
    result=project_learned_beats(beats,down,'test')
    assert [(b.beat,b.measure) for b in result.beats[:3]]==[(3,0),(4,0),(1,1)]
    assert [b.time for b in result.beats if b.beat==1]==down
    assert result.bpm==120 and result.downbeat_indices==[2,6]
    assert beats==[i*.5 for i in range(10)] and down==[1,3]


def test_three_four_meter():
    result=project_learned_beats([0,.5,1,1.5,2,2.5],[0,1.5],'test')
    assert result.time_signature=='3/4'
    assert [b.beat for b in result.beats]==[1,2,3,1,2,3]


def test_rejects_terminal_three_beat_bar_after_consistent_four_four():
    # Observed fold3 failure: a final downbeat after only three beats must
    # not be silently dropped to make an otherwise regular recording pass.
    beats = [i * 0.5 for i in range(64)]
    downbeats = [beats[i] for i in [*range(0, 61, 4), 63]]
    with pytest.raises(ValueError, match='Inconsistent meter'):
        project_learned_beats(beats, downbeats, 'test')


@pytest.mark.parametrize('beats,down',[
    ([0,.5,1,1.5,2,2.5,3,3.5,4],[0,4]),
    ([0,.5,1,1.5,2,2.5,3,3.5,4],[0,2]),
    ([0,.5,1,1.5,2],[0,2.1]),
    ([0,.5,.5,1],[0,1]),
    ([0,.5,float('nan'),2],[0,2]),
    ([0,.5,1,2],[2,0]),
    ([0,.5,1,2],[0]),
    ([False,.5,1,2],[0,2]),
])
def test_rejects_missing_inconsistent_or_invalid_observations(beats,down):
    with pytest.raises(ValueError):project_learned_beats(beats,down,'test')
