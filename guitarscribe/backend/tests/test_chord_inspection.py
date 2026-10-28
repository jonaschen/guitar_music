import pytest
from app.models.analysis import ChordEvent
from app.services.chord_inspection import chord_inspection_events


def test_unmetered_inspection_keeps_detection_times_gaps_and_short_chords():
    chords=[ChordEvent(id='a',start=.137,end=.147,symbol='C'),
            ChordEvent(id='b',start=1.231,end=5,symbol='G')]
    before=[c.model_dump() for c in chords]
    events,unsupported=chord_inspection_events(chords,5)
    assert not unsupported
    assert [(e.start,e.end) for e in events]==[(.137,.147),(1.231,5)]
    assert all(e.track=='guitar' and e.start+max(e.pitch_offsets)<e.end for e in events)
    assert [c.model_dump() for c in chords]==before


def test_unsupported_harmony_is_reported_and_never_substituted():
    events,unsupported=chord_inspection_events([ChordEvent(id='x',start=0,end=1,symbol='UNKNOWN')],1)
    assert events==[] and unsupported==['x']


@pytest.mark.parametrize('spans', [[(0,2)],[(1,2),(.5,1)],[(0,.8),(.7,1)],[(0,float('nan'))]])
def test_invalid_spans_are_rejected(spans):
    chords=[ChordEvent(id=str(i),start=a,end=b,symbol='C') for i,(a,b) in enumerate(spans)]
    with pytest.raises(ValueError):chord_inspection_events(chords,1)
