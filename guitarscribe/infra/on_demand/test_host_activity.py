import importlib.util
import json
import os
from pathlib import Path
import sqlite3

spec = importlib.util.spec_from_file_location('host_activity', Path(__file__).with_name('host_activity.py'))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def test_polling_does_not_keep_an_abandoned_tab_alive():
    assert not host.user_activity('GET', '/backend/api/v1/jobs/song/song-structure/analysis')
    assert not host.user_activity('GET', '/backend/health')
    assert host.user_activity('PUT', '/backend/api/v1/jobs/song/chord-practice')
    assert host.user_activity('GET', '/backend/api/v1/jobs/song/song-structure/audio')


def test_idle_shutdown_waits_for_analysis_and_fails_closed_on_corruption(tmp_path):
    activity = tmp_path / 'activity'
    activity.touch()
    os.utime(activity, (100, 100))
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    with sqlite3.connect(jobs / 'jobs.sqlite3') as db:
        db.execute('CREATE TABLE jobs(payload TEXT)')
        db.execute('INSERT INTO jobs VALUES (?)', (json.dumps({'status': 'chord_analysis'}),))
    assert not host.idle_due(tmp_path, activity, now=5000, uptime=5000)
    with sqlite3.connect(jobs / 'jobs.sqlite3') as db:
        db.execute('UPDATE jobs SET payload=?', (json.dumps({'status': 'completed'}),))
    assert host.idle_due(tmp_path, activity, now=5000, uptime=5000)
    with sqlite3.connect(jobs / 'jobs.sqlite3') as db:
        db.execute("UPDATE jobs SET payload='broken'")
    assert not host.idle_due(tmp_path, activity, now=5000, uptime=5000)


def test_structure_analysis_blocks_idle_and_boot_grace_is_preserved(tmp_path):
    activity = tmp_path / 'activity'; activity.touch(); os.utime(activity, (100, 100))
    state = tmp_path / 'structure-analysis/song/state.json'
    state.parent.mkdir(parents=True)
    state.write_text('{"state":"running"}')
    assert not host.idle_due(tmp_path, activity, now=5000, uptime=5000)
    state.write_text('{"state":"ready"}')
    assert not host.idle_due(tmp_path, activity, now=5000, uptime=60)
    assert host.idle_due(tmp_path, activity, now=5000, uptime=5000)


def test_late_analysis_guard_covers_all_heavy_entries():
    for path in ('/backend/api/v1/jobs', '/backend/api/v1/youtube-jobs',
                 '/backend/api/v1/jobs/song/song-structure/analysis', '/backend/api/v1/jobs/song/root-candidates'):
        assert host.analysis_request('POST', path)
        assert not host.analysis_request('GET', path)
    assert not host.analysis_request('PUT', '/backend/api/v1/jobs/song/song-structure')


def test_library_restores_latest_server_revision_on_a_new_device(tmp_path):
    jobs = tmp_path / 'jobs'; jobs.mkdir()
    revisions = tmp_path / 'revisions'; revisions.mkdir()
    with sqlite3.connect(jobs / 'jobs.sqlite3') as db:
        db.execute('CREATE TABLE jobs(payload TEXT, updated_at TEXT)')
        db.execute('INSERT INTO jobs VALUES (?,?)', (json.dumps(dict(id='song', status='completed', score={'song': {'title': '我的歌'}})), '2026-11-20'))
        db.executemany('INSERT INTO jobs VALUES (?,?)', [(json.dumps(dict(id=f'failed-{i}', status='failed')), '2026-11-21') for i in range(101)])
    with sqlite3.connect(revisions / 'guitarscribe.sqlite3') as db:
        db.execute('CREATE TABLE revisions(id TEXT,payload TEXT,created_at TEXT)')
        score = json.dumps({'provenance': {'parameters': {'analysis_source_job_id': 'song'}}})
        db.executemany('INSERT INTO revisions VALUES (?,?,?)', [('old', score, '2026-11-01'), ('new', score, '2026-11-20')])
    assert host.song_library(tmp_path) == [dict(job_id='song', title='我的歌', revision_id='new')]


def test_new_boot_recovers_only_operational_state_and_never_reuses_old_pid(tmp_path):
    state = tmp_path / 'structure-analysis/song/state.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(dict(state='running', process={'pid':1}, owner={'pid':2}, unit='old.scope')))
    draft = tmp_path / 'song-structure.sqlite3'; draft.write_bytes(b'untouched user progress')
    assert host.recover_boot_state(tmp_path, 'new-boot')
    value = json.loads(state.read_text())
    assert value['state'] == 'interrupted' and value['process'] is None and value['owner'] is None
    assert draft.read_bytes() == b'untouched user progress'
    state.write_text('{"state":"running"}')
    assert not host.recover_boot_state(tmp_path, 'new-boot')
    assert json.loads(state.read_text())['state'] == 'running'
