import pytest
from app.models.score import SongScore, SongInfo
from app.models.analysis import BeatInfo, ChordEvent, ChordVoicing
from app.services.performance_draft import build_performance_draft
from app.exporters.midi import compile_playback_manifest, export_midi
from app.services.revisions import RevisionStore


def source():
    score=SongScore(song=SongInfo(duration_seconds=4),beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(9)],
        chords=[ChordEvent(id='c',symbol='C/E',start=0,end=2.019),ChordEvent(id='g',symbol='G/B',start=2.019,end=4)])
    for c in score.chords:
        v=ChordVoicing(id='root-note-'+c.symbol,symbol=c.symbol,shape_symbol=c.symbol,frets=[0,None,None,None,None,None],tags=['incomplete','root-note'])
        c.available_voicings=[v];c.voicing_id=v.id
    return score


def test_shared_boundary_complete_playback_and_saved_reload_preserve_original(tmp_path):
    score=source();before=score.model_dump_json();candidate,report=build_performance_draft(score)
    assert candidate.chords[0].end==candidate.chords[1].start==2
    assert [(c.id,c.symbol) for c in candidate.chords]==[(c.id,c.symbol) for c in score.chords]
    assert candidate.beats==score.beats and candidate.melody==score.melody
    assert report['repaired_voicings']==['c','g']
    assert not report['unresolved_voicings']
    manifest=compile_playback_manifest(candidate)
    assert all(len(e.pitches)>=4 for e in manifest.events if e.track=='guitar')
    store=RevisionStore(tmp_path);original=store.save(score);revision=store.fork(original,candidate)
    assert store.load(original).model_dump_json()==before
    assert compile_playback_manifest(store.load(revision))==manifest
    assert export_midi(store.load(revision))==export_midi(candidate)
    assert score.model_dump_json()==before


def test_unmetered_repairs_sound_without_inventing_beats_or_strokes():
    score=source();score.analysis.timing_status='unmetered';score.analysis.bpm=0;score.analysis.time_signature='';score.beats=[]
    candidate,report=build_performance_draft(score)
    assert [(c.start,c.end) for c in candidate.chords]==[(c.start,c.end) for c in score.chords]
    assert candidate.beats==[] and candidate.analysis.bpm==0 and not report['grid_applied']
    events=compile_playback_manifest(candidate).events
    assert len(events)==2 and all(len(e.pitches)>=4 for e in events)


def test_manual_voicing_and_shared_timing_are_preserved():
    score=source();score.chords[0].edited=True
    candidate,report=build_performance_draft(score)
    assert candidate.chords[0]==score.chords[0]
    assert candidate.chords[1].start==2.019
    assert report['protected_manual_voicings']==['c']
    assert report['unresolved_voicings']==['c']


def test_repeated_preparation_does_not_change_musical_events():
    candidate,_=build_performance_draft(source());again,report=build_performance_draft(candidate)
    assert again.chords==candidate.chords and again.beats==candidate.beats
    assert not report['grid_applied'] and report['repaired_voicings']==[]


def test_custom_tuning_is_not_replaced_with_standard_tuning_shapes():
    score=source();score.guitar.tuning=[38,45,50,55,59,64]
    candidate,report=build_performance_draft(score)
    assert report['repaired_voicings']==[] and report['unresolved_voicings']==['c','g']
    assert candidate.chords[0].available_voicings==score.chords[0].available_voicings


@pytest.mark.asyncio
async def test_endpoint_returns_unsaved_reversible_candidate():
    from httpx import AsyncClient,ASGITransport
    from app.api import app
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/scores/performance-draft',json=source().model_dump(mode='json'))
    assert response.status_code==200
    result=response.json();assert not result['saved'] and not result['applied']
    assert result['score']['chords'][0]['end']==2
    assert result['report']['repaired_voicings']==['c','g']
