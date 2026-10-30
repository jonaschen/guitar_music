import pytest
from app.services.voicings import ChordVoicingProvider

TUNING = (40, 45, 50, 55, 59, 64)
# Pitch sets are musical expectations, independent of the shape search.
@pytest.mark.parametrize('symbol,bass,tones', [
    ('C/E',4,{0,4,7}), ('G/B',11,{7,11,2}), ('D7/F#',6,{2,6,9,0}),
    ('F/G',7,{5,9,0,7}), ('C/G',7,{0,4,7}), ('G/D',2,{7,11,2}),
    ('F/C',0,{5,9,0}), ('F#/C#',1,{6,10,1}), ('C#/B',11,{1,5,8,11}),
    ('F#m7b5/E',4,{6,9,0,4}), ('Bb/D',2,{10,2,5}), ('Db/F',5,{1,5,8}),
])
def test_slash_shapes_sound_complete_harmony_with_named_bass(symbol,bass,tones):
    shapes=ChordVoicingProvider().get(symbol)
    assert shapes and all('incomplete' not in v.tags for v in shapes)
    for shape in shapes:
        pitches=[p+f for p,f in zip(TUNING,shape.frets) if f is not None]
        assert len(pitches)>=4
        assert min(pitches)%12==bass
        assert {p%12 for p in pitches}==tones
        assert all(f is None or 0<=f<=15 for f in shape.frets)
        pressed=[f for f in shape.frets if f not in (None,0)]
        assert max(pressed)-min(pressed)<=3
        assert all(f is None or 1<=f<=4 for f in shape.fingers)


def test_capo_changes_sounding_pitch_without_mutating_cached_shapes():
    provider=ChordVoicingProvider()
    a=provider.get('C/E',capo=2)[0]
    assert min(p+f+2 for p,f in zip(TUNING,a.frets) if f is not None)%12==6
    a.frets[0]=15
    assert provider.get('C/E')[0].frets[0]!=15


def test_unknown_quality_and_fret_limits_do_not_claim_complete_voicing():
    provider=ChordVoicingProvider()
    assert all('incomplete' in v.tags for v in provider.get('Cunknown/E'))
    for shape in provider.get('C#/B',max_fret=1):
        assert max(f for f in shape.frets if f is not None)<=1
        assert 'incomplete' in shape.tags


@pytest.mark.parametrize('root',range(12))
@pytest.mark.parametrize('quality,intervals',[
    ('',(0,4,7)),('m',(0,3,7)),('7',(0,4,7,10)),('m7',(0,3,7,10)),
    ('maj7',(0,4,7,11)),('6',(0,4,7,9)),('m6',(0,3,7,9)),('m7b5',(0,3,6,10)),
])
def test_first_inversions_generalize_to_all_roots_and_supported_qualities(root,quality,intervals):
    names=('C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B')
    bass=(root+intervals[1])%12
    shapes=ChordVoicingProvider().get(names[root]+quality+'/'+names[bass])
    assert shapes and all('incomplete' not in v.tags for v in shapes)
    for shape in shapes:
        pitches=[p+f for p,f in zip(TUNING,shape.frets) if f is not None]
        assert min(pitches)%12==bass
        assert {p%12 for p in pitches}=={(root+n)%12 for n in intervals}
