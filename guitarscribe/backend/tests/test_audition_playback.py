import pytest
from app.models.score import SongScore,SongInfo,AnalysisSummary
from app.models.analysis import BeatInfo,ChordEvent
from app.services.audition_playback import audition_manifest,root_pitch
from app.exporters.midi import compile_playback_manifest
from app.services.transposition import TranspositionService


def score():
    return SongScore(song=SongInfo(duration_seconds=4),beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(8)],
        chords=[ChordEvent(id='c',symbol='C/E',start=0,end=.75),ChordEvent(id='g',symbol='G',start=.75,end=4)])


def guitar(s,*args):return [e for e in audition_manifest(s,*args).events if e.track=='guitar']


def test_default_manifest_and_score_unchanged():
    s=score();before=s.model_dump_json();original=compile_playback_manifest(s)
    assert audition_manifest(s)==original
    for mode in ('bar','two','one','half'):guitar(s,'root',mode)
    assert s.model_dump_json()==before and compile_playback_manifest(s)==original


@pytest.mark.parametrize('pulse,starts',[('bar',[0,2]),('two',[0,1,2,3]),('one',[i*.5 for i in range(8)]),('half',[i*.25 for i in range(15)])])
def test_frequency_uses_observed_beats_not_chord_changes(pulse,starts):
    events=guitar(score(),'root',pulse)
    assert [e.start for e in events]==starts
    assert all(e.start!=.75 for e in events) if pulse!='half' else True
    assert events[0].pitches==(48,) and all(len(e.pitches)==1 for e in events)
    assert next(e for e in events if e.start>=1).pitches==(43,)


def test_variable_beats_midpoints_and_no_tail_extrapolation():
    s=score();times=[0,.4,1,1.45,2.1,2.6,3.2,3.7]
    for b,t in zip(s.beats,times):b.time=t
    starts=[e.start for e in guitar(s,'root','half')]
    assert .2 in starts and .7 in starts and 3.85 not in starts
    assert starts[-1]==3.7


def test_root_uses_sounding_symbol_and_ignores_slash_and_capo():
    s=score();s.analysis.capo=4
    assert guitar(s,'root','one')[0].pitches==(48,)
    moved=TranspositionService().transpose_score(s,2,capo=3)
    assert guitar(moved,'root','one')[0].pitches[0]%12==2
    assert root_pitch('Bb/D')%12==10 and root_pitch('F#:min/b3')%12==6


def test_local_preview_only_known_sections_with_unknown_silent():
    s=score();s.analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='');s.beats=[]
    preview=dict(duration_seconds=4,source_start_seconds=0,regions=[dict(start=1,end=3,beats_per_bar=4,bars=[dict(start=1,end=3,beats=[1,1.4,2,2.5,3])])])
    events=guitar(s,'root','half',preview)
    assert [e.start for e in events]==[1,1.2,1.4,1.7,2,2.25,2.5,2.75]
    assert all(1<=e.start<e.end<=3 for e in events)
    with pytest.raises(ValueError):guitar(s,'root','one')
    preview['source_start_seconds']=1
    with pytest.raises(ValueError):guitar(s,'root','one',preview)


def test_rests_cut_ringing_and_skip_attacks():
    s=score();s.chords=[ChordEvent(id='c',symbol='C',start=0,end=.7),ChordEvent(id='n',symbol='N',start=.7,end=1.3),ChordEvent(id='g',symbol='G',start=1.3,end=4)]
    events=guitar(s,'root','one')
    assert events[1].end==.7 and not any(.7<=e.start<1.3 for e in events)


@pytest.mark.asyncio
async def test_api_rejects_missing_preview_and_invalid_options():
    from httpx import AsyncClient,ASGITransport
    from app.api import app
    s=score()
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
        r=await c.post('/scores/audition-playback?content=root&pulse=two',json=s.model_dump(mode='json'))
        assert r.status_code==200 and len([e for e in r.json()['events'] if e['track']=='guitar'])==4
        s.analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='');s.beats=[]
        r=await c.post('/scores/audition-playback?pulse=one',json=s.model_dump(mode='json'));assert r.status_code==422
        r=await c.post('/scores/audition-playback?pulse=guess',json=s.model_dump(mode='json'));assert r.status_code==422


def test_two_beat_spacing_crosses_three_four_bars_and_respects_pickup():
    s=score();s.analysis.time_signature='3/4'
    for i,b in enumerate(s.beats):b.beat=i%3+1;b.measure=i//3+1
    assert [e.start for e in guitar(s,'root','two')]==[0,1,2,3]
    s=score()
    for i,b in enumerate(s.beats):b.beat=(i+3)%4+1;b.measure=(i+3)//4+1
    assert [e.start for e in guitar(s,'root','two')]==[.5,1.5,2.5,3.5]


@pytest.mark.asyncio
async def test_api_rejects_another_songs_preview_even_if_duration_matches():
    from httpx import AsyncClient,ASGITransport
    from app.api import app
    s=score();s.analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='');s.beats=[]
    s.provenance.parameters['analysis_source_job_id']='song-a'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
        r=await c.post('/scores/audition-playback?pulse=one&source_job=song-b',json=s.model_dump(mode='json'))
        assert r.status_code==422 and '來源與目前樂譜不符' in r.text
