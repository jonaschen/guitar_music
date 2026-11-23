import sqlite3
from pathlib import Path

import pytest

from release_workspace import snapshot, verify_preserved


@pytest.fixture
def work(tmp_path):
    root = tmp_path / 'work'; (root / 'jobs/song').mkdir(parents=True)
    (root / 'jobs/song/input.wav').write_bytes(b'private source')
    with sqlite3.connect(root / 'jobs/jobs.sqlite3') as db:
        db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, payload TEXT)')
        db.execute('INSERT INTO jobs VALUES (?, ?)', ('song', '已保存的主歌'))
    return root


def add_retry(work):
    with sqlite3.connect(work / 'jobs/jobs.sqlite3') as db:
        db.execute('CREATE TABLE job_retries (parent_id TEXT PRIMARY KEY, child_id TEXT NOT NULL)')


def test_empty_retry_schema_requires_explicit_exception(work):
    before = snapshot(work); add_retry(work); after = snapshot(work)
    with pytest.raises(ValueError): verify_preserved(before, after)
    assert verify_preserved(before, after, allow_retry_schema=True) == ['jobs/jobs.sqlite3:job_retries']


@pytest.mark.parametrize('mutation', [
    "UPDATE jobs SET payload='overwritten'",
    "DELETE FROM jobs",
    "INSERT INTO job_retries VALUES ('song', 'unexpected-child')",
    "CREATE TRIGGER surprise AFTER INSERT ON jobs BEGIN DELETE FROM jobs; END",
    "CREATE TABLE other (value TEXT)",
    "CREATE INDEX extra ON job_retries(child_id)",
])
def test_schema_exception_does_not_hide_data_or_other_schema_changes(work, mutation):
    before = snapshot(work); add_retry(work)
    with sqlite3.connect(work / 'jobs/jobs.sqlite3') as db: db.execute(mutation)
    with pytest.raises(ValueError): verify_preserved(before, snapshot(work), allow_retry_schema=True)


def test_existing_retry_mapping_is_preserved_and_wal_rows_are_visible(work):
    add_retry(work)
    with sqlite3.connect(work / 'jobs/jobs.sqlite3') as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("INSERT INTO job_retries VALUES ('song', 'child')"); db.commit()
        before = snapshot(work)
        assert verify_preserved(before, snapshot(work), allow_retry_schema=True) == []
        db.execute("UPDATE job_retries SET child_id='other'"); db.commit()
        with pytest.raises(ValueError): verify_preserved(before, snapshot(work), allow_retry_schema=True)


def test_audio_changes_and_missing_databases_are_detected(work):
    before = snapshot(work); (work / 'jobs/song/input.wav').write_bytes(b'new source')
    with pytest.raises(ValueError): verify_preserved(before, snapshot(work), allow_retry_schema=True)
    (work / 'jobs/song/input.wav').write_bytes(b'private source')
    (work / 'jobs/jobs.sqlite3').unlink()
    with pytest.raises(ValueError): verify_preserved(before, snapshot(work), allow_retry_schema=True)


def test_workspace_symlinks_are_rejected(work, tmp_path):
    outside = tmp_path / 'outside'; outside.write_bytes(b'private')
    (work / 'jobs/song/link').symlink_to(outside)
    with pytest.raises(ValueError): snapshot(work)
