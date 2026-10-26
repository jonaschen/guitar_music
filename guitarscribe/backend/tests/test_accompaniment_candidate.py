from types import SimpleNamespace
import io

import mido
import pytest
from httpx import AsyncClient, ASGITransport

from app.api import app, get_job_service
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.jobs import AnalysisJob, JobStatus
from app.models.score import SongScore, SongInfo
from app.services.accompaniment_candidate import build_candidate
from app.services.revisions import RevisionStore
from app.exporters.midi import compile_playback_manifest, export_midi


def source():
    return SongScore(song=SongInfo(duration_seconds=2, source_start_seconds=18),
        chords=[ChordEvent(id='old', start=0, end=2, symbol='C')],
        beats=[BeatInfo(time=i*.5,beat=i+1,measure=1) for i in range(4)],
        melody=[MelodyNote(id='manual', start=.123, end=.728, midi=64, note='E4', edited=True)])


def test_candidate_preserves_manual_melody_gaps_short_chords_and_export(tmp_path):
    score=source(); score.rhythm.display=['D', None, 'D', None]; before=score.model_dump_json()
    candidate=build_candidate(score,[dict(start=0,end=.75,symbol='G'),
        dict(start=.75,end=1,symbol='N'),dict(start=1,end=1.075,symbol='F'),
        dict(start=1.075,end=2.1,symbol='C'),dict(start=2.1,end=2,symbol='N')], {'chord_accompaniment_sha256':'a'*64})
    assert score.model_dump_json()==before
    assert [(c.start,c.end,c.symbol) for c in candidate.chords]==[(0,.75,'G'),(1,1.075,'F'),(1.075,2,'C')]
    for field in ['melody','melody_edits','beats','rhythm','lyrics','guitar','song','key_context']:
        assert getattr(candidate,field)==getattr(score,field)
    store=RevisionStore(tmp_path); original=store.save(score); saved=store.save(candidate)
    assert RevisionStore(tmp_path).load(saved)==candidate and store.load(original)==score
    manifest=compile_playback_manifest(candidate)
    assert any(e.track=='guitar' for e in manifest.events)
    expected=sorted((e.start+(e.pitch_offsets[i] if e.pitch_offsets else 0),p)
                    for e in manifest.events if e.track!='metronome' for i,p in enumerate(e.pitches))
    # MIDI and playback share event starts, including manually edited melody.
    t=0.; actual=[]; endings=[]
    for msg in mido.MidiFile(file=io.BytesIO(export_midi(candidate))):
        t+=msg.time
        if msg.type=='note_on' and msg.velocity: actual.append((t,msg.note))
        if msg.type=='note_off': endings.append((t,msg.note))
    actual.sort()
    assert len(actual)==len(expected)
    for (t,p),(s,q) in zip(actual,expected):
        assert p==q and abs(t-s)<.002
    expected_ends=sorted((e.end,p) for e in manifest.events if e.track!='metronome' for p in e.pitches)
    assert len(endings)==len(expected_ends)
    for (t,p),(s,q) in zip(sorted(endings),expected_ends):
        assert p==q and abs(t-s)<.002


@pytest.mark.parametrize('events',[
    [dict(start=0,end=1,symbol='C'),dict(start=.8,end=2,symbol='G')],
    [dict(start=0,end=2.2,symbol='C')],
    [dict(start=0,end=0,symbol='C')],
    [dict(start=0,end=2,symbol='N')],
])
def test_rejects_bad_intervals(events):
    with pytest.raises(ValueError):build_candidate(source(),events,{})


@pytest.mark.asyncio
async def test_api_preserves_work_and_blocks_missing_or_incompatible_sources(tmp_path,monkeypatch):
    score=source(); score.provenance.parameters['vocal_source_separated']=True
    job=AnalysisJob(id='test',status=JobStatus.COMPLETED,score=score,created_at='2026-10-26',updated_at='2026-10-26')
    before=job.model_dump_json(); calls=[]
    def analyze(current,directory,job_id):
        calls.append(job_id)
        return build_candidate(current,[dict(start=0,end=2,symbol='G')],{})
    monkeypatch.setattr('app.services.accompaniment_candidate.analyze_existing_stem',analyze)
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=lambda _:job,store=SimpleNamespace(job_dir=lambda _:tmp_path))
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            path='/api/v1/jobs/test/accompaniment-candidate';body=score.model_dump(mode='json')
            assert (await client.post(path,json=body)).status_code==404
            assert not calls
            for name in ['analysis-source.wav','accompaniment-stem.wav']:(tmp_path/name).write_bytes(b'fixture')
            result=await client.post(path,json=body)
            assert result.status_code==200,result.text
            assert result.json()['melody']==body['melody'] and result.json()['beats']==body['beats']
            assert job.model_dump_json()==before
            assert (await client.post(path,json=result.json())).status_code==409
            changed=score.model_copy(deep=True);changed.chords[0].edited=True
            assert (await client.post(path,json=changed.model_dump(mode='json'))).status_code==409
            changed=score.model_copy(deep=True);changed.song.source_start_seconds=0
            assert (await client.post(path,json=changed.model_dump(mode='json'))).status_code==409
            assert calls==['test']
    finally:app.dependency_overrides.clear()
