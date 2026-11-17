from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import importlib.util
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from threading import Event

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.song_structure import SongStructureStore, source_for_job
from app.services.chord_practice import ChordPracticeStore, ChordDocument, ChordSave, ChordConflict, initial_document
from app.chord_practice_api import get_chord_practice_store, get_chord_structure_path


@pytest.fixture
def setup(tmp_path):
    audio = tmp_path / 'job'; audio.mkdir(); (audio / 'analysis-source.wav').write_bytes(b'original audio')
    score = SongScore.model_validate(dict(song=dict(duration_seconds=12., source_start_seconds=42.),
                                         chords=[dict(id='a', start=0., end=8., symbol='C'),
                                                 dict(id='b', start=10., end=12., symbol='G/B')]))
    job = SimpleNamespace(id='song', score=score, status=JobStatus.COMPLETED, skip_seconds=42., analysis_seconds=12.)
    source = source_for_job(job, audio).model_dump(mode='json')
    structure = SongStructureStore(tmp_path / 'structure.sqlite3')
    structure_doc = dict(schema_version=1, source=source, candidate_sha256=None,
                         sections=[dict(id='verse', start=0., end=4., label='verse', display_label='主歌'),
                                   dict(id='chorus', start=4., end=10., label='chorus', display_label='副歌'),
                                   dict(id='end', start=10., end=12., label='outro', display_label='尾奏')])
    structure.save('song', structure_doc, 0)
    store = ChordPracticeStore(tmp_path / 'chords.sqlite3')
    initial = initial_document(job, source)
    provider = lambda: (deepcopy(source), deepcopy(initial))
    return SimpleNamespace(store=store, structure=structure, structure_doc=structure_doc,
                           job=job, source=source, initial=initial, provider=provider, audio=audio)


def edited(s):
    doc = deepcopy(s.initial)
    first = doc['segments'][0]
    doc['segments'] = [{**first, 'id':'outside', 'end':4.},
                       {**first, 'id':'inside', 'start':4., 'symbol':'Am7/E', 'status':'confirmed'},
                       *doc['segments'][1:]]
    return doc


def save(s, doc=None, version=0, **overrides):
    body = ChordSave.model_validate(dict(expected_version=version, structure_version=1,
                                         section_id='chorus', document=doc or edited(s), **overrides))
    return s.store.save('song', body, s.provider, s.structure.path)


def test_initial_analysis_is_reference_only_fills_gaps_and_does_not_create_database(setup):
    s = setup
    assert [(r['start'], r['end'], r['original_symbol']) for r in s.initial['segments']] == [(0.,8.,'C'), (8.,10.,None), (10.,12.,'G/B')]
    assert all(r['symbol'] is None and r['status'] == 'pending' for r in s.initial['segments'])
    assert s.store.read('song')['document'] is None and s.store.history('song') == []
    assert not s.store.path.exists()


@pytest.mark.parametrize('kind', ['overlap', 'outside', 'negative', 'nan', 'zero'])
def test_bad_original_timing_never_guesses_a_draft(setup, kind):
    s = setup; score = s.job.score.model_dump(mode='json')
    row = score['chords'][1]
    if kind == 'overlap': row['start'] = 7.
    if kind == 'outside': row['end'] = 13.
    if kind == 'negative': score['chords'][0]['start'] = -1.
    if kind == 'nan': row['start'] = float('nan')
    if kind == 'zero': row['end'] = row['start']
    job = SimpleNamespace(**{**vars(s.job), 'score':SongScore.model_validate(score)})
    with pytest.raises(ValueError): initial_document(job, s.source)
    assert not s.store.path.exists()


@pytest.mark.parametrize('symbol', ['C', 'Am7', 'F#dim7', 'Bbmaj7/D', 'C7(b9)', 'Gsus4', 'N.C.'])
def test_common_chord_names_and_explicit_no_chord_are_supported(setup, symbol):
    doc = edited(setup); doc['segments'][1]['symbol'] = symbol
    assert ChordDocument.model_validate(doc).segments[1].symbol == symbol


