from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.root_practice_api import get_root_practice_store
from app.services.root_practice import RootPracticeStore, PracticeConflict, PracticeDocument
from app.services.root_reuse import RootReuseService, ReuseRequest, ReuseApply, ReuseUndo
from app.services.song_structure import source_for_job


def document(source=None):
    source = source or dict(job_id='song', fingerprint='a' * 64, duration=16., source_start=42.)
    specs = [('s0', 0, 1, 0, 'confirmed'), ('s1', 1, 2, 0, 'confirmed'),
             ('s2', 2, 4, 7, 'confirmed'), ('s3', 4, 6, None, 'unsure'),
             ('s4', 6, 7, 0, 'confirmed'), ('s5', 7, 8, 2, 'confirmed'),
             ('t0', 8, 10, None, 'pending'), ('t1', 10, 11, 7, 'confirmed'),
             ('t2', 11, 12, None, 'unsure'), ('t3', 12, 14, None, 'pending'),
             ('t4', 14, 16, None, 'pending')]
    return dict(schema_version=2, source=source, grid=dict(bpm=120., beats=4, anchor=0.),
                segments=[dict(id=i, start=float(a), end=float(b), root=root, status=status, original_root=9)
                          for i, a, b, root, status in specs])


@pytest.fixture
def setup(tmp_path):
    store = RootPracticeStore(tmp_path / 'roots.sqlite3')
    doc = document(); store.save('song', doc, 0)
    source = dict(doc['source'], audio_sha256='b' * 64)
    request = dict(expected_version=1, fingerprint=source['fingerprint'], audio_sha256=source['audio_sha256'],
                   source_range=dict(start=0., end=8.), target_range=dict(start=8., end=16.),
                   alignment_confirmed=True, source_label='主歌1', target_label='主歌2')
    return SimpleNamespace(store=store, service=RootReuseService(store), document=doc,
                           source=source, request=request, provider=lambda: deepcopy(source))


def plan(s, **overrides):
    return s.service.plan('song', ReuseRequest.model_validate({**s.request, **overrides}), s.source)


def apply(s, preview=None, selected=None):
    preview = preview or plan(s)
    body = ReuseApply.model_validate(dict(plan_id=preview['plan_id'], request=preview['request'],
                                         selected_target_ids=selected or ['t0']))
    return s.service.apply('song', body, s.provider)


def undo(s, operation, version):
    body = ReuseUndo(expected_version=version, fingerprint=s.source['fingerprint'], audio_sha256=s.source['audio_sha256'])
    return s.service.undo('song', operation['id'], body, s.provider)


def test_plan_is_read_only_and_preserves_uncertainty_protected_targets_and_subdivisions(setup):
    s = setup; before = s.store.path.read_bytes()
    result = plan(s)
    assert s.store.path.read_bytes() == before and s.store.read('song')['document'] == s.document
    assert result['beat_count'] == 16 and result['can_apply']
    assert [r['status'] for r in result['rows']] == [
        'fillable', 'already_same', 'target_protected', 'source_unknown', 'source_changes']
    assert result['rows'][0]['root'] == 0 and result['rows'][0]['source_ids'] == ['s0', 's1']
    assert result['counts']['fillable'] == 1
    assert not plan(s, alignment_confirmed=False)['can_apply']


@pytest.mark.parametrize('fault', ['v1', 'off_bar', 'unequal', 'overlap', 'outside', 'audio', 'fingerprint', 'version'])
def test_invalid_or_stale_mapping_is_rejected_without_changes(setup, fault):
    s = setup; request = deepcopy(s.request)
    if fault == 'v1':
        doc = deepcopy(s.document); doc['schema_version'] = 1; doc.pop('grid')
        with sqlite3.connect(s.store.path) as db: db.execute('UPDATE root_practice SET document=?', (json.dumps(doc),))
    if fault == 'off_bar': request['source_range'] = dict(start=1., end=7.)
    if fault == 'unequal': request['target_range']['end'] = 14.
    if fault == 'overlap': request['target_range'] = dict(start=6., end=14.)
    if fault == 'outside': request['target_range'] = dict(start=10., end=18.)
    if fault == 'audio': request['audio_sha256'] = 'c' * 64
    if fault == 'fingerprint': request['fingerprint'] = 'c' * 64
    if fault == 'version': request['expected_version'] = 0
    before = s.store.read('song')
    with pytest.raises((ValueError, PracticeConflict)):
        s.service.plan('song', ReuseRequest.model_validate(request), s.source)
    assert s.store.read('song') == before and not s.store.history('song')


