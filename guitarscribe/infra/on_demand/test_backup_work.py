import base64
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import backup_work as backup
import prepare_release


class RecordingObjects(backup.DirectoryObjects):
    def __init__(self, root):
        super().__init__(root)
        self.creates = []
        self.fail_on = None

    def create(self, name, source):
        self.creates.append(name)
        if self.fail_on and self.fail_on(name):
            raise OSError('fixture upload failure')
        return super().create(name, source)


@pytest.fixture
def workspace(tmp_path):
    work = tmp_path / 'live'; work.mkdir()
    jobs = work / 'jobs'; jobs.mkdir()
    with sqlite3.connect(jobs / 'jobs.sqlite3') as db:
        db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,payload TEXT,updated_at TEXT)')
        db.execute('INSERT INTO jobs VALUES (?,?,?)', ('song', json.dumps({'status':'completed'}), '2026-11-20'))
    for filename in ('root-practice.sqlite3', 'song-structure.sqlite3', 'chord-practice.sqlite3'):
        with sqlite3.connect(work / filename) as db:
            db.execute('CREATE TABLE edits(version INTEGER PRIMARY KEY, decision TEXT)')
            db.execute('INSERT INTO edits VALUES (?,?)', (1, '主歌：C，副歌：Am7'))
            db.execute('CREATE TABLE history(version INTEGER PRIMARY KEY, decision TEXT)')
            db.execute('INSERT INTO history VALUES (?,?)', (0, '待聽'))
    audio = jobs / 'song'; audio.mkdir()
    (audio / 'input.wav').write_bytes(b'original-private-audio' * 512)
    (audio / 'analysis-source.wav').write_bytes(b'source-local-audio' * 512)
    (audio / 'root-evidence.json').write_text('{"source":"verified","notes":[0,4,7]}')
    (audio / '.state.lock').touch()
    temp = audio / 'root-candidates-unfinished'; temp.mkdir(); (temp / 'worker.log').write_text('temporary')
    (work / 'empty-results').mkdir()
    mirror = tmp_path / 'objects'; mirror.mkdir()
    return work, RecordingObjects(mirror), tmp_path / 'scratch'


def run(workspace, **kwargs):
    work, store, scratch = workspace
    return backup.backup_workspace(work, store, temp_root=scratch, now=1_795_132_800., **kwargs)


def manifest(store, result):
    return json.loads((store.root / result['manifest']).read_text())


def rewrite_manifest(store, result, document):
    path = store.root / 'backups/manifests/malicious-fixture.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path.relative_to(store.root).as_posix()


def test_backup_restore_roundtrip_preserves_audio_all_databases_and_history(workspace, tmp_path):
    work, store, scratch = workspace
    before = {p.name:prepare_release.digest_database(p) for p in work.rglob('*.sqlite3')}
    result = run(workspace)
    document = manifest(store, result)
    assert result['status'] == 'complete' and store.creates[-1] == result['manifest']
    assert all('/blobs/sha256/' in p for p in store.creates[:-1])
    assert not any('.lock' in p or 'root-candidates-' in p for p in document['files'])
    assert len(document['sqlite_logical_sha256']) == 4
    target = tmp_path / 'restored'
    restored = backup.restore_workspace(store, result['manifest'], target,
                                         expected_manifest_sha256=result['manifest_sha256'])
    assert restored['status'] == 'restored'
    for name, row in document['files'].items():
        assert backup.file_hashes(target/name)['sha256'] == row['sha256']
    assert (target/'jobs/song/input.wav').read_bytes() == (work/'jobs/song/input.wav').read_bytes()
    assert (target/'empty-results').is_dir()
    after = {p.name:prepare_release.digest_database(p) for p in work.rglob('*.sqlite3')}
    assert before == after
    with sqlite3.connect(target/'root-practice.sqlite3') as db:
        assert db.execute('SELECT decision FROM history').fetchone()[0] == '待聽'
    assert not list(scratch.glob('snapshot-*'))


