"""Independent, versioned human root decisions. Never rewrites SongScore."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .root_candidates import initial_segments


class PracticeSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(min_length=1, max_length=100)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    duration: float = Field(gt=0, le=7200, allow_inf_nan=False)
    source_start: float = Field(ge=0, allow_inf_nan=False)


class RootSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    original_root: int | None = Field(default=None, ge=0, le=11, strict=True)
    root: int | None = Field(default=None, ge=0, le=11, strict=True)
    status: Literal['pending', 'confirmed', 'unsure'] = 'pending'

    @model_validator(mode='after')
    def valid(self):
        if self.end <= self.start or ((self.status == 'confirmed') != (self.root is not None)):
            raise ValueError('Invalid root decision')
        return self


class PracticeDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    source: PracticeSource
    segments: list[RootSegment] = Field(min_length=1, max_length=6000)

    @model_validator(mode='after')
    def continuous(self):
        cursor = 0.
        ids = set()
        for s in self.segments:
            if abs(s.start - cursor) > 1e-7 or s.id in ids:
                raise ValueError('Root practice intervals must be continuous and unique')
            cursor = s.end; ids.add(s.id)
        if abs(cursor - self.source.duration) > 1e-7:
            raise ValueError('Root practice must cover the source duration')
        return self


class PracticeSave(BaseModel):
    expected_version: int = Field(ge=0)
    document: PracticeDocument


def source_for_job(job):
    score = job.score.model_dump(mode='json')
    identity = {'job_id': job.id, 'song': score['song'], 'chords': score['chords'], 'provenance': score['provenance']}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return PracticeSource(job_id=job.id, fingerprint=digest, duration=job.score.song.duration_seconds,
                          source_start=job.score.song.source_start_seconds)


def initial_document(job):
    return PracticeDocument(source=source_for_job(job), segments=initial_segments(job.score.model_dump(mode='json')))


class PracticeConflict(Exception):
    pass


class RootPracticeStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS root_practice (job_id TEXT PRIMARY KEY, document TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)')

    def read(self, job_id):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT document,version,updated_at FROM root_practice WHERE job_id=?', (job_id,)).fetchone()
        return dict(job_id=job_id, document=json.loads(row[0]) if row else None, version=row[1] if row else 0,
                    updated_at=row[2] if row else None)

    def save(self, job_id, document, expected_version):
        document = PracticeDocument.model_validate(document)
        if document.source.job_id != job_id:
            raise ValueError('Source mismatch')
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document,version FROM root_practice WHERE job_id=?', (job_id,)).fetchone()
            if (row[1] if row else 0) != expected_version:
                raise PracticeConflict()
            if row and PracticeDocument.model_validate_json(row[0]).source != document.source:
                raise ValueError('Source fingerprint changed')
            db.execute('INSERT INTO root_practice VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET document=excluded.document,version=excluded.version,updated_at=excluded.updated_at',
                       (job_id, document.model_dump_json(), expected_version + 1, now))
        return dict(job_id=job_id, document=document.model_dump(mode='json'), version=expected_version+1, updated_at=now)