def test_apply_is_one_cas_with_ledger_and_history_preserving_time_ids_and_original_roots(setup):
    s = setup; result = apply(s)
    snapshot, operation = result['snapshot'], result['operation']
    assert snapshot['version'] == 2 and operation['applied_version'] == 2
    changed = [dict(a) for a, b in zip(snapshot['document']['segments'], s.document['segments']) if a != b]
    assert changed == [{**s.document['segments'][6], 'root': 0, 'status': 'confirmed'}]
    assert s.store.history('song')[0]['document'] == s.document
    listing = s.service.ledger('song', s.source)
    assert listing['version'] == 2 and len(listing['operations']) == 1
    entry = listing['operations'][0]
    assert entry['mapping_matches'] and entry['target_matches'] and entry['can_undo']
    assert not entry['fully_equivalent'] and entry['target_ids'] == ['t0']
    assert entry['changes'][0]['before']['root'] is None
    assert entry['changes'][0]['after']['root'] == 0


@pytest.mark.parametrize('fault', ['protected', 'unknown', 'changed_source', 'stale_version', 'digest', 'unconfirmed', 'empty'])
def test_apply_rejects_invalid_selection_and_outdated_plans_atomically(setup, fault):
    s = setup; preview = plan(s)
    selected = ['t0']
    if fault == 'protected': selected = ['t0', 't2']
    if fault == 'unknown': selected = ['t0', 't3']
    if fault == 'changed_source': s.source['audio_sha256'] = 'c' * 64
    if fault == 'stale_version': s.store.save('song', s.document, 1)
    if fault == 'digest': preview['plan_id'] = '0' * 64
    if fault == 'unconfirmed': preview = plan(s, alignment_confirmed=False)
    if fault == 'empty': selected = []
    body = dict(plan_id=preview['plan_id'], request=preview['request'], selected_target_ids=selected)
    before = s.store.read('song'); history = s.store.history('song')
    with pytest.raises((ValueError, PracticeConflict)):
        s.service.apply('song', ReuseApply.model_validate(body), s.provider)
    assert s.store.read('song') == before and s.store.history('song') == history
    assert s.service.ledger('song', s.source)['operations'] == []


def test_simultaneous_apply_has_one_winner_and_one_ledger_entry(setup):
    s = setup; preview = plan(s)
    def attempt():
        try: return apply(s, preview)['snapshot']['version']
        except PracticeConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(map(str, results)) == ['2', 'conflict']
    assert len(s.service.ledger('song', s.source)['operations']) == 1
    assert len(s.store.history('song')) == 1


