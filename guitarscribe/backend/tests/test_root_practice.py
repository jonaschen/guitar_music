import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api import app, get_job_service
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.root_practice_api import get_root_practice_store
from app.services.root_practice import PracticeDocument, RootPracticeStore, PracticeConflict, initial_document
from app.services.root_candidates import compact_trace, candidates_for_range, initial_segments, pitch_class
from app.services.root_candidate_jobs import RootCandidateJobs


def job(job_id='song'):
    score=SongScore.model_validate({'song':{'duration_seconds':8},'chords':[
        {'id':'c','start':1,'end':3,'symbol':'C/E'}, {'id':'c7','start':3,'end':4,'symbol':'Cmaj7'},
        {'id':'am','start':5,'end':8,'symbol':'Am7'}]})
    return SimpleNamespace(id=job_id,score=score,status=JobStatus.COMPLETED,skip_seconds=0,analysis_seconds=None)


def test_roots_are_not_bass_and_gaps_survive():
    assert [pitch_class(s) for s in ['C/E','A:min7','B#','Db','N','X']]==[0,9,0,1,None,None]
    original=job().score.model_dump(mode='json');before=deepcopy(original)
    segments=initial_segments(original)
    assert [(s['start'],s['end'],s['original_root']) for s in segments]==[(0,1,None),(1,4,0),(4,5,None),(5,8,9)]
    assert all(s['root'] is None for s in segments) and original==before


def trace():
    names=['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B','N']
    values=[.01]*13;values[0]=.4;values[4]=.3;values[7]=.2
    total=sum(values);values=[v/total for v in values]
    return {'dictionary':[{'label':s}for s in names], 'frames':[
        {'sec':t,'nsec':0,'emission':list(values)}for t in [0,1,3]]}


def test_real_frame_weighting_no_invented_tail_and_distinct_top3():
    t=trace();second=t['frames'][1]['emission'];t['frames'][1]['emission']=[second[(i+4)%12]if i<12 else second[12]for i in range(13)]
    compact=compact_trace(t)
    assert len(compact['frames'])==2
    result=candidates_for_range(compact,0,4)
    assert result['covered_seconds']==3 and result['coverage']==.75
    assert len({c['pitch_class']for c in result['candidates']})==3
    assert candidates_for_range(compact,3,4)['candidates']==[]
    first=candidates_for_range(compact,0,1)
    assert [c['pitch_class'] for c in first['candidates']]==[0,4,7]


def test_tied_or_n_dominant_frames_do_not_invent_three_answers():
    t=trace()
    for f in t['frames']:f['emission']=[1/13]*13
    assert candidates_for_range(compact_trace(t),0,3)['candidates']==[]
    for f in t['frames']:f['emission']=[.01]*12+[.88]
    assert candidates_for_range(compact_trace(t),0,3)['candidates']==[]
    t['frames'][1]['sec']=0
    with pytest.raises(ValueError):compact_trace(t)


def test_mean_pooling_has_no_profile_count_bonus():
    t=trace();t['dictionary'].append({'label':'C7'})
    for f in t['frames']:
        f['emission'].append(f['emission'][0]);total=sum(f['emission']);f['emission']=[v/total for v in f['emission']]
    row=compact_trace(t)['frames'][0]
    assert row[2]/row[6]==pytest.approx(4/3)


@pytest.mark.parametrize('change',[
    lambda d:d['segments'][0].update(start=.1),
    lambda d:d['segments'][0].update(end=float('nan')),
    lambda d:d['segments'][1].update(id=d['segments'][0]['id']),
    lambda d:d['segments'][0].update(root=12,status='confirmed'),
    lambda d:d['segments'][0].update(root=0,status='pending'),
    lambda d:d['segments'][0].update(root=None,status='confirmed'),
    lambda d:d['segments'][-1].update(end=9),
])
def test_bad_documents_rejected(change):
    d=initial_document(job()).model_dump(mode='json');change(d)
    with pytest.raises(ValidationError):PracticeDocument.model_validate(d)


