"""Explicit same-song root reuse on a saved grid, with an atomic undo ledger."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from typing import Annotated
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .root_practice import PracticeDocument, PracticeConflict
from .song_structure import StructureSource

EPS = 1e-7
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
SegmentId = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')]
STATUSES = ('fillable', 'already_same', 'target_protected', 'source_unknown', 'source_changes')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ReuseRange(StrictModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def positive(self):
        if self.end <= self.start: raise ValueError('範圍終點必須晚於起點。')
        return self


class ReuseUndo(StrictModel):
    expected_version: int = Field(ge=0)
    fingerprint: Digest
    audio_sha256: Digest


class ReuseRequest(ReuseUndo):
    source_range: ReuseRange
    target_range: ReuseRange
    alignment_confirmed: bool = False
    source_label: str = Field(default='', max_length=120)
    target_label: str = Field(default='', max_length=120)


class ReuseApply(StrictModel):
    plan_id: Digest
    request: ReuseRequest
    selected_target_ids: list[SegmentId] = Field(min_length=1, max_length=6000)

    @model_validator(mode='after')
    def unique(self):
        if len(self.selected_target_ids) != len(set(self.selected_target_ids)):
            raise ValueError('沿用目標不可重複。')
        return self


class ReuseNotFound(LookupError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def signature(document, span):
    return digest(dict(source=document['source'], grid=document.get('grid'), span=span,
                       segments=[s for s in document['segments']
                                 if s['start'] < span['end'] - EPS and s['end'] > span['start'] + EPS]))


def _source_matches(document, source):
    return bool(document and source and document['source'] == {k: v for k, v in source.items() if k != 'audio_sha256'})


def _check_source(job, document, request, source):
    source = StructureSource.model_validate(source).model_dump(mode='json')
    if (source['job_id'] != job or request.fingerprint != source['fingerprint']
            or request.audio_sha256 != source['audio_sha256'] or not _source_matches(document, source)):
        raise PracticeConflict('原曲或根音來源已變動，請重新載入後再預覽。')
    return source


def build_plan(job, document, version, request):
    document = PracticeDocument.model_validate(document).model_dump(mode='json')
    if version != request.expected_version: raise PracticeConflict('根音版本已更新，請重新預覽。')
    if document['schema_version'] != 2 or not document.get('grid'):
        raise ValueError('請先預覽並套用小節拍格，再沿用根音。')
    grid = document['grid']; beat = 60 / grid['bpm']; bar = beat * grid['beats']
    a, b = request.source_range, request.target_range
    for span in (a, b):
        if span.end > document['source']['duration'] + EPS:
            raise ValueError('沿用範圍超出原曲。')
        for point in (span.start, span.end):
            aligned = grid['anchor'] + round((point - grid['anchor']) / bar) * bar
            if abs(point - aligned) > EPS: raise ValueError('請選擇落在完整小節邊界的範圍。')
    if abs((a.end - a.start) - (b.end - b.start)) > EPS:
        raise ValueError('來源與目標須選相同拍數；不同結尾請留在範圍外。')
    if max(a.start, b.start) < min(a.end, b.end) - EPS:
        raise ValueError('來源與目標範圍不可重疊。')
    bars = round((a.end - a.start) / bar)
    if bars < 1: raise ValueError('至少選擇一個完整小節。')
    rows = []
    for target in document['segments']:
        if target['start'] >= b.end - EPS or target['end'] <= b.start + EPS: continue
        if target['start'] < b.start - EPS or target['end'] > b.end + EPS:
            raise ValueError('目標根音跨越沿用邊界，請先調整範圍。')
        start, end = a.start + target['start'] - b.start, a.start + target['end'] - b.start
        sources = [s for s in document['segments'] if s['start'] < end - EPS and s['end'] > start + EPS]
        coverage = sum(min(end, s['end']) - max(start, s['start']) for s in sources)
        roots = {s['root'] for s in sources if s['status'] == 'confirmed'}
        unknown = abs(coverage - (end - start)) > EPS or any(s['status'] != 'confirmed' for s in sources)
        root = next(iter(roots)) if not unknown and len(roots) == 1 else None
        if target['status'] == 'confirmed' and root is not None and target['root'] == root:
            status = 'already_same'
        elif target['status'] != 'pending': status = 'target_protected'
        elif unknown: status = 'source_unknown'
        elif len(roots) != 1: status = 'source_changes'
        else: status = 'fillable'
        rows.append(dict(target_id=target['id'], start=target['start'], end=target['end'],
                         source_ids=[s['id'] for s in sources], root=root, status=status))
    counts = {status: sum(row['status'] == status for row in rows) for status in STATUSES}
    base = digest(document); body = request.model_dump(mode='json')
    plan_id = digest(dict(method='root-reuse-v1', document_digest=base, request=body, rows=rows))
    return dict(job_id=job, version=version, plan_id=plan_id, document_digest=base,
                request=body, grid=grid, beat_count=bars * grid['beats'], rows=rows, counts=counts,
                can_apply=request.alignment_confirmed and counts['fillable'] > 0)


def _has_ledger(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='root_reuse_ledger'").fetchone() is not None


def _create_ledger(db):
    db.execute('CREATE TABLE IF NOT EXISTS root_reuse_ledger ('
               'job_id TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, '
               'applied_version INTEGER NOT NULL, undone_version INTEGER, PRIMARY KEY(job_id,id))')


def _entry(payload, undone_version, document, live_source):
    entry = deepcopy(payload)
    entry['undone_version'] = undone_version
    entry['status'] = 'undone' if undone_version is not None else 'applied'
    matches = bool(_source_matches(document, live_source) and live_source == payload['source']
                   and document.get('grid') == payload['grid'])
    by_id = {s['id']: s for s in document['segments']} if document else {}
    target_matches = matches and all(by_id.get(c['target_id']) == c['after'] for c in payload['changes'])
    mapping_matches = bool(matches and signature(document, payload['request']['source_range']) == payload['source_signature']
                           and signature(document, payload['request']['target_range']) == payload['target_signature'])
    entry.update(target_matches=bool(target_matches), mapping_matches=mapping_matches,
                 can_undo=bool(target_matches and undone_version is None),
                 fully_equivalent=bool(payload['fully_equivalent'] and mapping_matches and undone_version is None))
    return entry


class RootReuseService:
    def __init__(self, store):
        self.store = store

    def plan(self, job, request, source):
        snapshot = self.store.read(job)
        if snapshot['document'] is None: raise ValueError('請先保存根音稿，再預覽沿用。')
        _check_source(job, snapshot['document'], request, source)
        return build_plan(job, snapshot['document'], snapshot['version'], request)

    def apply(self, job, body, source_provider):
        def change(document, db, version, now):
            source = _check_source(job, document, body.request, source_provider())
            plan = build_plan(job, document, version - 1, body.request)
            if plan['plan_id'] != body.plan_id: raise PracticeConflict('沿用預覽已變動，請重新比較。')
            if not plan['can_apply']: raise ValueError('請先確認對齊，再選擇可沿用的空白目標。')
            selected = set(body.selected_target_ids)
            fillable = {r['target_id']: r for r in plan['rows'] if r['status'] == 'fillable'}
            if not selected or not selected.issubset(fillable):
                raise ValueError('只能沿用預覽中尚未填寫且可沿用的目標。')
            next_doc = deepcopy(document); changes = []
            for segment in next_doc['segments']:
                if segment['id'] not in selected: continue
                before = deepcopy(segment)
                segment.update(root=fillable[segment['id']]['root'], status='confirmed')
                changes.append(dict(target_id=segment['id'], before=before, after=deepcopy(segment)))
            source_ids = list(dict.fromkeys(i for row in plan['rows'] if row['target_id'] in selected for i in row['source_ids']))
            complete = all(row['status'] == 'already_same' or row['status'] == 'fillable' and row['target_id'] in selected
                           for row in plan['rows'])
            payload = dict(id=uuid.uuid4().hex, created_at=now, applied_version=version,
                           request=body.request.model_dump(mode='json'), grid=document['grid'], source=source,
                           source_signature=signature(document, plan['request']['source_range']),
                           target_signature=signature(next_doc, plan['request']['target_range']),
                           source_ids=source_ids, target_ids=[c['target_id'] for c in changes],
                           changes=changes, fully_equivalent=complete)
            _create_ledger(db)
            db.execute('INSERT INTO root_reuse_ledger VALUES (?,?,?,?,NULL)',
                       (job, payload['id'], json.dumps(payload, ensure_ascii=False, allow_nan=False), version))
            return next_doc, _entry(payload, None, next_doc, source)
        snapshot, operation = self.store.mutate(job, body.request.expected_version, change)
        return dict(snapshot=snapshot, operation=operation)

    def ledger(self, job, source=None):
        with sqlite3.connect(self.store.path) as db:
            db.execute('BEGIN')
            row = db.execute('SELECT document,version FROM root_practice WHERE job_id=?', (job,)).fetchone()
            document, version = (json.loads(row[0]), row[1]) if row else (None, 0)
            rows = db.execute('SELECT payload,undone_version FROM root_reuse_ledger WHERE job_id=? '
                              'ORDER BY applied_version DESC LIMIT 200', (job,)).fetchall() if _has_ledger(db) else []
        payloads = [(json.loads(payload), undone) for payload, undone in rows]
        matches = bool(source and source.get('job_id') == job and (
            document is None and not payloads or
            _source_matches(document, source) and (not payloads or payloads[0][0]['source'] == source)))
        return dict(job_id=job, version=version, source_matches=matches,
                    operations=[_entry(payload, undone, document, source) for payload, undone in payloads])

    def undo(self, job, operation_id, body, source_provider):
        def change(document, db, version, now):
            source = _check_source(job, document, body, source_provider())
            row = db.execute('SELECT payload,undone_version FROM root_reuse_ledger WHERE job_id=? AND id=?',
                             (job, operation_id)).fetchone() if _has_ledger(db) else None
            if row is None: raise ReuseNotFound('找不到這筆沿用紀錄。')
            payload, undone = json.loads(row[0]), row[1]
            entry = _entry(payload, undone, document, source)
            if not entry['can_undo']:
                raise PracticeConflict('這批目標、拍格或來源已變更，或已撤銷；未修改任何根音。')
            before = {c['target_id']: c['before'] for c in payload['changes']}
            next_doc = {**document, 'segments': [deepcopy(before.get(s['id'], s)) for s in document['segments']]}
            db.execute('UPDATE root_reuse_ledger SET undone_version=? WHERE job_id=? AND id=?',
                       (version, job, operation_id))
            return next_doc, _entry(payload, version, next_doc, source)
        snapshot, operation = self.store.mutate(job, body.expected_version, change)
        return dict(snapshot=snapshot, operation=operation)
