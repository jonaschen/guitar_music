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


def test_app_only_release_cannot_read_or_package_personal_work_or_runtime(tmp_path, monkeypatch):
    import io
    import tarfile
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, data in [('backend/app/__init__.py',b''),('frontend/package.json',b'{}'),('rhythm-patterns/example.json',b'{}')]:
            info=tarfile.TarInfo('guitarscribe/'+name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
    def check_output(args, **kwargs):
        return 'a'*40 if 'rev-parse' in args else payload.getvalue()
    def run(args, *, cwd, **kwargs):
        if args==['npm','run','build']:
            site=Path(cwd)/'dist';(site/'assets').mkdir(parents=True)
            (site/'index.html').write_text('<body></body>');(site/'assets/app.js').write_text('application')
    monkeypatch.setattr(release.subprocess,'check_output',check_output)
    monkeypatch.setattr(release.subprocess,'run',run)
    monkeypatch.setattr(release,'private_work_copy',lambda *a:pytest.fail('code release touched private work'))
    out=tmp_path/'release'
    result=release.prepare(tmp_path/'repo',tmp_path/'missing-runtime',out,app_only=True)
    assert set(result['artifacts'])=={'app.tar.gz'}
    assert result['release_kind']=='app_only'
    with tarfile.open(out/'app.tar.gz') as archive:
        names=archive.getnames()
        assert 'site/index.html' in names and 'app/backend/host_activity.py' in names
        assert 'app/backend/apply_app_release.py' in names and 'app/backend/release_workspace.py' in names
        assert not any(name.startswith(('work/','runtime/')) for name in names)
