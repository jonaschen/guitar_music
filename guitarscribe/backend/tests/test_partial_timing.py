import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.api import app, get_job_service
from app.models.jobs import AnalysisJob, JobStatus
from app.models.score import SongScore, SongInfo, AnalysisSummary
from app.services.jobs import JobStore
from app.services.partial_timing import local_bar_preview, preview_for_job


def observations(bars=12, meter=4):
    return dict(beats=[i*.5 for i in range(bars*meter+1)],
                downbeats=[i*.5*meter for i in range(bars+1)])


def test_agreeing_bars_are_exact_observations_without_new_edges():
    a=observations(); before=copy.deepcopy(a)
    result=local_bar_preview(a, a, 25)
    assert result['covered_seconds']==24
    assert len(result['regions'])==1
    assert result['regions'][0]['bars'][0]['beats']==a['beats'][:5]
    assert result['regions'][0]['end']==24  # Never extend to audio end.
    assert result['musical_verdict']=='unconfirmed' and not result['playback_changed']
    assert a==before


def test_missing_downbeat_only_removes_local_gap_not_all_good_bars():
    a=observations();b=copy.deepcopy(a);b['downbeats'].remove(12)
    result=local_bar_preview(a,b,25)
    assert [(r['start'],r['end']) for r in result['regions']]==[(0,10),(14,24)]
    assert result['covered_seconds']==20


@pytest.mark.parametrize('field', ['beats','downbeats'])
def test_phase_disagreement_never_becomes_a_region(field):
    a=observations();b=copy.deepcopy(a)
    if field=='beats':
        b={k:[t+.1 for t in times] for k,times in b.items()}
    else:
        b['downbeats']=[t+.5 for t in b['downbeats'][:-1]]
    assert local_bar_preview(a,b,30)['regions']==[]


def test_three_bar_island_is_not_promoted_and_three_four_meter_is_supported():
    a=observations(bars=3)
    assert local_bar_preview(a,a,10)['regions']==[]
    a=observations(bars=4,meter=3)
    assert local_bar_preview(a,a,10)['regions'][0]['beats_per_bar']==3


def test_agreed_double_density_region_still_stays_unknown():
    a=observations(bars=12)
    a['beats'] += [24+i*.25 for i in range(1,17)]
    a['downbeats'] += [25,26,27,28]
    result=local_bar_preview(a,a,29)
    assert [(r['start'],r['end']) for r in result['regions']]==[(0,24)]


def test_outside_audio_and_invalid_observations_do_not_make_bars():
    a=observations()
    assert local_bar_preview(a,a,7)['regions']==[]
    for bad in [dict(beats=[0,float('nan')],downbeats=[0,1]),
                dict(beats=[0,0,1],downbeats=[0,1]),dict(beats=[0,1],downbeats=[0,.7])]:
        assert local_bar_preview(bad,a,30)['regions']==[]


def test_global_median_between_two_densities_does_not_hide_transition():
    a=observations(bars=8)
    a['beats'] += [16+i*.25 for i in range(1,33)]
    a['downbeats'] += list(range(17,25))
    result=local_bar_preview(a,a,25)
    assert [(r['start'],r['end']) for r in result['regions']]==[(0,16),(17,24)]
    # The boundary bar is unknown, even when both decoders make the same jump.
    assert result['covered_seconds']==23


def make_job():
    return AnalysisJob(id='local-bars',status=JobStatus.COMPLETED,
        created_at=datetime.now(timezone.utc).isoformat(),updated_at=datetime.now(timezone.utc).isoformat(),score=SongScore(
        song=SongInfo(duration_seconds=25,source_start_seconds=40),
        analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='')))


def test_artifact_failure_and_full_grid_preserve_current_work(tmp_path):
    job=make_job();before=job.model_dump_json()
    assert preview_for_job(job,tmp_path)['reason']=='comparison_unavailable'
    path=tmp_path/'timing-recovery.json';path.write_text('{broken')
    assert preview_for_job(job,tmp_path)['reason']=='comparison_unreadable'
    path.write_text(json.dumps(dict(primary=observations(),candidate=observations())))
    preview=preview_for_job(job,tmp_path)
    assert preview['source_start_seconds']==40 and preview['regions'][0]['start']==0
    assert job.model_dump_json()==before
    job.score.analysis=AnalysisSummary()
    assert preview_for_job(job,tmp_path)['reason']=='full_grid_available'


@pytest.mark.asyncio
async def test_endpoint_is_read_only_and_requires_completed_existing_job(tmp_path):
    store=JobStore(tmp_path/'jobs');job=make_job();store.save(job)
    directory=store.job_dir(job.id);directory.mkdir()
    artifact=directory/'timing-recovery.json'
    artifact.write_text(json.dumps(dict(primary=observations(),candidate=observations())))
    before=store.database_path.read_bytes(),artifact.read_bytes()
    original=app.dependency_overrides.copy()
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=store.load,store=store)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/api/v1/jobs/local-bars/timing-preview')
            assert response.status_code==200 and response.json()['covered_seconds']==24
            assert response.json()['source_start_seconds']==40
            assert (store.database_path.read_bytes(),artifact.read_bytes())==before
            assert (await client.get('/api/v1/jobs/missing/timing-preview')).status_code==404
            job.status=JobStatus.BEAT_ANALYSIS;store.save(job)
            assert (await client.get('/api/v1/jobs/local-bars/timing-preview')).status_code==409
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(original)
