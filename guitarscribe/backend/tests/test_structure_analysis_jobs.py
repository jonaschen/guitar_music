"""Lifecycle tests use a tiny real subprocess, never the music inference model."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.song_structure import source_for_job, SongStructureStore, StructureDocument
from app.services.structure_analysis_jobs import StructureAnalysisJobs
from app.song_structure_api import get_structure_analysis_jobs


@pytest.fixture
def setup(tmp_path):
    audio_dir = tmp_path / 'song'; audio_dir.mkdir()
    (audio_dir / 'input.wav').write_bytes(b'unchanged source audio')
    job = SimpleNamespace(id='song', status=JobStatus.COMPLETED, skip_seconds=0, analysis_seconds=None,
                          score=SongScore.model_validate({'song': {'title': 'Test', 'duration_seconds': 8.}}))
    source = source_for_job(job, audio_dir).model_dump(mode='json')
    runner = tmp_path / 'runner.py'
    runner.write_text('''import argparse,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--protocol');p.add_argument('--job');p.add_argument('--out');a=p.parse_args()
protocol=json.loads(Path(a.protocol).read_text());source=protocol['sources'][0];out=Path(a.out);out.mkdir(parents=True)
behavior=protocol.get('test_behavior','success')
if behavior=='child':
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
 (out/'child.pid').write_text(str(child.pid))
if behavior in ['wait','child']:time.sleep(120)
if behavior=='fail':raise RuntimeError('test failure')
duration=source['root_source']['duration']
sections=[dict(id='section-1',start=0.,end=duration,label='verse',display_label='主歌',review_status='unreviewed',model_end=duration,generated_gap=False)]
candidate=dict(title=source['title'],job=source['job'],fingerprint=source['root_source']['fingerprint'],source_start=source['root_source']['source_start'],duration=duration,sections=sections,ready_as_default=False,semantic_quality='not_evaluated')
if behavior=='wrong':candidate['fingerprint']='0'*64
(out/'candidate.json').write_text(json.dumps(candidate))
(out/'manifest.json').write_text(json.dumps(dict(status='candidate_ready_unreviewed',source=source)))
''')
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps({'id': 'test', 'preprocessing': {'python': sys.executable},
                                    'resource_limits': {'seconds_per_song': 1200}}))
    manager = StructureAnalysisJobs(tmp_path / 'work', python=sys.executable, runner=runner,
                                    protocol=protocol, timeout=5., poll_interval=.03, supervised=False)
    def revalidate(): return source_for_job(job, audio_dir).model_dump(mode='json')
    before_score = job.score.model_dump_json()
    yield SimpleNamespace(manager=manager, directory=audio_dir, source=source, job=job, protocol=protocol,
                          runner=runner, revalidate=revalidate, work=tmp_path / 'work')
    manager.cancel('song')
    manager.wait(timeout=5)
    assert job.score.model_dump_json() == before_score
    assert (audio_dir / 'input.wav').read_bytes() == b'unchanged source audio'


def configure(setup, behavior):
    value = json.loads(setup.protocol.read_text()); value['test_behavior'] = behavior
    setup.protocol.write_text(json.dumps(value))


def start(s, force=False):
    return s.manager.start('song', s.source, s.directory / 'input.wav', 'Test', s.revalidate, force=force)


def terminal(s, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = s.manager.status('song', s.source)
        if result['state'] not in ('running', 'cancelling'): return result
        time.sleep(.03)
    raise AssertionError('Worker did not settle')


def test_success_is_only_a_candidate_and_ready_survives_manager_restart(setup):
    s = setup
    store = SongStructureStore(s.work / 'song-structure.sqlite3')
    assert s.manager.status('song', s.source)['state'] == 'idle'
    assert start(s)['state'] == 'running'
    result = terminal(s)
    assert result['state'] == 'ready' and result['candidate']['source'] == s.source
    StructureDocument.model_validate(result['candidate'])
    assert result['candidate']['sections'][0]['name_review_status'] == 'unreviewed'
    assert store.read('song')['document'] is None
    again = start(s)
    assert again['run_id'] == result['run_id']
    restarted = StructureAnalysisJobs(s.work)
    assert restarted.status('song', s.source)['candidate'] == result['candidate']
    assert start(s, force=True)['run_id'] != result['run_id']
    assert terminal(s)['state'] == 'ready'


def test_global_single_flight_across_manager_instances_and_duplicate_start(setup):
    s = setup; configure(s, 'wait')
    first = start(s)
    assert start(s)['run_id'] == first['run_id']
    other = StructureAnalysisJobs(s.work, python=sys.executable, runner=s.runner, protocol=s.protocol, supervised=False)
    source = dict(s.source, job_id='other')
    assert other.start('other', source, s.directory / 'input.wav', 'Other', lambda: source)['state'] == 'busy'
    assert other.cancel('song')['state'] == 'cancelling'
    assert terminal(s)['state'] == 'cancelled'


@pytest.mark.parametrize('behavior,expected', [('fail', 'failed'), ('wrong', 'failed'), ('wait', 'failed')])
def test_failed_invalid_and_timed_out_runs_never_publish_candidates(setup, behavior, expected):
    s = setup; configure(s, behavior)
    if behavior == 'wait': s.manager.timeout = .15
    start(s); result = terminal(s)
    assert result['state'] == expected and result['candidate'] is None
    if behavior == 'wait': assert '時間' in result['message']
    configure(s, 'success'); s.manager.timeout = 5
    start(s); assert terminal(s)['state'] == 'ready'


def test_completion_and_ready_reads_revalidate_both_source_hashes(setup):
    s = setup
    changed = dict(s.source, audio_sha256='0' * 64)
    s.revalidate = lambda: changed
    start(s); result = terminal(s)
    assert result['state'] == 'stale' and result['candidate'] is None
    s.revalidate = lambda: s.source
    start(s); assert terminal(s)['state'] == 'ready'
    for key in ('audio_sha256', 'fingerprint'):
        stale = s.manager.status('song', dict(s.source, **{key: '0' * 64}))
        assert stale['state'] == 'stale' and stale['candidate'] is None


def test_cancel_terminates_descendant_process_group(setup):
    s = setup; configure(s, 'child'); start(s)
    end = time.monotonic() + 5
    paths = []
    while not paths and time.monotonic() < end:
        paths = list(s.work.rglob('child.pid')); time.sleep(.03)
    assert paths
    child = int(paths[0].read_text())
    assert s.manager.cancel('song')['state'] == 'cancelling'
    assert terminal(s)['state'] == 'cancelled'
    def living():
        try: return Path(f'/proc/{child}/stat').read_text().split(') ', 1)[1][0] != 'Z'
        except FileNotFoundError: return False
    end = time.monotonic() + 2
    while living() and time.monotonic() < end: time.sleep(.03)
    assert not living()


def test_orphaned_running_state_becomes_interrupted_and_can_retry(setup):
    s = setup; start(s); assert terminal(s)['state'] == 'ready'
    path = next(s.work.rglob('state.json')); state = json.loads(path.read_text())
    state.update(state='running', owner={'pid': 999999999, 'start': 'missing'}, process=None)
    path.write_text(json.dumps(state))
    assert s.manager.status('song', s.source)['state'] == 'interrupted'
    start(s); assert terminal(s)['state'] == 'ready'


def test_missing_runtime_is_explicit_and_does_not_start(setup):
    manager = StructureAnalysisJobs(setup.work / 'missing')
    assert manager.status('song', setup.source)['state'] == 'unavailable'
    assert manager.start('song', setup.source, setup.directory / 'input.wav', 'Test', setup.revalidate)['state'] == 'unavailable'


def test_import_completed_run_reuses_validated_candidate_without_inference_or_editable_writes(setup):
    s = setup; start(s); ready = terminal(s)
    run = next(s.work.rglob('result'))
    original_bytes = {p.name: p.read_bytes() for p in run.iterdir() if p.is_file()}
    manager = StructureAnalysisJobs(s.work / 'import-only')
    imported = manager.import_completed_run('song', run, s.source, s.revalidate)
    assert imported['state'] == 'ready' and imported['candidate'] == ready['candidate']
    assert manager.status('song', s.source)['candidate'] == ready['candidate']
    assert manager.import_completed_run('song', run, s.source, s.revalidate)['run_id'] == imported['run_id']
    assert {p.name: p.read_bytes() for p in run.iterdir() if p.is_file()} == original_bytes
    assert not list((s.work / 'import-only').rglob('*.sqlite3'))


@pytest.mark.parametrize('fault', ['hash', 'live_source', 'manifest', 'schema'])
def test_import_rejects_stale_or_invalid_candidates(setup, fault):
    s = setup; start(s); assert terminal(s)['state'] == 'ready'
    run = next(s.work.rglob('result'))
    source, revalidate = s.source, s.revalidate
    if fault == 'hash': source = dict(source, audio_sha256='0' * 64)
    if fault == 'live_source': revalidate = lambda: dict(source, fingerprint='0' * 64)
    if fault == 'manifest':
        manifest = json.loads((run / 'manifest.json').read_text()); manifest['status'] = 'running'
        (run / 'manifest.json').write_text(json.dumps(manifest))
    if fault == 'schema':
        candidate = json.loads((run / 'candidate.json').read_text()); candidate['sections'][0]['start'] = 2
        (run / 'candidate.json').write_text(json.dumps(candidate))
    manager = StructureAnalysisJobs(s.work / 'import-only')
    with pytest.raises(ValueError): manager.import_completed_run('song', run, source, revalidate)
    assert not list((s.work / 'import-only').rglob('document.json'))


def test_explicit_cache_rebind_for_identical_recording_retains_original_provenance(setup):
    s = setup; start(s); ready = terminal(s)
    run = next(s.work.rglob('result')); before = (run / 'candidate.json').read_bytes()
    target = dict(s.source, job_id='same-recording-new-job', fingerprint='c' * 64)
    manager = StructureAnalysisJobs(s.work / 'rebind')
    with pytest.raises(ValueError): manager.import_completed_run(target['job_id'], run, target, lambda: target)
    result = manager.import_completed_run(target['job_id'], run, target, lambda: target, allow_rebind=True)
    assert result['state'] == 'ready' and result['candidate']['source'] == target
    assert result['candidate']['candidate_sha256'] == ready['candidate']['candidate_sha256']
    assert result['candidate']['sections'] == ready['candidate']['sections']
    provenance = json.loads(next(manager.root.rglob('import.json')).read_text())
    assert provenance['original_source'] == s.source and provenance['original_job'] == 'song'
    assert (run / 'candidate.json').read_bytes() == before


@pytest.mark.parametrize('field,value', [('audio_sha256', 'c' * 64), ('duration', 8.01), ('source_start', 1.)])
def test_cache_rebind_never_accepts_other_recording_or_time_range(setup, field, value):
    s = setup; start(s); terminal(s); run = next(s.work.rglob('result'))
    target = dict(s.source, job_id='other', fingerprint='c' * 64); target[field] = value
    manager = StructureAnalysisJobs(s.work / 'rebind')
    with pytest.raises(ValueError):
        manager.import_completed_run('other', run, target, lambda: target, allow_rebind=True)
    assert not list(manager.root.rglob('document.json'))


def test_reanalysis_does_not_overwrite_existing_user_structure_or_root_database(setup):
    s = setup; start(s); candidate = terminal(s)['candidate']
    structure = SongStructureStore(s.work / 'song-structure.sqlite3')
    human = deepcopy(candidate); human['sections'][0]['display_label'] = '人工主歌'; human['sections'][0]['note'] = 'Keep me'
    structure.save('song', human, 0)
    from app.services.root_practice import RootPracticeStore, initial_document
    roots = RootPracticeStore(s.work / 'root-practice.sqlite3'); roots.save('song', initial_document(s.job), 0)
    before = {path: path.read_bytes() for path in s.work.glob('*.sqlite3')}
    start(s, force=True); assert terminal(s)['state'] == 'ready'
    assert structure.read('song')['document'] == human
    assert {path: path.read_bytes() for path in before} == before


def test_supervised_subprocess_scope_is_bounded_and_cancellable_when_available(setup):
    s = setup
    supervised = StructureAnalysisJobs(s.work / 'scoped', python=sys.executable, runner=s.runner,
                                       protocol=s.protocol, timeout=5, poll_interval=.03)
    if not supervised._available(): pytest.skip('User systemd is unavailable')
    s.manager = supervised; configure(s, 'child'); start(s)
    end = time.monotonic() + 5
    while not list(supervised.root.rglob('child.pid')) and time.monotonic() < end: time.sleep(.03)
    assert list(supervised.root.rglob('child.pid'))
    state = json.loads(next(supervised.root.rglob('state.json')).read_text())
    import subprocess
    output = subprocess.check_output(['systemctl', '--user', 'show', state['unit'],
                                      '-p', 'MemoryMax', '-p', 'MemorySwapMax', '-p', 'CPUQuotaPerSecUSec',
                                      '-p', 'RuntimeMaxUSec', '-p', 'TimeoutStopUSec'], text=True)
    assert 'MemoryMax=2684354560' in output and 'MemorySwapMax=536870912' in output
    assert 'CPUQuotaPerSecUSec=2s' in output
    assert 'RuntimeMaxUSec=5s' in output
    assert 'TimeoutStopUSec=3s' in output
    supervised.cancel('song'); assert terminal(s)['state'] == 'cancelled'


def test_scope_hard_timeout_survives_owner_process_exit_without_status_polling(setup):
    s = setup
    probe = StructureAnalysisJobs(s.work / 'orphan', python=sys.executable, runner=s.runner,
                                  protocol=s.protocol, timeout=1., poll_interval=.03)
    if not probe._available(): pytest.skip('User systemd is unavailable')
    configure(s, 'child')
    import subprocess
    config = dict(work=str(s.work / 'orphan'), runner=str(s.runner), protocol=str(s.protocol),
                  source=s.source, audio=str(s.directory / 'input.wav'))
    code = '''import json,os,sys,time
from pathlib import Path
from app.services.structure_analysis_jobs import StructureAnalysisJobs
c=json.loads(sys.argv[1]);m=StructureAnalysisJobs(c['work'],python=sys.executable,runner=c['runner'],protocol=c['protocol'],timeout=1.,poll_interval=10)
m.start('song',c['source'],c['audio'],'Test',lambda:c['source'])
deadline=time.monotonic()+5
while not list(m.root.rglob('child.pid')) and time.monotonic()<deadline:time.sleep(.01)
os._exit(0 if list(m.root.rglob('child.pid')) else 2)
'''
    try:
        subprocess.run([sys.executable, '-c', code, json.dumps(config)], check=True, timeout=8)
        child = int(next(probe.root.rglob('child.pid')).read_text())
        def alive():
            try: return Path(f'/proc/{child}/stat').read_text().split(') ', 1)[1][0] != 'Z'
            except FileNotFoundError: return False
        deadline = time.monotonic() + 5
        # Do not call the manager: only systemd's own RuntimeMaxSec can stop it.
        while alive() and time.monotonic() < deadline: time.sleep(.05)
        assert not alive()
        assert probe.status('song', s.source)['state'] == 'interrupted'
    finally:
        probe.status('song', s.source)  # Also clean up if a hard-timeout assertion fails.


async def test_api_hash_preconditions_cancel_and_candidates_never_touch_saved_structure(setup):
    s = setup
    service = SimpleNamespace(get=lambda job: s.job, store=SimpleNamespace(job_dir=lambda _: s.directory))
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_structure_analysis_jobs] = lambda: s.manager
    url = '/api/v1/jobs/song/song-structure/analysis'
    body = {key: s.source[key] for key in ('fingerprint', 'audio_sha256')}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get(url)).json()['state'] == 'idle'
            assert (await client.post(url, json={})).status_code == 422
            assert (await client.post(url, json={**body, 'audio_sha256': '0' * 64})).status_code == 409
            configure(s, 'wait')
            response = await client.post(url, json=body)
            assert response.status_code == 200 and response.json()['state'] == 'running'
            assert (await client.delete(url)).json()['state'] == 'cancelling'
            assert terminal(s)['state'] == 'cancelled'
            configure(s, 'success')
            assert (await client.post(url, json=body)).json()['state'] == 'running'
            assert terminal(s)['state'] == 'ready'
            ready = (await client.get(url)).json()
            assert ready['candidate']['source'] == s.source
            assert (await client.post(url, json=body)).json()['run_id'] == ready['run_id']
    finally:
        app.dependency_overrides.pop(get_job_service, None)
        app.dependency_overrides.pop(get_structure_analysis_jobs, None)
