"""Read-only post-migration verification on the private VM; prints no credentials."""
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request

ROOT = Path('/srv/guitarscribe')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024 * 1024): h.update(block)
    return h.hexdigest()


def db_digest(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        return hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()


def main():
    manifest = json.loads((ROOT / 'release-manifest.json').read_text())
    access = json.loads((ROOT / 'access.json').read_text())
    auth = 'Basic ' + base64.b64encode(f"{access['username']}:{access['password']}".encode()).decode()
    def get(path, authorized=True, headers=None):
        request = urllib.request.Request('http://127.0.0.1:5273' + path,
            headers={**({'Authorization': auth} if authorized else {}), **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
    expected = manifest['sqlite_logical_sha256']
    before = {name: db_digest(ROOT / 'work' / name) for name in expected}
    assert before == expected, 'Migrated database content differs from snapshot'
    assert all(digest(ROOT / 'work' / name) == value for name, value in manifest['files_sha256'].items()), 'Migrated recording or result differs'
    assert get('/backend/health', authorized=False)[0] == 401
    assert get('/backend/health')[0] == 200
    library = json.loads(get('/backend/cloud/library')[2])
    rows = []
    for job in ('84defcef7fd44bbc8a1024b24d65c78e', '83a3643ab3814172a046cebf709f3413', 'a3be29912a7045448765290d7cba2f6c'):
        prefix = f'/backend/api/v1/jobs/{job}'
        structure = json.loads(get(prefix + '/song-structure')[2])
        assert structure['source_matches']
        source = structure['document']['source']
        url = prefix + '/song-structure/audio?fingerprint=' + source['fingerprint'] + '&audio_sha256=' + source['audio_sha256']
        status, headers, data = get(url, headers={'Range': 'bytes=0-1023'})
        assert status == 206 and len(data) == 1024 and headers['Content-Range'].startswith('bytes 0-1023/')
        assert get(url, authorized=False)[0] == 401
        assert get(prefix + '/root-practice')[0] == 200
        assert json.loads(get(prefix + '/chord-practice')[2])['source_matches']
        rows.append(dict(job=job, sections=len(structure['document']['sections']), audio_range=status, source_matches=True))
    after = {name: db_digest(ROOT / 'work' / name) for name in expected}
    assert before == after, 'Read-only checks changed progress'
    print(json.dumps(dict(database_count=len(expected), artifact_count=len(manifest['files_sha256']),
                         migration_hashes_match=True, no_progress_changes=True,
                         songs_in_library=len(library['songs']), rows=rows), indent=2))


if __name__ == '__main__':
    main()
