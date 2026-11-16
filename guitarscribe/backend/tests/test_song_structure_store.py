"""Structure edits have their own source-bound CAS history, never root/Score writes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import sqlite3
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api import app, get_job_service
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.song_structure_api import get_song_structure_store
from app.services.song_structure import (
    StructureConflict, StructureDocument, SongStructureStore, source_for_job,
)


def document():
    return {
        'schema_version': 1,
        'source': {'job_id': 'song', 'fingerprint': 'a' * 64, 'audio_sha256': 'b' * 64,
                   'duration': 8., 'source_start': 42.},
        'candidate_sha256': 'c' * 64,
        'sections': [
            {'id': 'section-1+section-2', 'start': 0., 'end': 4., 'label': 'intro',
             'display_label': '前奏', 'name_review_status': 'user_confirmed',
             'boundary_review_status': 'unreviewed', 'note': '',
             'model_sections': [
                 {'id': 'section-1', 'start': 0., 'end': 1., 'label': 'intro',
                  'model_end': 1., 'original_number': 1},
                 {'id': 'section-2', 'start': 1., 'end': 4., 'label': 'intro',
                  'model_end': 4., 'original_number': 2}]},
            {'id': 'section-3', 'start': 4., 'end': 8., 'label': 'closing',
             'display_label': '收尾段（較接近主歌）', 'name_review_status': 'tentative',
             'boundary_review_status': 'unreviewed', 'note': '使用者：較接近主歌',
             'model_sections': [{'id': 'section-3', 'start': 4., 'end': 8.,
                                 'label': 'chorus', 'model_end': 8.01, 'original_number': 3}]},
        ],
    }


def test_document_preserves_human_and_original_labels_and_distinct_confirmations():
    d = StructureDocument.model_validate(document()).model_dump(mode='json')
    assert d == document()
    assert d['sections'][1]['label'] == 'closing'
    assert d['sections'][1]['model_sections'][0]['label'] == 'chorus'
    assert d['sections'][0]['name_review_status'] == 'user_confirmed'
    assert d['sections'][0]['boundary_review_status'] == 'unreviewed'


@pytest.mark.parametrize('fault', [
    'gap', 'overlap', 'duplicate', 'nan', 'infinity', 'zero', 'negative', 'tail',
    'empty', 'unknown_field', 'bad_hash', 'invalid_status', 'model_outside_source',
])
def test_invalid_structure_rejected(fault):
    d = document()
    if fault == 'gap': d['sections'][1]['start'] = 4.1
    if fault == 'overlap': d['sections'][1]['start'] = 3.9
    if fault == 'duplicate': d['sections'][1]['id'] = d['sections'][0]['id']
    if fault == 'nan': d['sections'][0]['end'] = float('nan')
    if fault == 'infinity': d['source']['duration'] = float('inf')
    if fault == 'zero': d['sections'][0]['end'] = 0
    if fault == 'negative': d['sections'][0]['start'] = -1
    if fault == 'tail': d['sections'][-1]['end'] = 8.1
    if fault == 'empty': d['sections'] = []
    if fault == 'unknown_field': d['sections'][0]['root'] = 4
    if fault == 'bad_hash': d['source']['audio_sha256'] = 'wrong'
    if fault == 'invalid_status': d['sections'][0]['boundary_review_status'] = 'user_corrected'
    if fault == 'model_outside_source': d['sections'][1]['model_sections'][0]['end'] = 9
    with pytest.raises(ValidationError): StructureDocument.model_validate(d)


@pytest.mark.parametrize('fault', ['blank', 'long_label', 'long_note', 'invalid_id', 'missing_candidate',
                                 'repeated_original', 'conflicting_original', 'string_time', 'bool_time'])
def test_document_limits_and_model_provenance_are_validated(fault):
    d = document()
    if fault == 'blank': d['sections'][0]['display_label'] = ' \n '
    if fault == 'long_label': d['sections'][0]['display_label'] = '名' * 121
    if fault == 'long_note': d['sections'][0]['note'] = '字' * 2001
    if fault == 'invalid_id': d['sections'][0]['id'] = '../invalid'
    if fault == 'missing_candidate': d['candidate_sha256'] = None
    if fault == 'repeated_original': d['sections'][0]['model_sections'] *= 2
    if fault == 'conflicting_original':
        original = deepcopy(d['sections'][0]['model_sections'][0]); original['label'] = 'chorus'
        d['sections'][1]['model_sections'].append(original)
    if fault == 'string_time': d['sections'][0]['end'] = '4'
    if fault == 'bool_time': d['sections'][0]['start'] = False
    with pytest.raises(ValidationError): StructureDocument.model_validate(d)


def test_split_sections_can_reference_the_same_original_and_manual_documents_have_no_model():
    d = document()
    first = deepcopy(d['sections'][0]); first.update(id='new-left', end=2.)
    second = deepcopy(d['sections'][0]); second.update(id='new-right', start=2.)
    d['sections'] = [first, second, d['sections'][1]]
    assert len(StructureDocument.model_validate(d).sections) == 3
    manual = {'schema_version': 1, 'source': d['source'], 'sections': [
        {'id': 'manual', 'start': 0, 'end': 8, 'label': 'unknown', 'display_label': '未判定'}]}
    result = StructureDocument.model_validate(manual)
    assert result.candidate_sha256 is None and result.sections[0].model_sections == []


def test_full_and_zero_offset_cropped_sources_are_distinct_and_ambiguous_audio_is_rejected(tmp_path):
    job = SimpleNamespace(id='song', skip_seconds=0, analysis_seconds=None,
                          score=SongScore.model_validate({'song': {'duration_seconds': 8}}))
    (tmp_path / 'input.wav').write_bytes(b'full')
    (tmp_path / 'analysis-source.wav').write_bytes(b'crop')
    assert source_for_job(job, tmp_path).audio_sha256 == hashlib.sha256(b'full').hexdigest()
    job.analysis_seconds = 8
    assert source_for_job(job, tmp_path).audio_sha256 == hashlib.sha256(b'crop').hexdigest()
    job.analysis_seconds = None
    (tmp_path / 'input.mp3').write_bytes(b'other')
    with pytest.raises(StructureConflict): source_for_job(job, tmp_path)


def test_first_read_is_empty_and_cas_versions_archive_restore_without_mutating_input(tmp_path):
    store = SongStructureStore(tmp_path / 'structure.sqlite3')
    assert store.read('song') == dict(job_id='song', version=0, document=None, updated_at=None)
    original = document(); before = deepcopy(original)
    first = store.save('song', original, 0)
    revised = deepcopy(original); revised['sections'][1]['name_review_status'] = 'user_confirmed'
    second = store.save('song', revised, 1)
    assert first['version'] == 1 and second['version'] == 2 and original == before
    history = store.history('song')
    assert history == [dict(version=1, document=original, updated_at=first['updated_at'])]
    # An import/restore is a new save with the current version, not a version rewind.
    restored = store.save('song', history[0]['document'], 2)
    assert restored['version'] == 3 and restored['document'] == original
    assert [v['version'] for v in store.history('song')] == [2, 1]
    assert SongStructureStore(store.path).read('song') == restored


def test_stale_or_different_source_saves_never_change_document_or_history(tmp_path):
    store = SongStructureStore(tmp_path / 'structure.sqlite3')
    d = document(); first = store.save('song', d, 0)
    for field, value in [('audio_sha256', 'd' * 64), ('fingerprint', 'e' * 64), ('source_start', 0.)]:
        changed = deepcopy(d); changed['source'][field] = value
        with pytest.raises(StructureConflict): store.save('song', changed, 1)
    with pytest.raises(StructureConflict): store.save('song', d, 0)
    with pytest.raises(ValueError): store.save('other', d, 0)
    assert store.read('song') == first and store.history('song') == []


def test_concurrent_cas_only_one_writer_wins(tmp_path):
    store = SongStructureStore(tmp_path / 'structure.sqlite3')
    store.save('song', document(), 0)
    def save(note):
        d = document(); d['sections'][0]['note'] = note
        try: return store.save('song', d, 1)['version']
        except StructureConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['left', 'right']))
    assert sorted(map(str, results)) == ['2', 'conflict']
    assert store.read('song')['version'] == 2 and len(store.history('song')) == 1


def test_failed_write_rolls_back_history_and_version_together(tmp_path):
    store = SongStructureStore(tmp_path / 'structure.sqlite3')
    saved = store.save('song', document(), 0)
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON song_structure "
                   "BEGIN SELECT RAISE(ABORT, 'simulated disk write rejection'); END")
    with pytest.raises(sqlite3.IntegrityError): store.save('song', document(), 1)
    assert store.read('song') == saved and store.history('song') == []
    with sqlite3.connect(store.path) as db:
        db.execute('DROP TRIGGER reject_update')
    assert store.save('song', document(), 1)['version'] == 2
    assert len(store.history('song')) == 1


@pytest.fixture
def api_setup(tmp_path):
    source = SimpleNamespace(id='song', status=JobStatus.COMPLETED, skip_seconds=42.,
                             analysis_seconds=8., score=SongScore.model_validate({
                                 'song': {'duration_seconds': 8., 'source_start_seconds': 42.}}))
    (tmp_path / 'input.wav').write_bytes(b'full recording')
    (tmp_path / 'analysis-source.wav').write_bytes(b'cropped recording')
    # Separate root store is deliberately pre-populated; these endpoints must never touch it.
    from app.services.root_practice import RootPracticeStore, initial_document
    root_store = RootPracticeStore(tmp_path / 'root-practice.sqlite3')
    root_store.save('song', initial_document(source), 0)
    root_before = (tmp_path / 'root-practice.sqlite3').read_bytes()
    score_before = source.score.model_dump_json()
    store = SongStructureStore(tmp_path / 'song-structure.sqlite3')
    def get(identifier):
        if identifier != source.id: raise FileNotFoundError()
        return source
    service = SimpleNamespace(get=get, store=SimpleNamespace(job_dir=lambda _: tmp_path))
    app.dependency_overrides[get_job_service] = lambda: service
    app.dependency_overrides[get_song_structure_store] = lambda: store
    yield SimpleNamespace(job=source, service=service, store=store, directory=tmp_path)
    app.dependency_overrides.pop(get_job_service, None)
    app.dependency_overrides.pop(get_song_structure_store, None)
    assert source.score.model_dump_json() == score_before
    assert (tmp_path / 'root-practice.sqlite3').read_bytes() == root_before


URL = '/api/v1/jobs/song/song-structure'


async def initial(client):
    r = await client.get(URL)
    assert r.status_code == 200
    snapshot = r.json()
    assert snapshot['document'] is None and snapshot['version'] == 0
    assert snapshot['source_matches'] and snapshot['source_error'] is None
    assert snapshot['current_source']['audio_sha256'] == hashlib.sha256(b'cropped recording').hexdigest()
    d = document(); d['source'] = snapshot['current_source']
    return d


async def test_api_empty_create_export_import_history_and_conflict(api_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        assert (await c.get(URL + '/export')).status_code == 404
        d = await initial(c)
        response = await c.put(URL, json=dict(expected_version=0, document=d))
        assert response.status_code == 200
        saved = response.json(); assert saved['document'] == d and saved['source_matches']
        exported = await c.get(URL + '/export')
        assert exported.status_code == 200 and exported.json() == d
        edited = deepcopy(d); edited['sections'][1]['label'] = 'custom'
        edited['sections'][1]['display_label'] = '我的收尾'
        assert (await c.put(URL, json=dict(expected_version=1, document=edited))).status_code == 200
        assert (await c.put(URL, json=dict(expected_version=1, document=d))).status_code == 409
        assert (await c.get(URL)).json()['document'] == edited
        history = (await c.get(URL + '/history')).json()
        assert history[0]['document'] == d and history[0]['version'] == 1
        assert (await c.put(URL, json=dict(expected_version=2, document=exported.json()))).json()['version'] == 3
        invalid = deepcopy(d); invalid['sections'][0]['end'] = 4.5
        assert (await c.put(URL, json=dict(expected_version=3, document=invalid))).status_code == 422


@pytest.mark.parametrize('change', ['audio', 'fingerprint', 'missing_audio', 'missing_job'])
async def test_api_stale_source_keeps_exportable_draft_but_rejects_saving(api_setup, change):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        d = await initial(c)
        assert (await c.put(URL, json=dict(expected_version=0, document=d))).status_code == 200
        if change == 'audio': (api_setup.directory / 'analysis-source.wav').write_bytes(b'replaced same job')
        if change == 'fingerprint':
            # Alter provenance only, not the actual Score object used in the protection assertion.
            changed = deepcopy(api_setup.job)
            changed.score.provenance.chord_engine = 'updated'
            api_setup.service.get = lambda _: changed
        if change == 'missing_audio': (api_setup.directory / 'analysis-source.wav').unlink()
        if change == 'missing_job':
            def missing(_): raise FileNotFoundError()
            api_setup.service.get = missing
        r = await c.get(URL); assert r.status_code == 200
        assert r.json()['document'] == d and not r.json()['source_matches'] and r.json()['source_error']
        assert (await c.get(URL + '/export')).json() == d
        rejected = await c.put(URL, json=dict(expected_version=1, document=d))
        assert rejected.status_code == (404 if change.startswith('missing') else 409)
        assert api_setup.store.read('song')['version'] == 1 and api_setup.store.history('song') == []


async def test_first_save_cannot_forge_source_or_import_another_song(api_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        d = await initial(c)
        for field, value in [('audio_sha256', '0' * 64), ('job_id', 'another'), ('source_start', 0.)]:
            bad = deepcopy(d); bad['source'][field] = value
            assert (await c.put(URL, json=dict(expected_version=0, document=bad))).status_code == 409
        assert api_setup.store.read('song')['version'] == 0


async def test_api_missing_new_job_and_incomplete_analysis_are_not_initialized(api_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        assert (await c.get('/api/v1/jobs/missing/song-structure')).status_code == 404
        api_setup.job.status = JobStatus.QUEUED
        assert (await c.get(URL)).status_code == 409
        assert api_setup.store.read('song')['document'] is None


@pytest.mark.parametrize('skip,limit,payload', [
    (42., 8., b'cropped recording'),
    (0., 8., b'cropped recording'),
    (0., None, b'full recording'),
])
async def test_structure_audio_returns_bound_local_source_and_byte_ranges(api_setup, skip, limit, payload):
    job = deepcopy(api_setup.job)
    job.skip_seconds, job.analysis_seconds = skip, limit
    api_setup.service.get = lambda _: job
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        source = (await c.get(URL)).json()['current_source']
        params = {key: source[key] for key in ('fingerprint', 'audio_sha256')}
        response = await c.get(URL + '/audio', params=params)
        assert response.status_code == 200 and response.content == payload
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['accept-ranges'] == 'bytes'
        partial = await c.get(URL + '/audio', params=params, headers={'Range': 'bytes=2-6'})
        assert partial.status_code == 206 and partial.content == payload[2:7]
        assert partial.headers['content-range'] == f'bytes 2-6/{len(payload)}'
        suffix = await c.get(URL + '/audio', params=params, headers={'Range': 'bytes=-4'})
        assert suffix.status_code == 206 and suffix.content == payload[-4:]
        assert (await c.get(URL + '/audio', params=params, headers={'Range': 'bytes=999-'})).status_code == 416
        assert api_setup.store.read('song')['version'] == 0


@pytest.mark.parametrize('change', ['audio', 'fingerprint', 'missing_audio', 'missing_job'])
async def test_structure_audio_revalidates_source_on_every_request(api_setup, change):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        source = (await c.get(URL)).json()['current_source']
        params = {key: source[key] for key in ('fingerprint', 'audio_sha256')}
        assert (await c.get(URL + '/audio', params=params)).status_code == 200
        if change == 'audio':
            (api_setup.directory / 'analysis-source.wav').write_bytes(b'replaced recording')
            current = (await c.get(URL)).json()['current_source']
            assert current['fingerprint'] == source['fingerprint']
            assert current['audio_sha256'] != source['audio_sha256']
        if change == 'fingerprint':
            changed = deepcopy(api_setup.job)
            changed.score.provenance.chord_engine = 'updated'
            api_setup.service.get = lambda _: changed
        if change == 'missing_audio':
            (api_setup.directory / 'analysis-source.wav').unlink()
        if change == 'missing_job':
            def missing(_): raise FileNotFoundError()
            api_setup.service.get = missing
        response = await c.get(URL + '/audio', params=params, headers={'Range': 'bytes=0-4'})
        assert response.status_code == (404 if change.startswith('missing') else 409)
        assert api_setup.store.read('song')['version'] == 0


async def test_structure_audio_requires_both_valid_digests(api_setup):
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        source = (await c.get(URL)).json()['current_source']
        params = {key: source[key] for key in ('fingerprint', 'audio_sha256')}
        assert (await c.get(URL + '/audio')).status_code == 422
        for key in params:
            assert (await c.get(URL + '/audio', params={**params, key: 'bad'})).status_code == 422
            assert (await c.get(URL + '/audio', params={**params, key: '0' * 64})).status_code == 409
