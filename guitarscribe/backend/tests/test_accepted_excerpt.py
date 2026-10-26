import pytest

from app.models.analysis import MelodyNote
from app.models.score import SongScore,SongInfo
from app.services.accepted_excerpt import compose_excerpt


def sources():
    melody=SongScore(song=SongInfo(duration_seconds=12,source_start_seconds=18),
        melody=[MelodyNote(id=str(i),start=a,end=b,midi=60+i,note='C4',edited=True)
                for i,(a,b) in enumerate([(0,1),(1,3),(4,5),(6,9),(10,11)])])
    melody.provenance.parameters['melody_note_processing']='bounded-source-v1'
    return melody,SongScore(song=SongInfo(duration_seconds=5))


def test_clips_only_edges_preserves_pitches_and_does_not_mutate():
    m,a=sources();before=(m.model_dump_json(),a.model_dump_json())
    result=compose_excerpt(m,a,2)
    assert [(n.id,n.start,n.end,n.midi,n.edited) for n in result.melody]==[('1',0,1,61,True),('2',2,3,62,True),('3',4,5,63,True)]
    assert result.song.source_start_seconds==20
    assert result.provenance.parameters['melody_note_processing']=='bounded-source-v1'
    assert before==(m.model_dump_json(),a.model_dump_json())


@pytest.mark.parametrize('case',['negative','past_end','nan','key','guitar','capo','existing_melody'])
def test_rejects_incompatible_or_ambiguous_inputs(case):
    m,a=sources();start=2
    if case=='negative':start=-1
    if case=='past_end':start=9
    if case=='nan':start=float('nan')
    if case=='key':a.key_context.transpose_semitones=1
    if case=='guitar':a.guitar.tuning[0]=38
    if case=='capo':a.analysis.capo=1
    if case=='existing_melody':a.melody=m.melody[:1]
    with pytest.raises(ValueError):compose_excerpt(m,a,start)
