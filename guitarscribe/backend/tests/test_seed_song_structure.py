"""Seeding is a source-checked, create-only operation, including on reruns."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from app.evaluation.song_structure import summarize_candidate
from app.evaluation.song_structure_feedback import apply_feedback, candidate_digest
from app.services.song_structure import StructureDocument

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'seed_song_structure.py'
spec = importlib.util.spec_from_file_location('seed_song_structure', SCRIPT)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def fixture(job='song', reviewed=True):
    labels = ['intro', 'intro', 'verse', 'verse', 'chorus', 'solo', 'verse',
              'verse', 'verse', 'chorus', 'chorus', 'chorus', 'outro', 'outro']
    original = summarize_candidate([dict(start=i, end=i+1, label=label)
                                    for i, label in enumerate(labels)], 14.)
    original.update(job=job, fingerprint='a' * 64, title=job, source_start=42., duration=14.)
    original['sections'][-1]['model_end'] = 14.01
    source = dict(job_id=job, fingerprint='a' * 64, audio_sha256='b' * 64,
                  duration=14.000001, source_start=42.)
    feedback = dict(schema_version=1, job=job, audio_sha256=source['audio_sha256'],
                    candidate_sha256=candidate_digest(original), reviewer='user', date='2026-11-17',
                    independent_of_candidate=False,
                    operations=[dict(kind='merge', ids=['section-1', 'section-2'], label='intro'),
                                dict(kind='rename', ids=['section-8', 'section-9'], label='chorus'),
                                dict(kind='rename', ids=['section-12'], label='closing', similar_to='verse'),
                                dict(kind='confirm_name', ids=['section-13', 'section-14'], label='outro')])
    candidate = apply_feedback(original, feedback, source['audio_sha256']) if reviewed else deepcopy(original)
    return candidate, original, source


def test_conversion_preserves_feedback_originals_and_only_adjusts_editable_tail():
    candidate, original, source = fixture()
    before = deepcopy((candidate, original, source))
    result = seed.document_for(candidate, original, source)
    StructureDocument.model_validate(result)
    assert len(result['sections']) == 13
    assert result['candidate_sha256'] == candidate_digest(original)
    first = result['sections'][0]
    assert first['id'] == 'section-1+section-2' and first['end'] == 2
    assert [m['original_number'] for m in first['model_sections']] == [1, 2]
    assert first['name_review_status'] == 'user_confirmed'
    by_original = {m['original_number']: section for section in result['sections'] for m in section['model_sections']}
    assert by_original[8]['id'] != by_original[9]['id']
    for n in (8, 9):
        assert by_original[n]['label'] == 'chorus'
        assert by_original[n]['model_sections'][0]['label'] == 'verse'
    assert by_original[12]['label'] == 'closing'
    assert by_original[12]['name_review_status'] == 'tentative'
    assert by_original[12]['model_sections'][0]['label'] == 'chorus'
    assert by_original[13]['id'] != by_original[14]['id']
    assert all(s['boundary_review_status'] == 'unreviewed' for s in result['sections'])
    assert result['sections'][-1]['end'] == source['duration']
    assert result['sections'][-1]['model_sections'][0]['end'] == 14.
    assert result['sections'][-1]['model_sections'][0]['model_end'] == 14.01
    assert (candidate, original, source) == before


def test_unreviewed_candidate_is_not_promoted_to_confirmed():
    candidate, original, source = fixture(reviewed=False)
    result = seed.document_for(candidate, original, source)
    assert len(result['sections']) == 14
    assert all(s['name_review_status'] == s['boundary_review_status'] == 'unreviewed'
               for s in result['sections'])
    assert [s['model_sections'][0]['original_number'] for s in result['sections']] == list(range(1, 15))


@pytest.mark.parametrize('change', ['job', 'fingerprint', 'duration', 'offset', 'audio',
                                   'feedback_hash', 'edited_label', 'edited_original', 'other_original'])
def test_conversion_rejects_mismatched_source_or_unbound_review_data(change):
    candidate, original, source = fixture()
    if change == 'job': source['job_id'] = 'other'
    if change == 'fingerprint': source['fingerprint'] = 'c' * 64
    if change == 'duration': source['duration'] += 1
    if change == 'offset': source['source_start'] = 0.
    if change == 'audio': source['audio_sha256'] = 'c' * 64
    if change == 'feedback_hash': candidate['feedback']['candidate_sha256'] = 'c' * 64
    if change == 'edited_label': candidate['sections'][2]['display_label'] = 'Unrecorded revision'
    if change == 'edited_original': candidate['sections'][0]['model_sections'][0]['label'] = 'verse'
    if change == 'other_original': original['job'] = 'other'
    with pytest.raises(ValueError): seed.document_for(candidate, original, source)


class FakeAPI:
    def __init__(self, sources):
        self.snapshots = {s['job_id']: dict(job_id=s['job_id'], document=None, version=0,
                                          current_source=s, source_matches=True, source_error=None,
                                          updated_at=None) for s in sources}
        self.calls = []
        self.race = False
        self.bad_response = False

    def __call__(self, job, payload=None):
        self.calls.append((job, deepcopy(payload)))
        state = self.snapshots[job]
        if payload is not None:
            if self.race:
                state['version'] = 1
                state['document'] = {'human': 'concurrent work'}
            if payload['expected_version'] != state['version']:
                raise HTTPError('http://localhost/test', 409, 'conflict', {}, None)
            assert state['document'] is None
            state.update(document=deepcopy(payload['document']), version=1)
        result = deepcopy(state)
        if payload is not None and self.bad_response: result['version'] = 99
        return result

    @property
    def writes(self):
        return [c for c in self.calls if c[1] is not None]


def inputs(jobs=('song',)):
    fixtures = [fixture(job) for job in jobs]
    candidates = [x[0] for x in fixtures]
    runs = {x[0]['job']: (x[1], {'source': {'audio_sha256': x[2]['audio_sha256']}}) for x in fixtures}
    return candidates, runs, FakeAPI([x[2] for x in fixtures])


def test_create_once_and_idempotent_rerun_retains_server_version(tmp_path):
    candidates, runs, api = inputs()
    first = seed.seed_candidates(candidates, runs, api, tmp_path / 'first')
    second = seed.seed_candidates(candidates, runs, api, tmp_path / 'second')
    assert first == [dict(job='song', version=1, section_count=13, created=True)]
    assert second == [dict(job='song', version=1, section_count=13, created=False)]
    assert len(api.writes) == 1 and api.writes[0][1]['expected_version'] == 0
    assert json.loads((tmp_path / 'first/song-before.json').read_text())['document'] is None
    assert json.loads((tmp_path / 'second/summary.json').read_text()) == second


@pytest.mark.parametrize('fault', ['human_document', 'source_mismatch', 'wrong_audio',
                                  'missing_source', 'nonzero_empty_version', 'duplicate_job'])
def test_preflight_rejects_every_conflict_before_any_song_is_written(tmp_path, fault):
    candidates, runs, api = inputs(('first', 'second'))
    last = api.snapshots['second']
    if fault == 'human_document':
        last['document'] = seed.document_for(candidates[1], runs['second'][0], last['current_source'])
        last['document']['sections'][0]['display_label'] = 'Human edit'
        last['version'] = 4
    if fault == 'source_mismatch': last['source_matches'] = False
    if fault == 'wrong_audio': last['current_source']['audio_sha256'] = 'c' * 64
    if fault == 'missing_source': last['current_source'] = None
    if fault == 'nonzero_empty_version': last['version'] = 4
    if fault == 'duplicate_job': candidates.append(deepcopy(candidates[0]))
    before = deepcopy(api.snapshots)
    with pytest.raises(ValueError): seed.seed_candidates(candidates, runs, api, tmp_path / 'out')
    assert not api.writes and api.snapshots == before
    assert not (tmp_path / 'out').exists()


def test_cas_conflict_after_preflight_never_retries_or_overwrites(tmp_path):
    candidates, runs, api = inputs(); api.race = True
    with pytest.raises(HTTPError) as error:
        seed.seed_candidates(candidates, runs, api, tmp_path / 'out')
    assert error.value.code == 409 and len(api.writes) == 1
    assert api.snapshots['song']['document'] == {'human': 'concurrent work'}
    assert (tmp_path / 'out/song-before.json').exists()
    assert not (tmp_path / 'out/song-saved.json').exists()


def test_existing_output_folder_is_not_overwritten_and_invalid_reply_is_not_reported_as_success(tmp_path):
    candidates, runs, api = inputs()
    with pytest.raises(FileExistsError): seed.seed_candidates(candidates, runs, api, tmp_path)
    assert not api.writes
    api.bad_response = True
    with pytest.raises(ValueError): seed.seed_candidates(candidates, runs, api, tmp_path / 'out')
    assert not (tmp_path / 'out/summary.json').exists()


def test_cli_writes_only_structure_endpoint_and_repeated_run_is_read_only(tmp_path, monkeypatch, capsys):
    candidates, runs, api = inputs()
    review = tmp_path / 'review.json'; review.write_text(json.dumps(candidates))
    run = tmp_path / 'run'; run.mkdir()
    (run / 'manifest.json').write_text(json.dumps(runs['song'][1]))
    access = tmp_path / 'test-access.json'
    access.write_text(json.dumps(dict(username='test', password='fixture')))
    monkeypatch.setattr(seed, 'load_ready_candidate', lambda _: deepcopy(runs['song'][0]))
    methods = []
    def urlopen(request, timeout):
        assert request.full_url == 'http://127.0.0.1:5273/backend/api/v1/jobs/song/song-structure'
        assert request.get_header('Authorization').startswith('Basic ')
        assert timeout == 30
        methods.append(request.get_method())
        return io.StringIO(json.dumps(api('song', json.loads(request.data) if request.data else None)))
    monkeypatch.setattr(seed, 'urlopen', urlopen)
    for name in ('first', 'repeat'):
        monkeypatch.setattr(seed.sys, 'argv', [str(SCRIPT), '--review-data', str(review),
                           '--run', str(run), '--access-file', str(access), '--out', str(tmp_path / name)])
        seed.main()
    assert methods == ['GET', 'PUT', 'GET']
    assert len(api.writes) == 1
    assert 'fixture' not in capsys.readouterr().out