@pytest.mark.parametrize('change', ['html', 'long', 'blank', 'pending_symbol', 'confirmed_null', 'gap', 'overlap', 'duplicate', 'nan', 'extra'])
def test_invalid_document_is_rejected(setup, change):
    doc = edited(setup); row = doc['segments'][1]
    if change == 'html': row['symbol'] = '<script>'
    if change == 'long': row['symbol'] = 'C' + 'm' * 80
    if change == 'blank': row['symbol'] = ''
    if change == 'pending_symbol': row['status'] = 'pending'
    if change == 'confirmed_null': row['symbol'] = None
    if change == 'gap': row['start'] = 4.1
    if change == 'overlap': row['start'] = 3.9
    if change == 'duplicate': row['id'] = 'outside'
    if change == 'nan': row['end'] = float('nan')
    if change == 'extra': doc['grid'] = {}
    with pytest.raises(ValueError): ChordDocument.model_validate(doc)


def test_save_only_changes_selected_section_preserves_reference_and_other_databases(setup):
    s = setup; structure_before = s.structure.path.read_bytes(); score_before = s.job.score.model_dump_json()
    result = save(s)
    assert result['version'] == 1 and result['document'] == edited(s)
    assert s.structure.path.read_bytes() == structure_before and s.job.score.model_dump_json() == score_before
    assert result['document']['segments'][0]['symbol'] is None
    next_doc = deepcopy(result['document']); next_doc['segments'][1].update(symbol='N.C.', status='confirmed')
    save(s, next_doc, 1)
    assert s.store.history('song')[0]['document'] == result['document']
    assert s.store.history('song')[0]['version'] == 1


@pytest.mark.parametrize('kind', ['outside', 'original_inside', 'original_outside', 'outside_split', 'outside_id', 'source', 'structure', 'section'])
def test_outside_or_metadata_changes_and_stale_structure_are_rejected(setup, kind):
    s = setup; doc = edited(s); body = dict(expected_version=0, structure_version=1, section_id='chorus', document=doc)
    if kind == 'outside': doc['segments'][0].update(symbol='F', status='confirmed')
    if kind == 'original_inside': doc['segments'][1]['original_symbol'] = 'Am'
    if kind == 'original_outside': doc['segments'][-1]['original_symbol'] = None
    if kind == 'outside_split':
        row = doc['segments'][0]; doc['segments'][:1] = [{**row, 'end':2.}, {**row, 'id':'outside2', 'start':2.}]
    if kind == 'outside_id': doc['segments'][-1]['id'] = 'unrelated-change'
    if kind == 'source': doc['source']['audio_sha256'] = 'f' * 64
    if kind == 'structure': body['structure_version'] = 0
    if kind == 'section': body['section_id'] = 'merged-away'
    before = s.structure.path.read_bytes()
    with pytest.raises((ValueError, ChordConflict)):
        s.store.save('song', ChordSave.model_validate(body), s.provider, s.structure.path)
    assert s.store.read('song')['version'] == 0 and s.store.history('song') == []
    assert s.structure.path.read_bytes() == before


def test_cas_two_tabs_have_one_winner_without_overwriting_the_other(setup):
    s = setup
    def attempt():
        try: return save(s)['version']
        except ChordConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _:attempt(), range(2)))
    assert sorted(map(str,results)) == ['1','conflict']
    assert s.store.read('song')['version'] == 1


