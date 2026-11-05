"""Shared per-source text notes, independent of score revisions and musical edits."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class NoteConflict(Exception):
    pass


class MelodyNoteStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS melody_notes (job_id TEXT PRIMARY KEY, text TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)')

    def read(self, job_id):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT text,version,updated_at FROM melody_notes WHERE job_id=?', (job_id,)).fetchone()
        return dict(job_id=job_id, text=row[0] if row else '', version=row[1] if row else 0, updated_at=row[2] if row else None)

    def save(self, job_id, text, expected_version):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT version FROM melody_notes WHERE job_id=?', (job_id,)).fetchone()
            if (row[0] if row else 0) != expected_version:
                raise NoteConflict()
            version = expected_version + 1
            db.execute('INSERT INTO melody_notes VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET text=excluded.text,version=excluded.version,updated_at=excluded.updated_at', (job_id,text,version,now))
        return dict(job_id=job_id,text=text,version=version,updated_at=now)
