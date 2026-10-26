import io

import mido
import pytest

from app.exporters.midi import compile_playback_manifest, export_manifest_midi
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import SongScore, SongInfo
from app.services.chord_entry_performance import build_entry_performance


def source():
    score = SongScore(song=SongInfo(duration_seconds=6),
        beats=[BeatInfo(time=i*.5, beat=i%4+1, measure=i//4+1) for i in range(13)],
        chords=[ChordEvent(id='a',start=0,end=2.08,symbol='C'),ChordEvent(id='b',start=2.08,end=6,symbol='G')],
        melody=[MelodyNote(id='manual',start=.123,end=1.234,midi=64,note='E4',edited=True)])
    score.rhythm.display=['D',None,'D','U',None,'U','D','U']
    score.rhythm.subdivision=8
    return score


@pytest.mark.parametrize('mode',['sparse','continuous'])
def test_opt_in_entries_and_original_restore(mode):
    score=source();before=score.model_dump_json()
    original,candidate,changes,skipped=build_entry_performance(score,mode)
    assert not skipped and len(changes)==2
    assert score.model_dump_json()==before
    assert compile_playback_manifest(score)==original
    assert candidate.revision!=original.revision
    assert build_entry_performance(score,mode)[1]==candidate
    assert [e for e in candidate.events if e.track!='guitar']==[e for e in original.events if e.track!='guitar']
    for chord in score.chords:
        actual=[e for e in candidate.events if e.track=='guitar' and e.source_id==chord.id]
        previous=[e for e in original.events if e.track=='guitar' and e.source_id==chord.id]
        assert actual[0].start==chord.start
        assert all(e.sustain_end==chord.end for e in actual)
        if mode=='continuous':
            assert len(actual)==len(previous)
            assert [e.start for e in actual[1:]]==[e.start for e in previous[1:]]
        else:assert len(actual)==1
        for event in actual:assert event.start+max(event.pitch_offsets)<event.end


@pytest.mark.parametrize('case',['manual','short','empty_pattern','no_beats','merged'])
def test_preserve_unsupported_spans(case):
    score=source()
    if case=='manual':score.chords[1].edited=True
    if case=='short':score.chords[1].end=2.2
    if case=='empty_pattern':score.rhythm.display=[]
    if case=='no_beats':score.beats=[]
    if case=='merged':score.chords[1].symbol='C'
    original,candidate,_,skipped=build_entry_performance(score,'continuous')
    assert any(s['chord_id']=='b' for s in skipped)
    assert [e for e in candidate.events if e.source_id=='b' and e.track=='guitar']==[e for e in original.events if e.source_id=='b' and e.track=='guitar']


@pytest.mark.parametrize('case',['overlap','duplicate','nan','beats'])
def test_reject_invalid_score(case):
    score=source()
    if case=='overlap':score.chords[1].start=1
    if case=='duplicate':score.chords[1].id='a'
    if case=='nan':score.chords[1].end=float('nan')
    if case=='beats':score.beats[1].time=0
    with pytest.raises(ValueError):build_entry_performance(score,'continuous')


def test_string_crossing_boundary_preserves_original_span():
    score=source();score.chords[0].end=score.chords[1].start=2.04
    original,candidate,_,skipped=build_entry_performance(score,'continuous')
    assert dict(chord_id='a',reason='insufficient_room_for_strings') in skipped
    assert [e for e in original.events if e.source_id=='a' and e.track=='guitar']==[e for e in candidate.events if e.source_id=='a' and e.track=='guitar']


def test_midi_note_on_and_off_follow_manifest():
    manifest=build_entry_performance(source(),'continuous')[1]
    actual=[];time=0
    for msg in mido.MidiFile(file=io.BytesIO(export_manifest_midi(manifest))):
        time+=msg.time
        if msg.type in {'note_on','note_off'}:
            actual.append((msg.channel,msg.note,msg.type,time))
    expected=[]
    for event in manifest.events:
        if event.track=='metronome':continue
        channel=1 if event.track=='guitar' else 0
        for i,pitch in enumerate(event.pitches):
            offset=event.pitch_offsets[i] if event.pitch_offsets else 0
            expected.extend([(channel,pitch,'note_on',event.start+offset),(channel,pitch,'note_off',event.end)])
    assert len(actual)==len(expected)
    for a,b in zip(sorted(actual),sorted(expected)):
        assert a[:3]==b[:3] and abs(a[3]-b[3])<.002


@pytest.mark.asyncio
async def test_api_explicit_mode_and_same_midi_revision():
    from httpx import AsyncClient,ASGITransport
    from app.api import app
    body={'score':source().model_dump(mode='json')}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.post('/scores/chord-entry-performance',json=body)).status_code==422
        body['mode']='continuous'
        response=await client.post('/scores/chord-entry-performance',json=body)
        assert response.status_code==200,response.text
        data=response.json();assert not data['saved'] and not data['applied']
        expected=build_entry_performance(source(),'continuous')[1]
        assert data['candidate']['revision']==expected.revision
        body['output']='midi'
        midi=await client.post('/scores/chord-entry-performance',json=body)
        assert midi.status_code==200
        assert midi.headers['X-Playback-Revision']==expected.revision
        assert midi.content==export_manifest_midi(expected)
