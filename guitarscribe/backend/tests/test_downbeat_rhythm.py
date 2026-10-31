import math
import pytest
from app.models.score import SongScore, SongInfo
from app.models.analysis import BeatInfo, ChordEvent, RhythmSuggestion
from app.services.downbeat_rhythm import PATTERN_ID, downbeat_events
from app.exporters.midi import compile_playback_manifest, export_midi
from app.services.revisions import RevisionStore


def source():
    return SongScore(song=SongInfo(duration_seconds=8),
        beats=[BeatInfo(time=i*.5, beat=i%4+1, measure=i//4+1) for i in range(16)],
        chords=[ChordEvent(id='c', symbol='C', start=0, end=8)],
        rhythm=RhythmSuggestion(pattern_id=PATTERN_ID, subdivision=4, display=['D', None, None, None]))


def test_held_chord_repeats_every_bar_and_saves_identically(tmp_path):
    score=source(); before=score.model_dump_json()
    events=downbeat_events(score)
    assert [e.start for e in events] == [0, 2, 4, 6]
    assert [e.end for e in events] == [2, 4, 6, 8]
    assert all(len(e.pitches) >= 4 for e in events)
    manifest=compile_playback_manifest(score)
    assert [e for e in manifest.events if e.track=='guitar'] == events
    store=RevisionStore(tmp_path); revision=store.save(score)
    assert compile_playback_manifest(store.load(revision)) == manifest
    assert export_midi(store.load(revision)) == export_midi(score)
    assert score.model_dump_json() == before


def test_offbeat_changes_do_not_attack_or_mute_and_exact_boundary_uses_new_chord():
    score=source()
    score.chords=[ChordEvent(id='c',symbol='C',start=0,end=.75),
        ChordEvent(id='g',symbol='G',start=.75,end=4),ChordEvent(id='am',symbol='Am',start=4,end=8)]
    events=downbeat_events(score)
    assert [(e.start,e.source_id,e.end) for e in events] == [(0,'c',2),(2,'g',4),(4,'am',6),(6,'am',8)]
    assert events[0].pitches != events[1].pitches != events[2].pitches


@pytest.mark.parametrize('rest', [True, False])
def test_rests_and_gaps_cut_resonance_without_extra_attacks(rest):
    score=source();score.chords=[ChordEvent(id='c',symbol='C',start=0,end=1)]
    if rest: score.chords.append(ChordEvent(id='nc',symbol='N.C.',start=1,end=3))
    score.chords.append(ChordEvent(id='g',symbol='G',start=3,end=8))
    assert [(e.start,e.end) for e in downbeat_events(score)] == [(0,1),(4,6),(6,8)]


def test_pickup_variable_tempo_and_unobserved_tail_never_extrapolate():
    score=source();score.beats=[BeatInfo(time=.1,beat=4,measure=0)]+[
        BeatInfo(time=t,beat=i%4+1,measure=i//4+1) for i,t in enumerate([.6,1.2,1.8,2.5,3.2,4,4.9,5.9])]
    assert [e.start for e in downbeat_events(score)] == [.6,3.2]
    assert downbeat_events(score)[-1].end == 8


def test_three_four_and_short_tail():
    score=source();score.analysis.time_signature='3/4'
    score.beats=[BeatInfo(time=i*.5,beat=i%3+1,measure=i//3+1) for i in range(17)]
    assert [e.start for e in downbeat_events(score)] == [0,1.5,3,4.5,6,7.5]
    assert downbeat_events(score)[-1].end == 8


@pytest.mark.parametrize('bad', ['unmetered','empty','nan','duplicate','number','measure','overlap','duplicate_id'])
def test_reject_ambiguous_inputs(bad):
    score=source()
    if bad=='unmetered': score.analysis.timing_status='unmetered'
    elif bad=='empty': score.beats=[]
    elif bad=='nan': score.beats[1].time=math.nan
    elif bad=='duplicate': score.beats[1].time=0
    elif bad=='number': score.beats[1].beat=4
    elif bad=='measure': score.beats[4].measure=1
    elif bad=='overlap': score.chords.append(ChordEvent(id='g',symbol='G',start=4,end=8))
    elif bad=='duplicate_id': score.chords=[ChordEvent(id='c',symbol='C',start=0,end=4),ChordEvent(id='c',symbol='G',start=4,end=8)]
    with pytest.raises(ValueError): downbeat_events(score)


@pytest.mark.asyncio
async def test_api_compiles_bar_rhythm_and_rejects_broken_grid():
    from httpx import AsyncClient, ASGITransport
    from app.api import app
    score=source()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/scores/playback/manifest',json=score.model_dump(mode='json'))
        assert response.status_code == 200
        assert [e['start'] for e in response.json()['events'] if e['track']=='guitar'] == [0,2,4,6]
        score.beats[1].beat=4
        for endpoint in ('/scores/playback/manifest','/scores/midi'):
            response=await client.post(endpoint,json=score.model_dump(mode='json'))
            assert response.status_code == 422
        score.analysis.timing_status='unmetered';score.analysis.bpm=0;score.analysis.time_signature='';score.beats=[]
        response=await client.post('/scores/playback/manifest',json=score.model_dump(mode='json'))
        assert response.status_code == 422