def test_failed_save_rolls_back_history_and_preserves_current_document(setup):
    s = setup; before = save(s)
    with sqlite3.connect(s.store.path) as db:
        db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON chord_practice BEGIN SELECT RAISE(ABORT, 'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError): save(s, before['document'], 1)
    assert s.store.read('song') == before and not s.store.history('song')


def test_undo_can_restore_a_crossing_interval_without_touching_outside_harmony(setup):
    s = setup; save(s)
    result = save(s, s.initial, 1)
    assert result['document'] == s.initial and result['version'] == 2


@pytest.mark.parametrize('journal', ['delete', 'wal'])
def test_structure_merge_cannot_pass_between_version_check_and_chord_commit(setup, journal):
    s = setup
    with sqlite3.connect(s.structure.path) as db: db.execute(f'PRAGMA journal_mode={journal}')
    inside = Event(); release = Event(); attempting_merge = Event(); merged = Event()
    def provider():
        inside.set()
        assert release.wait(5)
        return s.provider()
    body = ChordSave(expected_version=0, structure_version=1, section_id='chorus', document=ChordDocument.model_validate(edited(s)))
    def change_structure():
        attempting_merge.set()
        next_doc = deepcopy(s.structure_doc); next_doc['sections'][1]['display_label'] = '使用者正在修改的副歌'
        result = s.structure.save('song', next_doc, 1)
        merged.set(); return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        saving = pool.submit(s.store.save, 'song', body, provider, s.structure.path)
        assert inside.wait(5)
        merging = pool.submit(change_structure)
        try:
            assert attempting_merge.wait(5)
            assert not merged.wait(.1)
        finally: release.set()
        assert saving.result()['version'] == 1
        assert merging.result()['version'] == 2
    assert s.structure.read('song')['document']['sections'][1]['display_label'] == '使用者正在修改的副歌'
    with pytest.raises(ChordConflict): save(s, edited(s), 1)


def test_no_chords_or_empty_rolled_back_database_remain_readable_without_schema_writes(setup):
    s = setup; s.job.score.chords = []
    doc = initial_document(s.job, s.source)
    assert len(doc['segments']) == 1 and doc['segments'][0]['original_symbol'] is None
    s.store.path.touch(); before = s.store.path.read_bytes()
    assert s.store.read('song')['document'] is None and s.store.history('song') == []
    assert s.store.path.read_bytes() == before


async def test_http_readonly_initial_save_conflict_history_and_missing_audio(setup):
    s = setup; service = SimpleNamespace(get=lambda _:s.job, store=SimpleNamespace(job_dir=lambda _:s.audio))
    app.dependency_overrides[get_job_service] = lambda:service
    app.dependency_overrides[get_chord_practice_store] = lambda:s.store
    app.dependency_overrides[get_chord_structure_path] = lambda:s.structure.path
    base = '/api/v1/jobs/song/chord-practice'
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            r = await client.get(base); assert r.status_code == 200
            first = r.json(); assert first['version'] == 0 and first['source_matches'] and first['current_source'] == s.source
            assert first['document'] == s.initial and not s.store.path.exists()
            body = dict(expected_version=0, structure_version=1, section_id='chorus', document=edited(s))
            r = await client.put(base, json=body); assert r.status_code == 200 and r.json()['version'] == 1
            assert (await client.put(base, json=body)).status_code == 409
            # UI undo overlays only the locked section's old decisions, keeping
            # the current boundary cuts and every outside ID untouched.
            body['expected_version'] = 1
            body['document']['segments'][1].update(symbol=None, status='pending')
            r = await client.put(base, json=body)
            assert r.status_code == 200 and r.json()['version'] == 2
            assert r.json()['document']['segments'][0] == edited(s)['segments'][0]
            assert r.json()['document']['segments'][-1] == s.initial['segments'][-1]
            body['expected_version'] = 2
            s.structure.save('song', s.structure_doc, 1)
            assert (await client.put(base, json=body)).status_code == 409
            history = (await client.get(base+'/history')).json()
            assert len(history) == 1 and history[0]['document'] == edited(s)
            (s.audio/'analysis-source.wav').unlink()
            r = await client.get(base); assert r.status_code == 200
            assert not r.json()['source_matches'] and r.json()['document'] == body['document'] and r.json()['source_error']
            assert (await client.put(base, json=body)).status_code == 404
    finally:
        for dependency in (get_job_service,get_chord_practice_store,get_chord_structure_path):
            app.dependency_overrides.pop(dependency,None)


async def test_browser_fixture_uses_only_temporary_stores_and_starts_without_chord_database(tmp_path):
    path = Path(__file__).resolve().parents[1] / 'scripts/serve_chord_practice_fixture.py'
    spec = importlib.util.spec_from_file_location('chord_browser_fixture', path)
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    api = fixture.create_fixture(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=api), base_url='http://test') as client:
        response = await client.get('/api/v1/jobs/fixture-song/chord-practice')
        assert response.status_code == 200 and response.json()['source_matches']
        assert [s['original_symbol'] for s in response.json()['document']['segments']] == ['C', 'G']
        assert not (tmp_path/'chord-practice.sqlite3').exists()
        assert all((await client.get('/fixture/invariants')).json().values())
