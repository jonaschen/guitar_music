"""Human chord decisions, saved independently of analysis, roots and structure."""
from contextlib import contextmanager
from bisect import bisect_left
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from .song_structure import StructureModel, StructureSource, StructureDocument

EPS = 1e-7
Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_+\-]{1,160}$')]
Symbol = Annotated[str, Field(min_length=1, max_length=64)]


class ChordSegment(StructureModel):
    id: Identifier
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    original_symbol: str | None = Field(default=None, min_length=1, max_length=128)
    symbol: Symbol | None = None
    status: Literal['pending', 'confirmed'] = 'pending'

    @field_validator('symbol')
    @classmethod
    def chord_name(cls, value):
        if value is not None and value != 'N.C.' and not re.fullmatch(
                r'[A-G][#b]?[a-zA-Z0-9+#b()°ø-]*(?:/[A-G][#b]?)?', value):
            raise ValueError('請輸入和弦名稱，例如 C、Am7、G/B 或 N.C.；待聽請留空。')
        return value

    @model_validator(mode='after')
    def valid(self):
        if self.end <= self.start or ((self.status == 'confirmed') != (self.symbol is not None)):
            raise ValueError('和弦狀態或時間範圍不符。')
        if self.original_symbol is not None and any(ord(c) < 32 for c in self.original_symbol):
            raise ValueError('原分析名稱含不支援字元。')
        return self


class ChordDocument(StructureModel):
    schema_version: Literal[1] = 1
    source: StructureSource
    segments: list[ChordSegment] = Field(min_length=1, max_length=6000)

    @model_validator(mode='after')
    def continuous(self):
        cursor, ids = 0., set()
        for segment in self.segments:
            if abs(segment.start - cursor) > EPS or segment.id in ids:
                raise ValueError('和弦區段必須連續且識別碼不可重複。')
            cursor = segment.end; ids.add(segment.id)
        if abs(cursor - self.source.duration) > EPS:
            raise ValueError('和弦工作稿須涵蓋完整原曲。')
        return self


class ChordSave(StructureModel):
    expected_version: int = Field(ge=0)
    structure_version: int = Field(ge=0)
    section_id: Identifier
    document: ChordDocument


class ChordConflict(Exception):
    pass


def initial_document(job, source):
    """Use analysis boundaries as references only. Never guess across overlaps."""
    source = StructureSource.model_validate(source).model_dump(mode='json')
    duration = source['duration']; cursor = 0.; segments = []
    def append(start, end, symbol):
        segments.append(dict(id=f'chord-{len(segments)}', start=start, end=end,
                             original_symbol=symbol, symbol=None, status='pending'))
    rows = sorted(job.score.chords, key=lambda row: row.start)
    for row in rows:
        if (not math.isfinite(row.start + row.end) or row.start < 0 or row.end > duration + EPS
                or row.end <= row.start or row.start < cursor - EPS):
            raise ValueError('原分析和弦時間重疊或不合法，無法建立無歧義的工作稿。')
        start = cursor if abs(row.start - cursor) <= EPS else row.start
        end = min(duration, row.end)
        if start > cursor: append(cursor, start, None)
        append(start, end, row.symbol); cursor = end
    if cursor < duration: append(cursor, duration, None)
    return ChordDocument.model_validate(dict(schema_version=1, source=source, segments=segments)).model_dump(mode='json')


def preserve_scope(before, after, section):
    """Compare time semantics, allowing only in-section edits and boundary cuts."""
    if before['source'] != after['source']:
        raise ChordConflict('和弦工作稿的原曲來源已變動。')
    start, end = section['start'], section['end']
    old, new = before['segments'], after['segments']
    by_id = {s['id']: s for s in new}
    old_boundaries = {s[k] for s in old for k in ('start', 'end')}
    new_boundaries = {s[k] for s in new for k in ('start', 'end')}
    ordered_boundaries = sorted(old_boundaries)
    ordered_new = sorted(new_boundaries)
    for segment in old:
        if segment['end'] <= start + EPS or segment['start'] >= end - EPS:
            if by_id.get(segment['id']) != segment:
                # An undo may join a boundary cut back into its crossing event.
                # Outside cuts and time-wise harmony still remain unchanged.
                joined_at_edge = any(
                    s['start'] <= segment['start'] + EPS and s['end'] >= segment['end'] - EPS and (
                        segment['end'] <= start + EPS and s['start'] < start - EPS and s['end'] > start + EPS or
                        segment['start'] >= end - EPS and s['start'] < end - EPS and s['end'] > end + EPS)
                    for s in new)
                if not joined_at_edge:
                    raise ValueError('不可變更鎖定段落以外的和弦區段。')
    for boundary in old_boundaries:
        if boundary < start - EPS or boundary > end + EPS:
            index = bisect_left(ordered_new, boundary - EPS)
            if index >= len(ordered_new) or abs(boundary - ordered_new[index]) > EPS:
                raise ValueError('不可合併鎖定段落以外的和弦區段。')
    for segment in new:
        for boundary in (segment['start'], segment['end']):
            if boundary < start - EPS or boundary > end + EPS:
                index = bisect_left(ordered_boundaries, boundary - EPS)
                if index >= len(ordered_boundaries) or abs(boundary - ordered_boundaries[index]) > EPS:
                    raise ValueError('不可在鎖定段落以外另行分段。')
    cuts = sorted(old_boundaries | new_boundaries | {start, end})
    i = j = 0
    for a, b in zip(cuts, cuts[1:]):
        if b - a <= EPS: continue
        point = (a + b) / 2
        while old[i]['end'] <= point: i += 1
        while new[j]['end'] <= point: j += 1
        if old[i]['original_symbol'] != new[j]['original_symbol']:
            raise ValueError('原分析和弦只供參考，不可改寫或移動。')
        if point < start or point > end:
            if any(old[i][key] != new[j][key] for key in ('symbol', 'status')):
                raise ValueError('跨界切割必須保留段外原有和聲。')


