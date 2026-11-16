"""Source-bound song structure documents, independent of root practice and Score.

The document itself is the export/import format. Server versions belong only to
snapshots: importing an old document is a new compare-and-swap save.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .root_practice import source_for_job as root_source_for_job


Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_+\-]{1,160}$')]
Time = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Label = Literal['intro', 'verse', 'prechorus', 'chorus', 'bridge', 'outro', 'inst',
                'solo', 'break', 'start', 'end', 'unknown', 'closing', 'custom']


class StructureModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class StructureSource(StructureModel):
    job_id: str = Field(min_length=1, max_length=100)
    fingerprint: Digest
    audio_sha256: Digest
    duration: float = Field(gt=0, le=7200, allow_inf_nan=False)
    source_start: Time


class ModelSection(StructureModel):
    id: Identifier
    start: Time
    end: Time
    label: Label
    model_end: Time | None = None
    original_number: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def valid_range(self):
        if self.end <= self.start or self.model_end is not None and self.model_end <= self.start:
            raise ValueError('Original model intervals must have positive length')
        return self


class StructureSection(StructureModel):
    id: Identifier
    start: Time
    end: Time
    label: Label
    display_label: str = Field(min_length=1, max_length=120)
    name_review_status: Literal['unreviewed', 'user_corrected', 'user_confirmed', 'tentative'] = 'unreviewed'
    boundary_review_status: Literal['unreviewed', 'user_confirmed'] = 'unreviewed'
    model_sections: list[ModelSection] = Field(default_factory=list, max_length=2000)
    note: str = Field(default='', max_length=2000)

    @field_validator('display_label')
    @classmethod
    def nonblank_label(cls, value):
        if not value.strip():
            raise ValueError('A display label cannot be blank')
        return value

    @model_validator(mode='after')
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError('Structure intervals must have positive length')
        ids = [s.id for s in self.model_sections]
        if len(ids) != len(set(ids)):
            raise ValueError('An original model section may only be referenced once per section')
        return self


class StructureDocument(StructureModel):
    schema_version: Literal[1] = 1
    source: StructureSource
    candidate_sha256: Digest | None = None
    sections: list[StructureSection] = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def complete_intervals(self):
        cursor = 0.
        ids = set()
        originals = {}
        references = 0
        for section in self.sections:
            if section.id in ids or abs(section.start - cursor) > 1e-7:
                raise ValueError('Sections must be ordered, continuous and have unique IDs')
            if section.end > self.source.duration + 1e-7:
                raise ValueError('Sections exceed source duration')
            ids.add(section.id)
            cursor = section.end
            references += len(section.model_sections)
            for original in section.model_sections:
                # Model frame rounding may overshoot; editable bounds remain exact.
                if (original.end > self.source.duration + .05
                        or original.model_end is not None and original.model_end > self.source.duration + .05):
                    raise ValueError('Original model interval exceeds source duration')
                previous = originals.get(original.id)
                if previous is not None and previous != original:
                    raise ValueError('Conflicting copies of an original model section')
                originals[original.id] = original
        if abs(cursor - self.source.duration) > 1e-7:
            raise ValueError('Structure must cover the entire source')
        if references > 20000:
            raise ValueError('Too many original model section references')
        if originals and self.candidate_sha256 is None:
            raise ValueError('Original model sections require their candidate digest')
        return self


class StructureSave(StructureModel):
    expected_version: int = Field(ge=0)
    document: StructureDocument


class StructureConflict(Exception):
    """The saved version or source changed; the caller must retain its draft."""


def source_and_audio_for_job(job, directory: Path) -> tuple[StructureSource, Path]:
    """Hash the same local audio selected for root-practice playback.

    A cropped recording is already source-local, including when its offset is 0.
    Multiple full inputs are ambiguous and never selected by filesystem order.
    """
    root_source = root_source_for_job(job)
    cropped = getattr(job, 'skip_seconds', 0) > 0 or getattr(job, 'analysis_seconds', None) is not None
    paths = [directory / 'analysis-source.wav'] if cropped else sorted(directory.glob('input.*'))
    paths = [p for p in paths if p.is_file()]
    if not paths:
        raise FileNotFoundError('Source audio is unavailable')
    if len(paths) != 1:
        raise StructureConflict('Source audio is ambiguous')
    path = paths[0]
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise StructureConflict('Source audio changed while reading')
    return StructureSource(**root_source.model_dump(), audio_sha256=digest.hexdigest()), path


def source_for_job(job, directory: Path) -> StructureSource:
    return source_and_audio_for_job(job, directory)[0]


class SongStructureStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS song_structure ('
                       'job_id TEXT PRIMARY KEY, document TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS song_structure_history ('
                       'job_id TEXT NOT NULL, version INTEGER NOT NULL, document TEXT NOT NULL, '
                       'updated_at TEXT NOT NULL, PRIMARY KEY(job_id, version))')

    def read(self, job_id: str) -> dict:
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT document, version, updated_at FROM song_structure WHERE job_id=?', (job_id,)).fetchone()
        return dict(job_id=job_id, version=row[1] if row else 0,
                    document=json.loads(row[0]) if row else None, updated_at=row[2] if row else None)

    def history(self, job_id: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute('SELECT version, document, updated_at FROM song_structure_history '
                              'WHERE job_id=? ORDER BY version DESC LIMIT 50', (job_id,)).fetchall()
        return [dict(version=v, document=json.loads(d), updated_at=t) for v, d, t in rows]

    def save(self, job_id: str, document, expected_version: int) -> dict:
        document = StructureDocument.model_validate(document)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError('Expected version must be a nonnegative integer')
        if document.source.job_id != job_id:
            raise ValueError('Source job does not match')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document, version, updated_at FROM song_structure WHERE job_id=?', (job_id,)).fetchone()
            if (row[1] if row else 0) != expected_version:
                raise StructureConflict('The structure was updated in another tab')
            if row:
                previous = StructureDocument.model_validate_json(row[0])
                if previous.source != document.source:
                    raise StructureConflict('The structure source changed')
                db.execute('INSERT INTO song_structure_history VALUES (?, ?, ?, ?)',
                           (job_id, row[1], row[0], row[2]))
            now = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO song_structure VALUES (?, ?, ?, ?) '
                       'ON CONFLICT(job_id) DO UPDATE SET document=excluded.document, '
                       'version=excluded.version, updated_at=excluded.updated_at',
                       (job_id, document.model_dump_json(), expected_version + 1, now))
        return dict(job_id=job_id, version=expected_version + 1,
                    document=document.model_dump(mode='json'), updated_at=now)
