"""Explicit offset-based chord reuse; one transaction for draft, history and undo."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Annotated
import uuid

from pydantic import Field, model_validator

from .chord_practice import (ChordConflict, ChordDocument, Identifier, EPS,
                             has_table, read_structure, structure_guard, preserve_scope)
from .song_structure import StructureModel, StructureSource

Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
STATUSES = ('fillable', 'already_same', 'target_protected', 'source_unknown')


class ReuseRange(StructureModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def positive(self):
        if self.end - self.start <= EPS: raise ValueError('範圍終點必須晚於起點。')
        return self


class ReuseUndo(StructureModel):
    expected_version: int = Field(ge=0)
    structure_version: int = Field(ge=0)
    fingerprint: Digest
    audio_sha256: Digest


class ReuseRequest(ReuseUndo):
    source_section_id: Identifier
    target_section_id: Identifier
    source_range: ReuseRange
    target_range: ReuseRange
    alignment_confirmed: bool = False


class ReuseApply(StructureModel):
    plan_id: Digest
    request: ReuseRequest
    selected_row_ids: list[Digest] = Field(min_length=1, max_length=6000)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.selected_row_ids)) != len(self.selected_row_ids):
            raise ValueError('沿用切片不可重複。')
        return self


class ReuseNotFound(LookupError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check_sections(structure, request):
    if request.source_section_id == request.target_section_id:
        raise ValueError('請選擇兩個不同的歌曲段落。')
    for key, span in ((request.source_section_id, request.source_range),
                      (request.target_section_id, request.target_range)):
        section = next((s for s in structure['sections'] if s['id'] == key), None)
        if section is None: raise ChordConflict('沿用段落已移除，請重新選取。')
        if span.start < section['start'] - EPS or span.end > section['end'] + EPS:
            raise ValueError('核心範圍必須完整位於所選歌曲段落內。')
    a, b = request.source_range, request.target_range
    if abs(a.end-a.start-(b.end-b.start)) > EPS:
        raise ValueError('兩個核心範圍必須等長；不同結尾請留在範圍外。')
    if max(a.start,b.start) < min(a.end,b.end)-EPS:
        raise ValueError('來源與目標核心範圍不可重疊。')


def check_source(job, document, structure, request, source):
    source = StructureSource.model_validate(source).model_dump(mode='json')
    if (source['job_id'] != job or document['source'] != source or structure['source'] != source
            or request.fingerprint != source['fingerprint'] or request.audio_sha256 != source['audio_sha256']):
        raise ChordConflict('和弦稿、歌曲結構或錄音來源已變動，請重新載入。')
    return source


def build_plan(job, document, version, structure, request):
    document = ChordDocument.model_validate(document).model_dump(mode='json')
    if version != request.expected_version: raise ChordConflict('和弦版本已更新，請重新預覽。')
    check_sections(structure, request)
    a, b = request.source_range, request.target_range
    offset = b.start-a.start; rows=[]; index=0
    segments = document['segments']
    for target in segments:
        left, right = max(target['start'],b.start), min(target['end'],b.end)
        if right-left <= EPS: continue
        while index < len(segments) and segments[index]['end']+offset <= left+EPS: index+=1
        cursor=index
        while cursor < len(segments) and segments[cursor]['start']+offset < right-EPS:
            origin=segments[cursor]
            start=max(left,origin['start']+offset); end=min(right,origin['end']+offset)
            symbol=origin['symbol'] if origin['status']=='confirmed' else None
            if target['status']=='confirmed':
                status='already_same' if symbol is not None and target['symbol']==symbol else 'target_protected'
            else: status='fillable' if symbol is not None else 'source_unknown'
            rows.append(dict(id=digest([target['id'],origin['id'],start,end]),target_id=target['id'],
                source_ids=[origin['id']],start=start,end=end,source_start=start-offset,source_end=end-offset,
                symbol=symbol,status=status))
            cursor+=1
    counts={status:sum(r['status']==status for r in rows) for status in STATUSES}
    body=request.model_dump(mode='json')
    plan_id=digest(dict(method='chord-reuse-v1',document=document,structure=structure,request=body,rows=rows))
    return dict(job_id=job,version=version,structure_version=request.structure_version,plan_id=plan_id,
        request=body,rows=rows,counts=counts,can_apply=request.alignment_confirmed and counts['fillable']>0)


def patch(document, rows):
    by_target={}
    for row in rows: by_target.setdefault(row['target_id'],[]).append(row)
    result=deepcopy(document); segments=[]; changes=[]
    for segment in document['segments']:
        selected=by_target.get(segment['id'],[])
        if not selected:
            segments.append(deepcopy(segment)); continue
        cuts=sorted({segment['start'],segment['end'],*(r[k] for r in selected for k in ('start','end'))})
        for start,end in zip(cuts,cuts[1:]):
            if end-start <= EPS: continue
            part={**segment,'start':start,'end':end}
            if len(cuts)>2: part['id']='reuse-'+digest([segment['id'],start,end])[:40]
            row=next((r for r in selected if r['start']<=start+EPS and r['end']>=end-EPS),None)
            if row:
                before=deepcopy(part); part.update(symbol=row['symbol'],status='confirmed')
                changes.append(dict(row_id=row['id'],before=before,after=deepcopy(part)))
            segments.append(part)
    result['segments']=segments
    return ChordDocument.model_validate(result).model_dump(mode='json'),changes


def entry(payload, undone, document, source, structure):
    result=deepcopy(payload); valid=False
    if document and source and structure and document['source']==source==structure['source']==payload['source']:
        try:
            check_sections(structure,ReuseRequest.model_validate(payload['request'])); valid=True
        except (ValueError,ChordConflict): pass
    by_id={s['id']:s for s in document['segments']} if document else {}
    unchanged=valid and all(by_id.get(c['after']['id'])==c['after'] for c in payload['changes'])
    result.update(undone_version=undone,status='undone' if undone is not None else 'applied',
                  can_undo=bool(unchanged and undone is None))
    return result


class ChordReuseService:
    def __init__(self, store, structure_path):
        self.store=store; self.structure_path=structure_path

    @contextmanager
    def transaction(self, job, version):
        if not self.store.path.is_file(): raise ValueError('請先保存和弦工作稿，再沿用。')
        with sqlite3.connect(self.store.path.resolve().as_uri()+'?mode=rw',uri=True) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT document,version,updated_at FROM chord_practice WHERE job_id=?',(job,)).fetchone() if has_table(db,'chord_practice') else None
            if row is None: raise ValueError('請先保存和弦工作稿，再沿用。')
            if row[1]!=version: raise ChordConflict('和弦版本已更新，請重新預覽。')
            document=ChordDocument.model_validate_json(row[0]).model_dump(mode='json')
            yield db,row,document

    @staticmethod
    def commit(db, job, row, document):
        validated=ChordDocument.model_validate(document)
        now=datetime.now(timezone.utc).isoformat(); version=row[1]+1
        db.execute('INSERT INTO chord_practice_history VALUES (?,?,?,?)',(job,row[1],row[0],row[2]))
        db.execute('UPDATE chord_practice SET document=?,version=?,updated_at=? WHERE job_id=?',
                   (validated.model_dump_json(),version,now,job))
        return dict(job_id=job,document=validated.model_dump(mode='json'),version=version,updated_at=now)

    def plan(self, job, request, source_provider):
        with structure_guard(self.structure_path,job,request.structure_version,request.target_section_id) as (structure,_):
            snapshot=self.store.read(job)
            if snapshot['document'] is None: raise ValueError('請先保存和弦工作稿，再沿用。')
            check_source(job,snapshot['document'],structure,request,source_provider())
            return build_plan(job,snapshot['document'],snapshot['version'],structure,request)

    def apply(self, job, body, source_provider):
        request=body.request
        with structure_guard(self.structure_path,job,request.structure_version,request.target_section_id) as (structure,section):
            with self.transaction(job,request.expected_version) as (db,row,document):
                source=check_source(job,document,structure,request,source_provider())
                preview=build_plan(job,document,row[1],structure,request)
                if preview['plan_id']!=body.plan_id: raise ChordConflict('沿用預覽已變動，請重新比較。')
                fillable={r['id']:r for r in preview['rows'] if r['status']=='fillable'}
                if not preview['can_apply'] or not set(body.selected_row_ids).issubset(fillable):
                    raise ValueError('請先確認回聽對齊，且只能選擇可沿用的空白切片。')
                next_doc,changes=patch(document,[fillable[i] for i in body.selected_row_ids])
                preserve_scope(document,next_doc,section)
                snapshot=self.commit(db,job,row,next_doc)
                payload=dict(id=uuid.uuid4().hex,created_at=snapshot['updated_at'],applied_version=snapshot['version'],
                    source=source,request=request.model_dump(mode='json'),changes=changes)
                db.execute('CREATE TABLE IF NOT EXISTS chord_reuse_ledger (job_id TEXT NOT NULL,id TEXT NOT NULL,'
                    'payload TEXT NOT NULL,applied_version INTEGER NOT NULL,undone_version INTEGER,PRIMARY KEY(job_id,id))')
                db.execute('INSERT INTO chord_reuse_ledger VALUES (?,?,?,?,NULL)',
                    (job,payload['id'],json.dumps(payload,ensure_ascii=False,allow_nan=False),snapshot['version']))
                operation=entry(payload,None,next_doc,source,structure)
        return dict(snapshot=snapshot,operation=operation)

    def ledger(self, job, source_provider):
        source=source_provider(); structure,_=read_structure(self.structure_path,job)
        document=None; version=0; rows=[]
        if self.store.path.is_file():
            with sqlite3.connect(self.store.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                db.execute('BEGIN')
                row=db.execute('SELECT document,version FROM chord_practice WHERE job_id=?',(job,)).fetchone() if has_table(db,'chord_practice') else None
                if row: document,version=json.loads(row[0]),row[1]
                if has_table(db,'chord_reuse_ledger'):
                    rows=db.execute('SELECT payload,undone_version FROM chord_reuse_ledger WHERE job_id=? ORDER BY applied_version DESC LIMIT 200',(job,)).fetchall()
        matches=bool(document and source and structure and document['source']==source==structure['source'])
        return dict(job_id=job,version=version,source_matches=matches,
            operations=[entry(json.loads(payload),undone,document,source,structure) for payload,undone in rows])

    def undo(self, job, operation_id, body, source_provider):
        # Obtain immutable mapping metadata without creating a DB. All validity
        # and after-image checks are repeated under structure -> chord locks.
        saved=None
        if self.store.path.is_file():
            with sqlite3.connect(self.store.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                if has_table(db,'chord_reuse_ledger'):
                    saved=db.execute('SELECT payload FROM chord_reuse_ledger WHERE job_id=? AND id=?',(job,operation_id)).fetchone()
        if saved is None: raise ReuseNotFound('找不到這筆沿用紀錄。')
        request=ReuseRequest.model_validate(json.loads(saved[0])['request'])
        with structure_guard(self.structure_path,job,body.structure_version,request.target_section_id) as (structure,section):
            with self.transaction(job,body.expected_version) as (db,row,document):
                source=check_source(job,document,structure,body,source_provider())
                saved=db.execute('SELECT payload,undone_version FROM chord_reuse_ledger WHERE job_id=? AND id=?',(job,operation_id)).fetchone()
                if saved is None: raise ReuseNotFound('找不到這筆沿用紀錄。')
                payload,undone=json.loads(saved[0]),saved[1]
                if not entry(payload,undone,document,source,structure)['can_undo']:
                    raise ChordConflict('這批目標、錄音或段落已變更，或已撤銷；未修改和弦。')
                before={c['after']['id']:c['before'] for c in payload['changes']}
                next_doc={**document,'segments':[deepcopy(before.get(s['id'],s)) for s in document['segments']]}
                preserve_scope(document,next_doc,section)
                snapshot=self.commit(db,job,row,next_doc)
                db.execute('UPDATE chord_reuse_ledger SET undone_version=? WHERE job_id=? AND id=?',
                    (snapshot['version'],job,operation_id))
                operation=entry(payload,snapshot['version'],next_doc,source,structure)
        return dict(snapshot=snapshot,operation=operation)
