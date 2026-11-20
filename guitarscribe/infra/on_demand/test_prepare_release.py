import importlib.util
from pathlib import Path
import sqlite3
import pytest

spec = importlib.util.spec_from_file_location('prepare_release', Path(__file__).with_name('prepare_release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_sqlite_backup_keeps_committed_wal_content_without_copying_wal(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    db = sqlite3.connect(source / 'progress.sqlite3')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE draft(value TEXT)')
    db.execute("INSERT INTO draft VALUES ('confirmed chord')"); db.commit()
    (source / 'input.wav').write_bytes(b'private-source')
    target = tmp_path / 'backup'
    manifest = release.private_work_copy(source, target)
    with sqlite3.connect(target / 'progress.sqlite3') as copied:
        assert copied.execute('SELECT value FROM draft').fetchone() == ('confirmed chord',)
    assert not list(target.glob('*-wal'))
    assert manifest['files_sha256']['input.wav'] == release.sha(target / 'input.wav')
    db.close()


def test_rejects_symlinks_instead_of_copying_files_outside_workspace(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    private = tmp_path / 'private-secret'; private.write_text('do not migrate')
    (source / 'linked.txt').symlink_to(private)
    with pytest.raises(ValueError, match='symlink'):
        release.private_work_copy(source, tmp_path / 'backup')
    assert not (tmp_path / 'backup/linked.txt').exists()


def test_changed_audio_cannot_publish_as_consistent_backup(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    audio = source / 'input.wav'; audio.write_bytes(b'before')
    copy = release.shutil.copytree
    def concurrent_edit(*args, **kwargs):
        result = copy(*args, **kwargs)
        audio.write_bytes(b'after')
        return result
    monkeypatch.setattr(release.shutil, 'copytree', concurrent_edit)
    with pytest.raises(RuntimeError, match='changed during backup'):
        release.private_work_copy(source, tmp_path / 'backup')