def test_failed_root_write_rolls_back_ledger_and_history(setup):
    s = setup
    with sqlite3.connect(s.store.path) as db:
        db.execute("CREATE TRIGGER reject_reuse BEFORE UPDATE ON root_practice BEGIN SELECT RAISE(ABORT, 'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError): apply(s)
    assert s.store.read('song')['version'] == 1 and not s.store.history('song')
    assert s.service.ledger('song', s.source)['operations'] == []


def test_undo_is_one_transaction_and_preserves_subsequent_unrelated_edits(setup):
    s = setup; operation = apply(s)['operation']
    next_doc = s.store.read('song')['document']; next_doc['segments'][0]['root'] = 5
    s.store.save('song', next_doc, 2)
    before_undo = s.service.ledger('song', s.source)['operations'][0]
    assert not before_undo['mapping_matches'] and before_undo['can_undo']
    result = undo(s, operation, 3)
    assert result['snapshot']['version'] == 4
    assert result['snapshot']['document']['segments'][0]['root'] == 5
    assert result['snapshot']['document']['segments'][6] == s.document['segments'][6]
    assert result['operation']['status'] == 'undone' and result['operation']['undone_version'] == 4
    with pytest.raises(PracticeConflict): undo(s, operation, 4)


@pytest.mark.parametrize('change', ['target', 'grid', 'source'])
def test_undo_never_overwrites_changed_targets_grid_or_audio(setup, change):
    s = setup; operation = apply(s)['operation']
    doc = s.store.read('song')['document']
    if change == 'target': doc['segments'][6]['root'] = 5
    if change == 'grid': doc['grid']['bpm'] = 60.
    if change == 'source': s.source['audio_sha256'] = 'c' * 64
    s.store.save('song', doc, 2); before = s.store.read('song')
    with pytest.raises(PracticeConflict): undo(s, operation, 3)
    assert s.store.read('song') == before


def test_generic_undo_invalidates_relation_in_ledger_without_overwriting_it(setup):
    s = setup; apply(s); s.store.save('song', s.document, 2)
    entry = s.service.ledger('song', s.source)['operations'][0]
    assert entry['status'] == 'applied'
    assert not entry['mapping_matches'] and not entry['can_undo'] and not entry['fully_equivalent']


def test_unsaved_song_can_compare_live_source_without_creating_root_or_ledger(tmp_path):
    store = RootPracticeStore(tmp_path / 'roots.sqlite3')
    service = RootReuseService(store)
    source = dict(document()['source'], audio_sha256='b' * 64)
    before = store.path.read_bytes()
    assert service.ledger('song', source) == dict(job_id='song', version=0, source_matches=True, operations=[])
    assert not service.ledger('song')['source_matches']
    assert store.path.read_bytes() == before and store.read('song')['document'] is None


@pytest.mark.parametrize('partial', [False, True])
def test_equivalence_requires_every_mapped_target_confirmed_including_already_same(setup, partial):
    s = setup; doc = deepcopy(s.document)
    # Source covers two complete bars, with same-root subdivisions in the first.
    s.request.update(source_range=dict(start=0., end=4.), target_range=dict(start=8., end=12.))
    doc['segments'][8]['status'] = 'pending'
    s.store.save('song', doc, 1); s.request['expected_version'] = 2
    operation = apply(s, selected=['t0'] if partial else ['t0', 't2'])['operation']
    assert operation['fully_equivalent'] is (not partial)
    # An edit beyond either mapped core does not break the accepted relationship.
    later = s.store.read('song')['document']; later['segments'][-1].update(root=5, status='confirmed')
    s.store.save('song', later, 3)
    entry = s.service.ledger('song', s.source)['operations'][0]
    assert entry['mapping_matches'] and entry['can_undo']
    assert entry['fully_equivalent'] is (not partial)


def test_failed_undo_rolls_back_ledger_root_and_history(setup):
    s = setup; operation = apply(s)['operation']
    before = s.store.read('song'); history = s.store.history('song')
    with sqlite3.connect(s.store.path) as db:
        db.execute("CREATE TRIGGER reject_undo BEFORE UPDATE ON root_practice BEGIN SELECT RAISE(ABORT, 'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError): undo(s, operation, 2)
    assert s.store.read('song') == before and s.store.history('song') == history
    entry = s.service.ledger('song', s.source)['operations'][0]
    assert entry['status'] == 'applied' and entry['undone_version'] is None and entry['can_undo']


async def test_http_preview_apply_ledger_undo_and_source_validation(tmp_path):
    directory = tmp_path / 'audio'; directory.mkdir(); (directory / 'analysis-source.wav').write_bytes(b'fixture audio')
    job = SimpleNamespace(id='song', status=JobStatus.COMPLETED, skip_seconds=42., analysis_seconds=16.,
                          score=SongScore.model_validate({'song': {'duration_seconds': 16., 'source_start_seconds': 42.}}))
    current = source_for_job(job, directory).model_dump(mode='json')
    doc = document({k: v for k, v in current.items() if k != 'audio_sha256'})
    store = RootPracticeStore(tmp_path / 'roots.sqlite3'); store.save('song', doc, 0)
    service = SimpleNamespace(get=lambda _: job, store=SimpleNamespace(job_dir=lambda _: directory))
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_root_practice_store] = lambda: store
    score_before = job.score.model_dump_json()
    base = '/api/v1/jobs/song/root-practice'
    request = dict(expected_version=1, fingerprint=current['fingerprint'], audio_sha256=current['audio_sha256'],
                   source_range=dict(start=0., end=8.), target_range=dict(start=8., end=16.), alignment_confirmed=True)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post(base + '/reuse-plan', json=request)
            assert response.status_code == 200
            preview = response.json(); assert store.read('song')['version'] == 1
            body = dict(request=preview['request'], plan_id=preview['plan_id'], selected_target_ids=['t0'])
            result = await client.post(base + '/reuse-apply', json=body)
            assert result.status_code == 200 and result.json()['snapshot']['version'] == 2
            operation = result.json()['operation']
            assert (await client.post(base + '/reuse-apply', json=body)).status_code == 409
            assert len((await client.get(base + '/reuse-ledger')).json()['operations']) == 1
            rollback = {k: current[k] for k in ('fingerprint', 'audio_sha256')}; rollback['expected_version'] = 2
            result = await client.post(base + f"/reuse-ledger/{operation['id']}/undo", json=rollback)
            assert result.status_code == 200 and result.json()['snapshot']['document'] == doc
            (directory / 'analysis-source.wav').write_bytes(b'different audio')
            assert (await client.post(base + '/reuse-plan', json={**request, 'expected_version': 3})).status_code == 409
            assert not (await client.get(base + '/reuse-ledger')).json()['source_matches']
            (directory / 'analysis-source.wav').unlink()
            listing = await client.get(base + '/reuse-ledger')
            assert listing.status_code == 200 and not listing.json()['source_matches']
            assert len(listing.json()['operations']) == 1
            assert not listing.json()['operations'][0]['can_undo']
        assert job.score.model_dump_json() == score_before
    finally:
        app.dependency_overrides.pop(get_job_service, None)
        app.dependency_overrides.pop(get_root_practice_store, None)
