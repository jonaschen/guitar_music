import pytest

from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import SongScore, SongInfo
from app.services.chord_timing_candidate import build_timing_candidate, restore_detected_timing, RECEIPT, WARNING
from app.services.revisions import RevisionStore


def source(boundary=2.04):
    s=SongScore(song=SongInfo(duration_seconds=6,source_start_seconds=18),
        beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(13)],
        chords=[ChordEvent(id='a',start=0,end=boundary,symbol='C'),ChordEvent(id='b',start=boundary,end=6,symbol='G')],
        melody=[MelodyNote(id='manual',start=.123,end=1.234,midi=64,note='E4',edited=True)])
    s.rhythm.display=['D',None,'D','U',None,'U','D','U'];s.rhythm.subdivision=8
    s.provenance.parameters['chord_input_source']='existing-accompaniment-stem-v1'
    return s


def test_late_downbeat_roundtrip_and_revision(tmp_path):
    s=source();before=s.model_dump_json()
    candidate,changes,_=build_timing_candidate(s,0,6)
    assert len(changes)==1 and candidate.chords[1].start==2
    assert candidate.melody==s.melody and candidate.beats==s.beats
    assert s.model_dump_json()==before
    assert restore_detected_timing(candidate)==s
    store=RevisionStore(tmp_path);identifier=store.save(candidate)
    assert restore_detected_timing(RevisionStore(tmp_path).load(identifier))==s
    candidate.melody[0].midi=65
    assert restore_detected_timing(candidate).melody[0].midi==65
    candidate.chords[1].symbol='Am'
    with pytest.raises(ValueError,match='changed'):restore_detected_timing(candidate)


def test_restore_preserves_preexisting_warning_order():
    s=source();s.analysis.warnings=[WARNING,'Existing other warning']
    candidate,_,_=build_timing_candidate(s,0,6)
    assert restore_detected_timing(candidate)==s


@pytest.mark.parametrize('boundary',[1.75,2.25,2.06,1.98,2.5,2.54])
def test_preserve_offbeats_large_lateness_anticipation_and_non_downbeats(boundary):
    s=source(boundary);candidate,changes,_=build_timing_candidate(s,0,6)
    assert not changes and candidate==s


@pytest.mark.parametrize('kind',['gap','short','manual','range','no_stroke','same_label'])
def test_protect_music_and_user_work(kind):
    s=source();start=0;end=6
    if kind=='gap':s.chords[0].end=2
    if kind=='short':s.chords[1].end=2.115
    if kind=='manual':s.chords[0].edited=True
    if kind=='range':start=2.02
    if kind=='no_stroke':s.rhythm.display[0]=None
    if kind=='same_label':s.chords[1].symbol='C'
    candidate,changes,_=build_timing_candidate(s,start,end)
    assert not changes and candidate==s


def test_faster_tempo_has_relative_limit_and_repeat_is_rejected():
    s=source(2.04)
    s.beats=[BeatInfo(time=i*.25,beat=i%4+1,measure=i//4+1) for i in range(25)]
    assert not build_timing_candidate(s,0,6)[1]  # 40ms > 1/8 of a 250ms beat.
    c,_,_=build_timing_candidate(source(),0,6)
    with pytest.raises(ValueError,match='Restore'):build_timing_candidate(c,0,6)
    c.provenance.parameters[RECEIPT]='bad json'
    with pytest.raises(ValueError,match='receipt'):restore_detected_timing(c)


@pytest.mark.parametrize('kind',['overlap','duplicate','beats','nan','wrong_source','range'])
def test_invalid_inputs(kind):
    s=source();start,end=0,6
    if kind=='overlap':s.chords[0].end=2.1
    if kind=='duplicate':s.chords[1].id='a'
    if kind=='beats':s.beats[1].time=0
    if kind=='nan':s.chords[0].end=float('nan')
    if kind=='wrong_source':s.provenance.parameters.clear()
    if kind=='range':end=7
    with pytest.raises(ValueError):build_timing_candidate(s,start,end)


@pytest.mark.asyncio
async def test_preview_requires_confirmed_range_and_restore_is_exact():
    from httpx import AsyncClient, ASGITransport
    from app.api import app
    score=source();body=dict(score=score.model_dump(mode='json'),start=0,end=6)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.post('/scores/chord-timing-candidate',json=body)).status_code==409
        body['downbeats_confirmed']=True
        response=await client.post('/scores/chord-timing-candidate',json=body)
        assert response.status_code==200,response.text
        packet=response.json()
        assert not packet['applied'] and not packet['saved'] and len(packet['changes'])==1
        restored=await client.post('/scores/chord-timing-restore',json=packet['score'])
        assert restored.status_code==200 and restored.json()==score.model_dump(mode='json')
        packet['score']['chords'][1]['edited']=True
        assert (await client.post('/scores/chord-timing-restore',json=packet['score'])).status_code==409
