import pytest
from app.models.score import SongScore,SongInfo
from app.models.analysis import BeatInfo,ChordEvent,MelodyNote
from app.services.chord_grid_candidate import build_chord_grid_candidate

def source():
    s=SongScore(song=SongInfo(duration_seconds=4),beats=[BeatInfo(time=t,beat=i%4+1,measure=i//4+1) for i,t in enumerate([0,.5,1,1.5,2,2.6,3,3.5,4])],
        chords=[ChordEvent(id='a',start=0,end=2.019,symbol='Am'),ChordEvent(id='b',start=2.019,end=4,symbol='Em')],
        melody=[MelodyNote(id='n',start=.13,end=.31,midi=60,note='C4')])
    return s

def test_shared_edges_and_melody_preserved_without_mutating_source():
    s=source();before=s.model_dump_json();c,r=build_chord_grid_candidate(s)
    assert c.chords[0].end==c.chords[1].start==2
    assert c.melody==s.melody and c.beats==s.beats
    assert s.model_dump_json()==before and len(r['changes'])==2

def test_half_beat_change_and_uneven_tempo_use_local_grid():
    s=source();s.chords[0].end=s.chords[1].start=2.29
    c,_=build_chord_grid_candidate(s);assert c.chords[1].start==2.3

def test_short_chord_is_not_deleted_or_collapsed():
    s=source();s.chords=[ChordEvent(id='a',start=0,end=1.01,symbol='C'),ChordEvent(id='b',start=1.01,end=1.03,symbol='G'),ChordEvent(id='c',start=1.03,end=4,symbol='F')]
    c,r=build_chord_grid_candidate(s);assert c.chords==s.chords
    assert r['unquantized_edges']==[1.01,1.03]

def test_real_gap_and_manual_boundaries_are_not_erased():
    s=source();s.chords[0].end=2.01;s.chords[1].start=2.03
    c,_=build_chord_grid_candidate(s);assert c.chords==s.chords
    s=source();s.chords[0].edited=True
    c,_=build_chord_grid_candidate(s);assert c.chords==s.chords

def test_intro_and_outro_rests_survive_quantization():
    s=source();s.chords[0].start=.01;s.chords[-1].end=3.99
    c,_=build_chord_grid_candidate(s)
    assert c.chords[0].start==.01 and c.chords[-1].end==3.99

@pytest.mark.parametrize('case',['nan','overlap','beats'])
def test_invalid_inputs(case):
    s=source()
    if case=='nan':s.chords[0].end=float('nan')
    if case=='overlap':s.chords[1].start=1
    if case=='beats':s.beats[1].time=0
    with pytest.raises(ValueError):build_chord_grid_candidate(s)
