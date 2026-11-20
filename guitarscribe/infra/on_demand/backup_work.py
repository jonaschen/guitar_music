"""Private immutable workspace backups. No live files are replaced or uploaded publicly.

Install beside prepare_release.py and host_activity.py. The timer may run every
30 minutes; analysis or a concurrent backup makes this invocation skip safely.
Use --temp-root on the persistent disk (allow at least one workspace-sized copy).

GCS permissions: objectViewer plus objectCreator restricted to backups/. There
is no delete, overwrite, mutable latest pointer, or bucket IAM operation here.
Restoration verifies every SHA-256 and SQLite logical digest before an atomic,
no-replace publication to a NEW directory on Linux. An offline object mirror is
also supported; it must preserve object names under its root.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing, contextmanager
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sqlite3
import stat
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 50_000
MAX_RESTORE_BYTES = 30 * 1024 ** 3
DIGEST = re.compile(r'^[a-f0-9]{64}$')


class BackupSkipped(Exception):
    pass


class BackupInvalid(Exception):
    pass


@dataclass(frozen=True)
class ObjectInfo:
    generation: str
    size: int
    md5: str


def safe_relative(value):
    if (not isinstance(value, str) or not value or len(value.encode()) > 2048
            or '\\' in value or any(ord(c) < 32 for c in value)):
        raise BackupInvalid('Invalid relative path')
    parts = value.split('/')
    if any(p in ('', '.', '..') for p in parts) or PurePosixPath(value).is_absolute():
        raise BackupInvalid('Invalid relative path')
    return value


def safe_prefix(value):
    safe_relative(value)
    if value != 'backups' and not value.startswith('backups/'):
        raise BackupInvalid('Backup objects must stay under backups/')
    return value


def file_hashes(path):
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with Path(path).open('rb') as stream:
        while chunk := stream.read(CHUNK_SIZE):
            sha.update(chunk); md5.update(chunk); size += len(chunk)
    return dict(sha256=sha.hexdigest(), md5=base64.b64encode(md5.digest()).decode(), size=size)


def regular_tree(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise BackupInvalid('Workspace must be a real directory')
    files, directories = [], []
    for path in sorted(root.rglob('*')):
        name = safe_relative(path.relative_to(root).as_posix())
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise BackupInvalid('Symlinks and special files are not backed up')
        (directories if stat.S_ISDIR(mode) else files).append(name)
    if len(files) > MAX_FILES or len(directories) > MAX_FILES:
        raise BackupInvalid('Workspace file count exceeds backup limit')
    return files, directories


def _check_object(info, expected):
    # SHA-256 names are computed locally. GCS returns the MD5 of the immutable
    # stored object, allowing dedup without downloading all old audio each run.
    # Restore independently rehashes the full contents with SHA-256.
    if (not info or not str(info.generation).isdigit() or int(info.generation) <= 0
            or info.size != expected['size'] or info.md5 != expected['md5']):
        raise BackupInvalid('Stored object failed size/checksum verification')


def ensure_object(store, name, path, expected):
    info = store.stat(name)
    created = False
    if info is None:
        try:
            info = store.create(name, path)
            created = True
        except FileExistsError:
            info = store.stat(name)
    _check_object(info, expected)
    return info, created


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MetadataToken:
    def __init__(self, opener=None, clock=time.monotonic):
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirect())
        self.clock = clock
        self.token = None
        self.expires = 0

    def __call__(self):
        if self.token is None or self.clock() >= self.expires:
            request = Request('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',
                              headers={'Metadata-Flavor': 'Google'})
            with self.opener.open(request, timeout=15) as response:
                payload = response.read(65537)
                if len(payload) > 65536:
                    raise BackupInvalid('Invalid metadata response')
                data = json.loads(payload)
            self.token = data['access_token']
            self.expires = self.clock() + max(0, int(data['expires_in']) - 60)
        return self.token


class GCSObjects:
    """Small stdlib REST adapter; media uploads stream from files, never overwrite."""
    def __init__(self, bucket, token_provider=None, opener=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]', bucket):
            raise ValueError('Invalid bucket name')
        self.bucket = bucket
        self.token_provider = token_provider or MetadataToken()
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirect())

    def _request(self, url, *, data=None, method='GET', headers=None):
        headers = dict(headers or {})
        headers['Authorization'] = 'Bearer ' + self.token_provider()
        return self.opener.open(Request(url, data=data, headers=headers, method=method), timeout=180)

    def _object_url(self, name):
        safe_relative(name)
        return f'https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{quote(name, safe="")}'

    @staticmethod
    def _info(response):
        payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise BackupInvalid('Object metadata is too large')
        data = json.loads(payload)
        return ObjectInfo(str(data['generation']), int(data['size']), data.get('md5Hash', ''))

    def stat(self, name):
        try:
            with self._request(self._object_url(name)) as response:
                return self._info(response)
        except HTTPError as error:
            if error.code == 404:
                error.close()
                return None
            raise

    def create(self, name, source):
        safe_relative(name)
        if not name.startswith('backups/'):
            raise BackupInvalid('Writes are restricted to backups/')
        source = Path(source)
        query = urlencode({'uploadType': 'media', 'name': name, 'ifGenerationMatch': '0'})
        url = f'https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o?{query}'
        try:
            with source.open('rb') as stream:
                with self._request(url, method='POST', data=stream, headers={
                    'Content-Type': 'application/octet-stream', 'Content-Length': str(source.stat().st_size)}) as response:
                    return self._info(response)
        except HTTPError as error:
            if error.code in (409, 412):
                error.close()
                raise FileExistsError(name) from None
            raise

    def download(self, name, generation, target, *, max_bytes):
        if not str(generation).isdigit() or int(generation) <= 0:
            raise BackupInvalid('Invalid object generation')
        url = self._object_url(name) + '?' + urlencode({'alt':'media', 'generation':str(generation)})
        with self._request(url) as response, Path(target).open('xb') as stream:
            _copy_bounded(response, stream, max_bytes)
            stream.flush(); os.fsync(stream.fileno())


def _copy_bounded(source, destination, limit):
    total = 0
    while chunk := source.read(CHUNK_SIZE):
        total += len(chunk)
        if total > limit:
            raise BackupInvalid('Object exceeds its declared size')
        destination.write(chunk)


class DirectoryObjects:
    """Offline object mirror for validation/recovery; contents are SHA-checked.

    GCS generations do not exist in an exported directory. The offline adapter
    pins the selected object by its immutable name and relies on full SHA-256
    verification during restoration. Its create method is used by offline tests.
    """
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError('Object mirror must exist')

    def _path(self, name):
        safe_relative(name)
        path = self.root
        for part in name.split('/'):
            path = path / part
            if path.is_symlink():
                raise BackupInvalid('Object mirror contains a symlink')
        return path

    def stat(self, name):
        path = self._path(name)
        if not path.exists():
            return None
        if not path.is_file():
            raise BackupInvalid('Expected a regular object file')
        digest = file_hashes(path)
        return ObjectInfo('1', digest['size'], digest['md5'])

    def create(self, name, source):
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix='.object-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as target, Path(source).open('rb') as stream:
                shutil.copyfileobj(stream, target, CHUNK_SIZE)
                target.flush(); os.fsync(target.fileno())
            os.link(temporary, path)  # Atomic create-if-absent; never replace.
        finally:
            Path(temporary).unlink(missing_ok=True)
        return self.stat(name)

    def download(self, name, generation, target, *, max_bytes):
        with self._path(name).open('rb') as stream, Path(target).open('xb') as destination:
            _copy_bounded(stream, destination, max_bytes)
            destination.flush(); os.fsync(destination.fileno())


@contextmanager
def backup_lock(temp_root, work):
    temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = '.backup-' + hashlib.sha256(str(work).encode()).hexdigest() + '.lock'
    descriptor = os.open(temp_root / name, os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupSkipped('Another backup is in progress') from None
        yield


def _staging_owner(work):
    return {'application': 'guitarscribe-work-backup',
            'workspace_sha256': hashlib.sha256(str(work).encode()).hexdigest()}


def _clean_stale_staging(temp_root, work):
    """The same-workspace lock is held. Clean only our marked interrupted copies."""
    for path in temp_root.glob('snapshot-*'):
        marker = path / '.backup-owner.json'
        if path.is_symlink() or not path.is_dir() or marker.is_symlink():
            continue
        try:
            if marker.stat().st_size > 1024 or json.loads(marker.read_text()) != _staging_owner(work):
                continue
        except (OSError, ValueError):
            continue
        shutil.rmtree(path)


def backup_workspace(work, store, *, prefix='backups', temp_root, now=None,
                     snapshotter=None, busy=None):
    from prepare_release import private_work_copy, digest_database
    from host_activity import active_analysis
    work, temp_root = Path(work), Path(temp_root)
    if work.is_symlink():
        raise BackupInvalid('Workspace must not be a symlink')
    work, temp_root = work.resolve(), temp_root.resolve()
    if temp_root == work or work in temp_root.parents:
        raise BackupInvalid('Temporary directory must be outside the live workspace')
    prefix = safe_prefix(prefix)
    snapshotter = snapshotter or private_work_copy
    busy = busy or active_analysis
    now = time.time() if now is None else now
    if not math.isfinite(now):
        raise ValueError('Invalid backup time')
    if busy(work):
        raise BackupSkipped('Analysis is active; backup deferred')
    with backup_lock(temp_root, work):
        _clean_stale_staging(temp_root, work)
        regular_tree(work)  # Reject symlinks before copytree can follow them.
        with tempfile.TemporaryDirectory(prefix='snapshot-', dir=temp_root) as temporary:
            temporary = Path(temporary)
            (temporary / '.backup-owner.json').write_text(json.dumps(_staging_owner(work)))
            snapshot = temporary / 'work'
            audit = snapshotter(work, snapshot)
            files, directories = regular_tree(snapshot)
            records = {}
            for name in files:
                record = file_hashes(snapshot / name)
                if name.endswith('.sqlite3'):
                    if digest_database(snapshot / name) != audit['sqlite_logical_sha256'].get(name):
                        raise BackupInvalid('SQLite snapshot differs from its logical digest')
                elif record['sha256'] != audit['files_sha256'].get(name):
                    raise BackupInvalid('Snapshot file differs from its verified source')
                records[name] = record
            if busy(work):
                raise BackupSkipped('Analysis started during snapshot; backup deferred')
            created_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
            snapshot_id = datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex
            manifest = dict(schema_version=1, application='guitarscribe', private_data=True,
                snapshot_id=snapshot_id, created_at=created_at, blob_prefix=prefix + '/blobs/sha256',
                directories=directories, files=records, sqlite_logical_sha256=audit['sqlite_logical_sha256'])
            new_blobs = new_bytes = 0
            for name, record in records.items():
                if busy(work):
                    raise BackupSkipped('Analysis started during upload; no completed manifest published')
                digest = record['sha256']
                object_name = f'{prefix}/blobs/sha256/{digest[:2]}/{digest}'
                info, created = ensure_object(store, object_name, snapshot / name, record)
                record.update(blob=object_name, generation=info.generation)
                new_blobs += int(created)
                if created:
                    new_bytes += record['size']
            if busy(work):
                raise BackupSkipped('Analysis started before publication; backup deferred')
            manifest_path = temporary / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                                                 allow_nan=False, separators=(',', ':')) + '\n')
            manifest_digest = file_hashes(manifest_path)
            if manifest_digest['size'] > MAX_MANIFEST_BYTES:
                raise BackupInvalid('Manifest exceeds size limit')
            manifest_name = prefix + '/manifests/' + snapshot_id + '.json'
            # The only completion marker. Never publish on a partial upload.
            info = store.create(manifest_name, manifest_path)
            _check_object(info, manifest_digest)
            return dict(status='complete', manifest=manifest_name, generation=info.generation,
                        manifest_sha256=manifest_digest['sha256'], files=len(records),
                        new_blobs=new_blobs, new_bytes=new_bytes)


def observed_backup(work, store, *, status_file=None, clock=time.time, runner=None, **kwargs):
    """Persist only verified completion; status lives outside the backed-up tree."""
    runner = runner or backup_workspace
    if status_file is None:
        return runner(work, store, **kwargs)
    path, work = Path(status_file).resolve(), Path(work).resolve()
    if path == work or work in path.parents:
        raise ValueError('Backup status must stay outside the workspace')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupSkipped('Another observed backup is active') from None
        try:
            previous = json.loads(path.read_text())
            success = previous.get('last_success') if isinstance(previous, dict) else None
        except (OSError, ValueError):
            success = None
        started = clock()
        record = dict(schema_version=1, state='running', started_at=started, last_success=success)
        def write():
            with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.backup-status-', delete=False) as output:
                temporary = Path(output.name)
                try:
                    os.fchmod(output.fileno(), 0o600)
                    json.dump(record, output, allow_nan=False)
                    output.flush(); os.fsync(output.fileno())
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
        write()
        try:
            result = runner(work, store, **kwargs)
            if result.get('status') != 'complete':
                raise BackupInvalid('Backup did not publish a completed manifest')
            record.update(state='complete', finished_at=clock(), last_success=dict(
                snapshot_at=started, completed_at=clock(), manifest=result['manifest'],
                manifest_sha256=result['manifest_sha256'], files=result['files']))
            write()
            return result
        except BackupSkipped:
            record.update(state='deferred', finished_at=clock())
            write(); raise
        except Exception as error:
            record.update(state='interrupted' if isinstance(error, InterruptedError) else 'failed',
                          finished_at=clock(), error_type=type(error).__name__)
            write(); raise


def validate_manifest(manifest, *, max_bytes):
    try:
        if (manifest['schema_version'] != 1 or manifest['application'] != 'guitarscribe'
                or manifest['private_data'] is not True):
            raise BackupInvalid('Unsupported backup manifest')
        prefix = manifest['blob_prefix']
        if not prefix.endswith('/blobs/sha256'):
            raise BackupInvalid('Invalid blob prefix')
        safe_prefix(prefix[:-len('/blobs/sha256')])
        files, directories, databases = manifest['files'], manifest['directories'], manifest['sqlite_logical_sha256']
        if (not isinstance(files, dict) or not isinstance(directories, list) or not isinstance(databases, dict)
                or len(files) > MAX_FILES or len(directories) > MAX_FILES or len(set(directories)) != len(directories)):
            raise BackupInvalid('Invalid file inventory')
        total = 0
        for name in directories:
            safe_relative(name)
            if name in files:
                raise BackupInvalid('Conflicting file and directory paths')
        for name, record in files.items():
            safe_relative(name)
            if not DIGEST.fullmatch(record['sha256']):
                raise BackupInvalid('Invalid SHA-256')
            digest = record['sha256']
            if record['blob'] != f'{prefix}/{digest[:2]}/{digest}':
                raise BackupInvalid('Blob path does not match its SHA-256')
            if not str(record['generation']).isdigit() or int(record['generation']) <= 0:
                raise BackupInvalid('Invalid object generation')
            if type(record['size']) is not int or record['size'] < 0:
                raise BackupInvalid('Invalid file size')
            if len(base64.b64decode(record['md5'], validate=True)) != 16:
                raise BackupInvalid('Invalid file checksum')
            total += record['size']
            if total > max_bytes:
                raise BackupInvalid('Restore exceeds its disk size limit')
        for name in set(files) | set(directories):
            for parent in PurePosixPath(name).parents:
                if str(parent) in files:
                    raise BackupInvalid('A file is used as a directory')
        if set(databases) != {n for n in files if n.endswith('.sqlite3')}:
            raise BackupInvalid('SQLite digest inventory is incomplete')
        if any(not DIGEST.fullmatch(v) for v in databases.values()):
            raise BackupInvalid('Invalid SQLite digest')
        return total
    except (KeyError, TypeError, ValueError) as error:
        raise BackupInvalid('Malformed backup manifest') from error


def _publish_new_directory(source, target):
    """Linux renameat2 avoids the exists()+rename() race that replaces empty dirs."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        raise BackupInvalid('Atomic no-replace restore requires Linux renameat2')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(target)
        raise OSError(code, os.strerror(code), str(target))
    descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def restore_workspace(store, manifest_name, target, *, max_bytes=MAX_RESTORE_BYTES,
                      expected_manifest_sha256=None):
    from prepare_release import digest_database
    safe_relative(manifest_name)
    if not manifest_name.startswith('backups/'):
        raise BackupInvalid('Manifest must be under backups/')
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError('Invalid restore size limit')
    target = Path(target)
    if target.is_symlink() or target.exists():
        raise FileExistsError('Restore target already exists; live work is never replaced')
    parent = target.parent.resolve(strict=True)
    target = parent / target.name
    info = store.stat(manifest_name)
    if not info or info.size > MAX_MANIFEST_BYTES:
        raise BackupInvalid('Backup manifest is missing or too large')
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=parent) as temporary:
        temporary = Path(temporary)
        manifest_path = temporary / 'manifest.json'
        store.download(manifest_name, info.generation, manifest_path, max_bytes=MAX_MANIFEST_BYTES)
        digest = file_hashes(manifest_path)
        _check_object(info, digest)
        if expected_manifest_sha256 is not None and digest['sha256'] != expected_manifest_sha256:
            raise BackupInvalid('Backup manifest SHA-256 does not match')
        manifest = json.loads(manifest_path.read_text())
        validate_manifest(manifest, max_bytes=max_bytes)
        restored = temporary / 'work'; restored.mkdir(mode=0o700)
        for name in manifest['directories']:
            (restored / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, record in manifest['files'].items():
            path = restored / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            store.download(record['blob'], record['generation'], path, max_bytes=record['size'])
            path.chmod(0o600)
            actual = file_hashes(path)
            if any(actual[key] != record[key] for key in ('sha256', 'md5', 'size')):
                raise BackupInvalid('Restored file failed its checksum')
        for name, expected in manifest['sqlite_logical_sha256'].items():
            path = restored / name
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise BackupInvalid('Restored SQLite database failed integrity check')
            if digest_database(path) != expected:
                raise BackupInvalid('Restored SQLite logical digest does not match')
        _publish_new_directory(restored, target)
    return dict(status='restored', target=str(target), files=len(manifest['files']),
                manifest=manifest_name, manifest_sha256=digest['sha256'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('backup')
    backup.add_argument('--work', type=Path, required=True)
    backup.add_argument('--bucket', required=True)
    backup.add_argument('--prefix', default='backups')
    backup.add_argument('--temp-root', type=Path, required=True)
    backup.add_argument('--status-file', type=Path)
    restore = commands.add_parser('restore')
    source = restore.add_mutually_exclusive_group(required=True)
    source.add_argument('--bucket')
    source.add_argument('--objects-dir', type=Path)
    restore.add_argument('--manifest', required=True)
    restore.add_argument('--manifest-sha256')
    restore.add_argument('--target', type=Path, required=True)
    restore.add_argument('--max-bytes', type=int, default=MAX_RESTORE_BYTES)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == 'backup':
            result = observed_backup(args.work, GCSObjects(args.bucket), prefix=args.prefix, temp_root=args.temp_root, status_file=args.status_file)
        else:
            store = GCSObjects(args.bucket) if args.bucket else DirectoryObjects(args.objects_dir)
            result = restore_workspace(store, args.manifest, args.target, max_bytes=args.max_bytes,
                                       expected_manifest_sha256=args.manifest_sha256)
    except BackupSkipped:
        print(json.dumps({'status':'skipped', 'reason':'analysis_or_backup_active'}))
        return 0
    except Exception as error:
        # Do not log request objects, metadata tokens, private paths or payloads.
        print(json.dumps({'status':'failed', 'error_type':type(error).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError('Backup interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