def test_atomic_conflicts_reopen_and_source_protection(tmp_path):
    store=RootPracticeStore(tmp_path/'roots.sqlite3');d=initial_document(job()).model_dump(mode='json')
    def save(_):
        try:store.save('song',d,0);return 1
        except PracticeConflict:return 0
    with ThreadPoolExecutor(max_workers=8)as pool:assert sum(pool.map(save,range(8)))==1
    assert RootPracticeStore(store.path).read('song')['document']==d
    changed=deepcopy(d);changed['source']['fingerprint']='0'*64
    with pytest.raises(ValueError):store.save('song',changed,1)
    assert store.read('other')['version']==0


@pytest.mark.asyncio
async def test_candidate_cancellation_busy_cache_identity_and_retry(tmp_path,monkeypatch):
    import threading
    from app.services import root_candidate_jobs as module
    plugin=tmp_path/'plugin';plugin.mkdir();(plugin/'root-plugin.json').write_text('{}')
    monkeypatch.setattr(module,'plugin_path',lambda:plugin)
    manager=RootCandidateJobs();a=tmp_path/'a';a.mkdir();b=tmp_path/'b';b.mkdir();source={'fingerprint':'a'*64}
    began=threading.Event()
    def worker(directory,identity,audio,cancel):
        began.set()
        if cancel.wait(3):raise RuntimeError('cancelled')
        raise TimeoutError()
    monkeypatch.setattr(manager,'_run',worker)
    assert manager.start(a,source,tmp_path/'audio')['state']=='running'
    await asyncio.to_thread(began.wait,1)
    assert manager.start(b,source,tmp_path/'audio')['state']=='busy'
    manager.cancel(a);assert manager.status(a,source)['state']=='cancelling'
    await manager.running[str(a)]['task']
    assert manager.status(a,source)['state']=='failed' and not manager.cache_path(a).exists()
    def complete(directory,identity,audio,cancel):manager.cache_path(directory).write_text(json.dumps({'method':'root-mean-profile-duration-v1','source':identity,'frames':[]}))
    monkeypatch.setattr(manager,'_run',complete)
    manager.start(a,source,tmp_path/'audio');await manager.running[str(a)]['task']
    assert manager.status(a,source)['state']=='ready'
    assert manager.evidence(a,{'fingerprint':'b'*64})is None
    manager.cache_path(a).write_text('bad json');assert manager.evidence(a,source)is None


@pytest.mark.asyncio
async def test_api_roundtrip_expiry_rank_bounds_audio_crop_and_no_score_write(tmp_path):
    store=RootPracticeStore(tmp_path/'roots.sqlite3');source=job();source.analysis_seconds=8
    before=source.score.model_dump_json();expired=False
    (tmp_path/'input.wav').write_bytes(b'full-source')
    (tmp_path/'analysis-source.wav').write_bytes(b'cropped-source')
    def get(job_id):
        if expired or job_id!='song':raise FileNotFoundError()
        return source
    service=SimpleNamespace(get=get,store=SimpleNamespace(job_dir=lambda _:tmp_path))
    app.dependency_overrides[get_job_service]=lambda:service
    app.dependency_overrides[get_root_practice_store]=lambda:store
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test')as c:
            url='/api/v1/jobs/song/root-practice'
            response=(await c.get(url)).json();d=response['document']
            assert response['version']==0
            d['segments'][1].update(root=7,status='confirmed')
            assert (await c.put(url,json={'document':d,'expected_version':0})).status_code==200
            assert (await c.put(url,json={'document':d,'expected_version':0})).status_code==409
            assert (await c.get(url+'/audio',params={'fingerprint':d['source']['fingerprint']})).content==b'cropped-source'
            assert (await c.get(url+'/audio',params={'fingerprint':'0'*64})).status_code==409
            bad={'fingerprint':'0'*64,'start':0,'end':2}
            assert (await c.post('/api/v1/jobs/song/root-candidates/rank',json=bad)).status_code==409
            expired=True
            assert (await c.get(url)).json()['document']==d
            assert (await c.put(url,json={'document':d,'expected_version':1})).status_code==200
            assert (await c.get(url+'/audio',params={'fingerprint':d['source']['fingerprint']})).status_code==404
        assert source.score.model_dump_json()==before
    finally:
        app.dependency_overrides.pop(get_job_service,None);app.dependency_overrides.pop(get_root_practice_store,None)