def read_structure(path, job):
    if not Path(path).is_file(): return None, 0
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        if not has_table(db, 'song_structure'): return None, 0
        row = db.execute('SELECT document,version FROM song_structure WHERE job_id=?', (job,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, 0)


def has_table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


@contextmanager
def structure_guard(path, job, version, section_id):
    if not Path(path).is_file(): raise ChordConflict('請先保存歌曲結構，再鎖定要練習的段落。')
    # Reserve the existing structure DB while reading: works with rollback and
    # WAL journals and prevents a merge between validation and chord commit.
    # query_only forbids data writes after taking the reservation. No DDL/DML.
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('PRAGMA query_only=ON')
        if not has_table(db, 'song_structure'): raise ChordConflict('請先保存歌曲結構，再鎖定範圍。')
        row = db.execute('SELECT document,version FROM song_structure WHERE job_id=?', (job,)).fetchone()
        if row is None or row[1] != version:
            raise ChordConflict('歌曲段落已變動，請保留草稿並重新選取範圍。')
        structure = StructureDocument.model_validate_json(row[0]).model_dump(mode='json')
        section = next((s for s in structure['sections'] if s['id'] == section_id), None)
        if section is None: raise ChordConflict('鎖定的段落已合併或移除，請重新選取。')
        yield structure, section


class ChordPracticeStore:
    def __init__(self, path):
        self.path = Path(path)

    def read(self, job):
        row = None
        if self.path.is_file():
            with sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True) as db:
                if has_table(db, 'chord_practice'):
                    row = db.execute('SELECT document,version,updated_at FROM chord_practice WHERE job_id=?', (job,)).fetchone()
        return dict(job_id=job, document=json.loads(row[0]) if row else None,
                    version=row[1] if row else 0, updated_at=row[2] if row else None)

    def history(self, job):
        if not self.path.is_file(): return []
        with sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            if not has_table(db, 'chord_practice_history'): return []
            return [dict(version=v, document=json.loads(d), updated_at=t) for v, d, t in db.execute(
                'SELECT version,document,updated_at FROM chord_practice_history WHERE job_id=? ORDER BY version DESC LIMIT 50', (job,))]

    def save(self, job, body, source_provider, structure_path):
        document = body.document.model_dump(mode='json')
        with structure_guard(structure_path, job, body.structure_version, body.section_id) as (structure, section):
            source, initial = source_provider()
            source = StructureSource.model_validate(source).model_dump(mode='json')
            if source['job_id'] != job or source != document['source'] or structure['source'] != source:
                raise ChordConflict('和弦稿、歌曲結構與目前錄音來源不符。')
            # Reject invalid initial changes before creating even an empty file.
            if not self.path.exists():
                if body.expected_version != 0: raise ChordConflict('和弦版本已變動，請重新載入。')
                preserve_scope(ChordDocument.model_validate(initial).model_dump(mode='json'), document, section)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS chord_practice (job_id TEXT PRIMARY KEY, document TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS chord_practice_history (job_id TEXT NOT NULL, version INTEGER NOT NULL, document TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(job_id,version))')
                row = db.execute('SELECT document,version,updated_at FROM chord_practice WHERE job_id=?', (job,)).fetchone()
                if (row[1] if row else 0) != body.expected_version:
                    raise ChordConflict('其他分頁已更新和弦；請保留草稿並載入最新版本。')
                before = ChordDocument.model_validate_json(row[0]).model_dump(mode='json') if row else ChordDocument.model_validate(initial).model_dump(mode='json')
                preserve_scope(before, document, section)
                if row:
                    db.execute('INSERT INTO chord_practice_history VALUES (?,?,?,?)', (job,row[1],row[0],row[2]))
                now = datetime.now(timezone.utc).isoformat()
                db.execute('INSERT INTO chord_practice VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET document=excluded.document, version=excluded.version, updated_at=excluded.updated_at',
                           (job, body.document.model_dump_json(), body.expected_version+1, now))
        return dict(job_id=job, document=document, version=body.expected_version+1, updated_at=now)