def test_repeated_backup_deduplicates_immutable_blobs_and_never_overwrites_manifest(workspace):
    first = run(workspace)
    store = workspace[1]; old_bytes = (store.root / first['manifest']).read_bytes()
    store.creates.clear()
    second = run(workspace)
    assert second['new_blobs'] == 0 and second['new_bytes'] == 0
    assert store.creates == [second['manifest']] and second['manifest'] != first['manifest']
    assert (store.root/first['manifest']).read_bytes() == old_bytes


def test_sqlite_wal_is_backed_up_via_api_into_a_standalone_database(workspace, tmp_path):
    work, store, _ = workspace
    db = sqlite3.connect(work/'root-practice.sqlite3')
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('INSERT INTO edits VALUES (2,?)', ('已確認 Eb2',)); db.commit()
        assert (work/'root-practice.sqlite3-wal').exists()
        result = run(workspace)
        document = manifest(store, result)
        assert not any(n.endswith(('-wal','-shm','-journal')) for n in document['files'])
        backup.restore_workspace(store, result['manifest'], tmp_path/'restored')
        with sqlite3.connect(tmp_path/'restored/root-practice.sqlite3') as restored:
            assert restored.execute('SELECT decision FROM edits WHERE version=2').fetchone()[0] == '已確認 Eb2'
            assert restored.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    finally:
        db.close()


