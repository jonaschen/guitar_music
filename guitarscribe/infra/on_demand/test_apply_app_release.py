import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

from apply_app_release import stage_release, apply_staged


def package(tmp_path, bad=None):
    archive = tmp_path / 'app.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in ['app/backend/app/api.py', 'site/index.html']:
            member = tarfile.TarInfo(name); member.size = 3
            tar.addfile(member, io.BytesIO(b'new'))
        if bad:
            member = tarfile.TarInfo(bad)
            if bad == 'app/link': member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'
            tar.addfile(member)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(commit='a'*40, release_kind='app_only', artifacts={'app.tar.gz':dict(sha256=sha, bytes=archive.stat().st_size)})))
    return archive, manifest, sha


@pytest.mark.parametrize('bad', ['../work/overwrite', '/tmp/absolute', 'work/new-song', 'app/link'])
def test_unsafe_package_never_reaches_the_application(tmp_path, bad):
    archive, manifest, sha = package(tmp_path, bad)
    with pytest.raises(ValueError): stage_release(archive, manifest, tmp_path/'release', 'a'*40, sha)
    assert not (tmp_path/'work').exists()


def test_explicit_commit_and_hash_and_new_release_directory_required(tmp_path):
    archive, manifest, sha = package(tmp_path)
    with pytest.raises(ValueError): stage_release(archive, manifest, tmp_path/'wrong-commit', 'b'*40, sha)
    with pytest.raises(ValueError): stage_release(archive, manifest, tmp_path/'wrong-hash', 'a'*40, '0'*64)
    release = tmp_path/'release'
    stage_release(archive, manifest, release, 'a'*40, sha)
    with pytest.raises(FileExistsError): stage_release(archive, manifest, release, 'a'*40, sha)


@pytest.mark.parametrize('failure', ['none', 'health', 'data'])
def test_code_swap_preserves_work_and_rolls_back_code_on_failed_validation(tmp_path, failure):
    archive, manifest, sha = package(tmp_path); release = tmp_path/'release'
    stage_release(archive, manifest, release, 'a'*40, sha)
    root = tmp_path/'live'
    (root/'app/backend/app').mkdir(parents=True); (root/'app/backend/app/api.py').write_text('old')
    (root/'site').mkdir(); (root/'site/index.html').write_text('old')
    (root/'app-release-manifest.json').write_text('{"commit":"old"}')
    (root/'work/jobs').mkdir(parents=True)
    with sqlite3.connect(root/'work/jobs/jobs.sqlite3') as db:
        db.execute('CREATE TABLE jobs (id TEXT, payload TEXT)'); db.execute("INSERT INTO jobs VALUES ('song','my-progress')")
    calls = []
    def service(action):
        calls.append(action)
        if action == 'start' and calls.count('start') == 1:
            with sqlite3.connect(root/'work/jobs/jobs.sqlite3') as db:
                db.execute('CREATE TABLE job_retries (parent_id TEXT PRIMARY KEY, child_id TEXT NOT NULL)')
                if failure == 'data': db.execute("UPDATE jobs SET payload='changed'")
    def health():
        if failure == 'health': raise RuntimeError('Unhealthy candidate')
    if failure == 'none':
        result = apply_staged(root, release, service, health, allow_retry_schema=True)
        assert result['allowed_additions'] == ['jobs/jobs.sqlite3:job_retries']
        assert (root/'app/backend/app/api.py').read_text() == 'new'
        assert (release/'previous/app/backend/app/api.py').read_text() == 'old'
        assert json.loads((root/'app-release-manifest.json').read_text())['commit'] == 'a'*40
    else:
        with pytest.raises((ValueError, RuntimeError)): apply_staged(root, release, service, health, allow_retry_schema=True)
        assert (root/'app/backend/app/api.py').read_text() == 'old'
        assert (root/'site/index.html').read_text() == 'old'
        assert json.loads((root/'app-release-manifest.json').read_text())['commit'] == 'old'
        assert calls == ['stop', 'start', 'stop', 'start']
    with sqlite3.connect(root/'work/jobs/jobs.sqlite3') as db:
        # Code rollback must never restore an old DB over newly committed data.
        assert db.execute('SELECT payload FROM jobs').fetchone()[0] == ('changed' if failure == 'data' else 'my-progress')
        assert db.execute('SELECT COUNT(*) FROM job_retries').fetchone()[0] == 0
