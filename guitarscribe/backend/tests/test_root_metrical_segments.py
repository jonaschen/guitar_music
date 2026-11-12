from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from app.services.root_segments import PracticeGrid, segmentation_plan, grid_aligned
from app.services.root_practice import PracticeDocument, RootPracticeStore, PracticeConflict


def document(duration=8):
    return dict(schema_version=1,source=dict(job_id='song',fingerprint='a'*64,duration=duration,source_start=90),segments=[dict(id='old',start=0,end=duration,root=None,original_root=None,status='pending')])


def evidence(roots,step=.5):
    frames=[]
    for i,root in enumerate(roots):
        values=[.01]*12
        if root is not None:values[root]=.8
        frames.append([i*step,(i+1)*step,*values,.9 if root is None else .001])
    return dict(frames=frames)


@pytest.mark.parametrize('roots,ends',[
    ([0,0,0,0],[2]), # one root, one bar
    ([0,0,7,7],[1,2]), # two half bars
    ([0,2,7,7],[.5,1,2]), # only first half needs quarters
    ([0,0,7,9],[1,1.5,2]),
    ([0,2,7,9],[.5,1,1.5,2]),
    ([None,None,7,7],[2]), # missing evidence is not a change
])
def test_conservative_exceptions(roots,ends):
    plan=segmentation_plan(document(2),PracticeGrid(bpm=120,beats=4,anchor=0),evidence(roots))
    assert [s['end'] for s in plan['document']['segments']]==ends
    assert all(s['root'] is None for s in plan['document']['segments'])
    PracticeDocument.model_validate(plan['document'])


def test_short_transient_and_ambiguous_observations_do_not_split():
    frames=evidence([0]*40,.05);frames['frames'][15][2]=.01;frames['frames'][15][9]=.8
    grid=PracticeGrid(bpm=120,beats=4,anchor=0)
    assert len(segmentation_plan(document(2),grid,frames)['document']['segments'])==1
    for row in frames['frames']:row[2:14]=[.1]*12
    assert len(segmentation_plan(document(2),grid,frames)['document']['segments'])==1
    assert len(segmentation_plan(document(2),grid,None)['document']['segments'])==1


@pytest.mark.parametrize('beats',[1,2,3,4,6,8,12])
def test_arbitrary_anchor_all_boundaries_and_subdivisions_align(beats):
    grid=PracticeGrid(bpm=115,beats=beats,anchor=5.123)
    plan=segmentation_plan(document(11.27),grid,evidence([0,0,7,7]*6))
    d=PracticeDocument.model_validate(plan['document']);assert d.segments[0].start==0 and d.segments[-1].end==11.27
    assert d.source.source_start==90 # local-time grid never adds the source offset twice
    assert grid_aligned(d.segments,grid,11.27)
    for s in d.segments[:-1]:assert abs((s.end-grid.anchor)/(60/grid.bpm)-round((s.end-grid.anchor)/(60/grid.bpm)))<1e-7


def test_transfer_never_extends_confirmed_root_into_unknown_or_overwrites_disagreement():
    d=document(6);d['segments']=[
        dict(id='a',start=0,end=1,root=0,original_root=None,status='confirmed'),
        dict(id='b',start=1,end=2,root=7,original_root=None,status='confirmed'),
        dict(id='c',start=2,end=3,root=2,original_root=None,status='confirmed'),
        dict(id='d',start=3,end=4,root=None,original_root=None,status='pending'),
        dict(id='e',start=4,end=6,root=4,original_root=None,status='confirmed')]
    before=deepcopy(d);plan=segmentation_plan(d,PracticeGrid(bpm=120,beats=4,anchor=0))
    assert [s['root'] for s in plan['document']['segments']]==[None,None,4]
    assert [s['status'] for s in plan['document']['segments']]==['unsure','unsure','confirmed']
    assert [s['roots'] for s in plan['review']]==[[0,7],[2]]
    assert d==before


def test_v2_rejects_off_grid_cross_bar_and_three_quarter_intervals():
    plan=segmentation_plan(document(4),PracticeGrid(bpm=120,beats=4,anchor=0))['document']
    for boundary in [.2,1.5,2.5]:
        bad=deepcopy(plan);bad['segments'][0]['end']=boundary;bad['segments'][1]['start']=boundary
        with pytest.raises(ValidationError):PracticeDocument.model_validate(bad)
    bad=deepcopy(plan);bad['grid']=None
    with pytest.raises(ValidationError):PracticeDocument.model_validate(bad)


def test_atomic_archive_and_old_client_cannot_remove_meter(tmp_path):
    store=RootPracticeStore(tmp_path/'roots.sqlite3');old=document(4);old['segments'][0].update(root=7,status='confirmed')
    store.save('song',old,0)
    new=segmentation_plan(old,PracticeGrid(bpm=120,beats=4,anchor=0))['document'];store.save('song',new,1)
    archived=store.history('song');assert archived[0]['version']==1;assert archived[0]['document']['segments']==old['segments']
    with pytest.raises(PracticeConflict):store.save('song',old,2)
    assert len(store.history('song'))==1
    with pytest.raises(PracticeConflict):store.save('song',new,1)
    restored=segmentation_plan(archived[0]['document'],PracticeGrid(bpm=120,beats=4,anchor=0))['document']
    assert store.save('song',restored,2)['version']==3
    assert len(store.history('song'))==2


def test_limits():
    with pytest.raises(ValueError):segmentation_plan(document(),PracticeGrid(bpm=115,beats=4,anchor=9))
    with pytest.raises(ValueError):segmentation_plan(document(7200),PracticeGrid(bpm=300,beats=1,anchor=0))

@pytest.mark.asyncio
async def test_plan_api_is_read_only_checks_source_and_returns_history(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from app.api import app, get_job_service
    from app.root_practice_api import get_root_practice_store
    from app.models.score import SongScore
    from app.models.jobs import JobStatus
    item=SimpleNamespace(id='song',score=SongScore.model_validate({'song':{'duration_seconds':8},'chords':[]}),status=JobStatus.COMPLETED,skip_seconds=0,analysis_seconds=None);before=item.score.model_dump_json();store=RootPracticeStore(tmp_path/'roots.sqlite3')
    service=SimpleNamespace(get=lambda _:item,store=SimpleNamespace(job_dir=lambda _:tmp_path))
    app.dependency_overrides[get_job_service]=lambda:service
    app.dependency_overrides[get_root_practice_store]=lambda:store
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            url='/api/v1/jobs/song/root-practice';initial=(await client.get(url)).json()
            assert initial['document']['schema_version']==2
            body=dict(document=initial['document'],grid=dict(bpm=120,beats=4,anchor=.25))
            response=await client.post(url+'/segment-plan',json=body)
            assert response.status_code==200 and response.json()['evidence_available'] is False
            assert store.read('song')['version']==0 and store.history('song')==[]
            d=response.json()['document'];PracticeDocument.model_validate(d)
            assert (await client.put(url,json=dict(expected_version=0,document=d))).status_code==200
            assert (await client.get(url+'/history')).json()==[]
            assert (await client.put(url,json=dict(expected_version=1,document=d))).status_code==200
            assert len((await client.get(url+'/history')).json())==1
            body['document']['source']['fingerprint']='b'*64
            assert (await client.post(url+'/segment-plan',json=body)).status_code==409
        assert item.score.model_dump_json()==before
    finally:
        app.dependency_overrides.pop(get_job_service,None);app.dependency_overrides.pop(get_root_practice_store,None)
