"""Read-only release evidence, including narrowly allowed additive retry schema.

Never restores, rewrites or copies the live workspace. SQLite is read through
its API so committed WAL rows are included. Evidence contains hashes, not song
decisions or audio. Run while the application is stopped or a checked idle
window is held; the deployment caller must detect concurrent activity.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
    return digest.hexdigest()


def database_snapshot(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity check failed')
        objects, tables = {}, {}
        for kind, name, owner, sql in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name'):
            objects[name] = dict(type=kind, table=owner, sql=sql)
            if kind == 'table':
                quoted = '"' + name.replace('"', '""') + '"'
                # repr preserves SQLite value types and bytes; sorting ignores
                # physical page/row order, while preserving duplicate rows.
                rows = sorted(repr(row).encode() for row in db.execute('SELECT * FROM ' + quoted))
                digest = hashlib.sha256()
                for row in rows:
                    digest.update(len(row).to_bytes(8, 'big')); digest.update(row)
                tables[name] = dict(rows=len(rows), sha256=digest.hexdigest())
        return dict(objects=objects, tables=tables)


def snapshot(work):
    work = Path(work)
    if not work.is_dir() or work.is_symlink(): raise ValueError('A real workspace directory is required')
    files, databases = {}, {}
    for path in sorted(work.rglob('*')):
        relative = path.relative_to(work).as_posix()
        if path.is_symlink(): raise ValueError('Workspace symlinks are not supported')
        if not path.is_file(): continue
        if path.name.endswith(('.lock', '.sqlite3-wal', '.sqlite3-shm', '.sqlite3-journal')): continue
        if any(part.startswith('root-candidates-') for part in path.relative_to(work).parts): continue
        if path.name.endswith('.sqlite3'): databases[relative] = database_snapshot(path)
        else: files[relative] = file_sha(path)
    return dict(schema_version=1, files=files, databases=databases)


def verify_preserved(before, after, *, allow_retry_schema=False):
    if before.get('schema_version') != 1 or after.get('schema_version') != 1:
        raise ValueError('Unsupported snapshot schema')
    if before['files'] != after['files']: raise ValueError('Workspace files changed')
    if before['databases'].keys() != after['databases'].keys(): raise ValueError('Database inventory changed')
    additions = []
    for path, old in before['databases'].items():
        new = after['databases'][path]
        for name, obj in old['objects'].items():
            if new['objects'].get(name) != obj: raise ValueError('Existing database schema changed: ' + path)
        for name, rows in old['tables'].items():
            if new['tables'].get(name) != rows: raise ValueError('Existing database rows changed: ' + path)
        extra = set(new['objects']) - set(old['objects'])
        if not extra: continue
        if not (allow_retry_schema and path == 'jobs/jobs.sqlite3' and 'job_retries' not in old['objects']
                and extra == {'job_retries', 'sqlite_autoindex_job_retries_1'}):
            raise ValueError('Unexpected new database schema: ' + path)
        table = new['objects']['job_retries']; index = new['objects']['sqlite_autoindex_job_retries_1']
        expected = 'CREATE TABLE job_retries (parent_id TEXT PRIMARY KEY, child_id TEXT NOT NULL)'
        if table['type'] != 'table' or table['table'] != 'job_retries' or table['sql'] != expected:
            raise ValueError('Retry schema differs from reviewed migration')
        if index != dict(type='index', table='job_retries', sql=None) or new['tables']['job_retries']['rows'] != 0:
            raise ValueError('New retry table must be empty and have only its implicit key index')
        additions.append(path + ':job_retries')
    return additions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New evidence file, outside work')
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--allow-retry-schema', action='store_true')
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.work.resolve()): parser.error('Evidence must be outside work')
    result = snapshot(args.work)
    additions = verify_preserved(json.loads(args.compare.read_text()), result, allow_retry_schema=args.allow_retry_schema) if args.compare else None
    with args.out.open('x') as stream: json.dump(result, stream, indent=2)
    print(json.dumps(dict(databases=len(result['databases']), files=len(result['files']), allowed_additions=additions)))