def test_edit_during_cross_database_snapshot_publishes_nothing(workspace, monkeypatch):
    work, store, scratch = workspace
    original = prepare_release.shutil.copytree
    changed = False
    def copy(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            with sqlite3.connect(work/'root-practice.sqlite3') as db:
                db.execute('UPDATE edits SET decision=?', ('使用者最新修改',))
        return result
    monkeypatch.setattr(prepare_release.shutil, 'copytree', copy)
    with pytest.raises(RuntimeError): run(workspace)
    assert not store.creates and not list(scratch.glob('snapshot-*'))
    with sqlite3.connect(work/'root-practice.sqlite3') as db:
        assert db.execute('SELECT decision FROM edits').fetchone()[0] == '使用者最新修改'


def test_source_audio_change_during_copy_is_rejected(workspace):
    work, store, _ = workspace
    def snapshot(source, target):
        result = prepare_release.private_work_copy(source, target)
        (target/'jobs/song/input.wav').write_bytes(b'incomplete-or-corrupt-copy')
        return result
    with pytest.raises(backup.BackupInvalid): run(workspace, snapshotter=snapshot)
    assert not store.creates
    assert (work/'jobs/song/input.wav').read_bytes().startswith(b'original-private-audio')


def test_running_analysis_skips_without_uploading_or_copying(workspace):
    work, store, scratch = workspace
    with sqlite3.connect(work/'jobs/jobs.sqlite3') as db:
        db.execute('UPDATE jobs SET payload=?', (json.dumps({'status':'chord_analysis'}),))
    with pytest.raises(backup.BackupSkipped): run(workspace)
    assert not store.creates and not scratch.exists()


def test_analysis_start_during_upload_does_not_publish_manifest(workspace):
    work, store, scratch = workspace
    def busy(_): return bool(store.creates)
    with pytest.raises(backup.BackupSkipped): run(workspace, busy=busy)
    assert store.creates and all('/blobs/' in name for name in store.creates)
    assert not list(scratch.glob('snapshot-*'))


def test_failed_upload_leaves_no_completion_manifest_and_retry_reuses_blobs(workspace):
    _, store, _ = workspace
    store.fail_on = lambda name: len(store.creates) == 2
    with pytest.raises(OSError): run(workspace)
    assert not (store.root/'backups/manifests').exists()
    store.fail_on = None
    result = run(workspace)
    assert result['status'] == 'complete'
    assert result['new_blobs'] < len({v['sha256'] for v in manifest(store,result)['files'].values()})


def test_manifest_publication_failure_never_claims_completed_backup(workspace):
    store = workspace[1]; store.fail_on = lambda name:'/manifests/' in name
    with pytest.raises(OSError): run(workspace)
    assert not (store.root/'backups/manifests').exists()


def test_corrupt_existing_immutable_blob_is_not_overwritten(workspace):
    result = run(workspace); store = workspace[1]
    row = next(iter(manifest(store, result)['files'].values()))
    blob = store.root / row['blob']; blob.write_bytes(b'corrupt')
    count = len(list((store.root/'backups/manifests').glob('*.json')))
    with pytest.raises(backup.BackupInvalid): run(workspace)
    assert blob.read_bytes() == b'corrupt'
    assert len(list((store.root/'backups/manifests').glob('*.json'))) == count


@pytest.mark.parametrize('existing', ['file','empty_directory','live_directory','symlink'])
def test_restore_refuses_every_existing_target(workspace, tmp_path, existing):
    result = run(workspace); work, store, _ = workspace
    target = tmp_path/'existing'
    if existing == 'file': target.write_text('do not change')
    elif existing == 'empty_directory': target.mkdir()
    elif existing == 'live_directory': target = work
    else: target.symlink_to(work, target_is_directory=True)
    before = backup.file_hashes(work/'jobs/song/input.wav')
    with pytest.raises(FileExistsError): backup.restore_workspace(store,result['manifest'],target)
    assert backup.file_hashes(work/'jobs/song/input.wav') == before
    if existing == 'file': assert target.read_text() == 'do not change'


def test_restore_no_replace_handles_target_created_after_initial_check(workspace, tmp_path, monkeypatch):
    result = run(workspace); target = tmp_path/'racing-target'
    original = backup._publish_new_directory
    def racing(source, destination):
        destination.mkdir()
        return original(source,destination)
    monkeypatch.setattr(backup, '_publish_new_directory', racing)
    with pytest.raises(FileExistsError): backup.restore_workspace(workspace[1],result['manifest'],target)
    assert target.is_dir() and not list(target.iterdir())


def test_restore_corruption_never_publishes_partial_directory(workspace, tmp_path):
    result = run(workspace); store = workspace[1]
    row = manifest(store,result)['files']['jobs/song/input.wav']
    (store.root/row['blob']).write_bytes(b'x'*row['size'])
    target = tmp_path/'restored'
    with pytest.raises(backup.BackupInvalid): backup.restore_workspace(store,result['manifest'],target)
    assert not target.exists() and not list(tmp_path.glob('.restore-*'))


@pytest.mark.parametrize('change', ['traversal','absolute','backslash','wrong_blob','size','missing_db_digest','wrong_db_digest','file_parent'])
def test_malformed_manifest_cannot_escape_or_publish(workspace, tmp_path, change):
    result = run(workspace); store = workspace[1]; document=manifest(store,result)
    row = deepcopy(document['files']['jobs/song/input.wav'])
    if change == 'traversal': document['files']['../escape'] = row
    if change == 'absolute': document['directories'].append('/escape')
    if change == 'backslash': document['files']['..\\escape'] = row
    if change == 'wrong_blob': document['files']['jobs/song/input.wav']['blob'] = 'secrets/credentials'
    if change == 'size': document['files']['jobs/song/input.wav']['size'] = -1
    if change == 'missing_db_digest': document['sqlite_logical_sha256'].pop('root-practice.sqlite3')
    if change == 'wrong_db_digest': document['sqlite_logical_sha256']['root-practice.sqlite3'] = '0'*64
    if change == 'file_parent': document['files']['jobs/song/input.wav/child'] = row
    bad = rewrite_manifest(store,result,document)
    with pytest.raises(backup.BackupInvalid): backup.restore_workspace(store,bad,tmp_path/'restored')
    assert not (tmp_path/'restored').exists() and not (tmp_path/'escape').exists()


def test_restore_enforces_manifest_hash_and_total_disk_bound(workspace, tmp_path):
    result = run(workspace); store = workspace[1]
    with pytest.raises(backup.BackupInvalid):
        backup.restore_workspace(store,result['manifest'],tmp_path/'restored',expected_manifest_sha256='0'*64)
    with pytest.raises(backup.BackupInvalid):
        backup.restore_workspace(store,result['manifest'],tmp_path/'restored',max_bytes=1)
    assert not (tmp_path/'restored').exists()


def test_source_symlink_is_rejected_without_following_it(workspace, tmp_path):
    work, store, _ = workspace
    outside = tmp_path/'private-secret'; outside.write_text('never upload')
    (work/'unexpected').symlink_to(outside)
    with pytest.raises(backup.BackupInvalid): run(workspace)
    assert not store.creates


def test_temp_directory_must_not_be_inside_live_workspace(workspace):
    work, store, _ = workspace
    with pytest.raises(backup.BackupInvalid):
        backup.backup_workspace(work,store,temp_root=work/'temp')
    assert not store.creates and not (work/'temp').exists()


def test_concurrent_timer_or_manual_backup_is_skipped(workspace):
    work, store, scratch = workspace
    with backup.backup_lock(scratch,work.resolve()):
        with pytest.raises(backup.BackupSkipped): run(workspace)
    assert not store.creates


def test_only_marked_same_workspace_interrupted_staging_is_cleaned(workspace):
    work, store, scratch = workspace
    owned=scratch/'snapshot-interrupted'; owned.mkdir(parents=True)
    (owned/'.backup-owner.json').write_text(json.dumps(backup._staging_owner(work.resolve())))
    (owned/'partial-audio').write_bytes(b'unfinished temporary copy')
    unrelated=scratch/'snapshot-someone-else'; unrelated.mkdir()
    (unrelated/'keep.txt').write_text('keep')
    other=scratch/'snapshot-other-workspace'; other.mkdir()
    (other/'.backup-owner.json').write_text(json.dumps(backup._staging_owner(work.parent/'other')))
    result=run(workspace)
    assert result['status']=='complete' and not owned.exists()
    assert (unrelated/'keep.txt').read_text()=='keep' and other.is_dir()


class FakeOpener:
    def __init__(self): self.objects = {}; self.calls = []
    def open(self, request, timeout):
        self.calls.append(request)
        assert request.get_header('Authorization') == 'Bearer fixture-token'
        parsed = urlsplit(request.full_url); query = parse_qs(parsed.query)
        if request.method == 'POST':
            assert query['ifGenerationMatch'] == ['0'] and query['uploadType'] == ['media']
            assert hasattr(request.data,'read'), 'upload must stream from an open file'
            name = query['name'][0]
            if name in self.objects: raise HTTPError(request.full_url,412,'already exists',{},None)
            data = request.data.read(); self.objects[name] = data
        else:
            name = unquote(parsed.path.split('/o/',1)[1])
            if name not in self.objects: raise HTTPError(request.full_url,404,'missing',{},None)
            data = self.objects[name]
            if query.get('alt') == ['media']:
                assert query['generation'] == ['123']
                return io.BytesIO(data)
        import hashlib
        return io.BytesIO(json.dumps(dict(generation='123',size=str(len(data)),
            md5Hash=base64.b64encode(hashlib.md5(data).digest()).decode())).encode())


def test_gcs_rest_uses_create_only_preconditions_streams_and_pins_read_generation(tmp_path):
    opener = FakeOpener(); store=backup.GCSObjects('private-test-bucket',lambda:'fixture-token',opener)
    source=tmp_path/'data'; source.write_bytes(b'private-audio')
    name='backups/blobs/sha256/aa/'+'a'*64
    assert store.stat(name) is None
    info=store.create(name,source)
    assert info.generation=='123' and info.size==13
    with pytest.raises(FileExistsError): store.create(name,source)
    restored=tmp_path/'restored'; store.download(name,'123',restored,max_bytes=13)
    assert restored.read_bytes()==source.read_bytes()
    with pytest.raises(backup.BackupInvalid): store.create('public/audio',source)
    assert len([r for r in opener.calls if r.method=='POST'])==2


def test_metadata_token_cached_and_no_credentials_printed(capsys):
    class Metadata:
        calls=0
        def open(self,request,timeout):
            self.calls+=1
            assert request.get_header('Metadata-flavor')=='Google'
            assert 'Authorization' not in request.headers
            return io.BytesIO(b'{"access_token":"secret-token","expires_in":3600}')
    now=[100.]; opener=Metadata(); token=backup.MetadataToken(opener,lambda:now[0])
    assert token()=='secret-token' and token()=='secret-token' and opener.calls==1
    now[0]+=3550
    assert token()=='secret-token' and opener.calls==2
    assert capsys.readouterr()==('','')
