"""Versioned per-source lyric/handwritten notation sheets, separate from score/notes."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator


class WorksheetAnchor(BaseModel):
    model_config=ConfigDict(extra='forbid')
    time:float=Field(ge=0,allow_inf_nan=False)
    end:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    source_start_seconds:float=Field(ge=0,allow_inf_nan=False)
    duration_seconds:float=Field(gt=0,allow_inf_nan=False)
    kind:Literal['seconds','metered','local']
    grid_id:str|None=Field(default=None,max_length=80)

    @model_validator(mode='after')
    def within_source(self):
        if self.time>=self.duration_seconds or self.end is not None and (self.end<=self.time or self.end>self.duration_seconds):raise ValueError('Anchor outside source')
        if self.kind!='seconds' and not self.grid_id:raise ValueError('Missing grid identity')
        return self


class WorksheetLine(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    lyric:str=Field(default='',max_length=2000)
    notation:str=Field(default='',max_length=2000)
    anchor:WorksheetAnchor|None=None
    start:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    end:float|None=Field(default=None,ge=0,allow_inf_nan=False)

    @model_validator(mode='after')
    def ordered(self):
        if self.start is not None and self.end is not None and self.end<=self.start:raise ValueError('Invalid line interval')
        return self


class WorksheetDocument(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source:str=Field(default='',max_length=500)
    lines:list[WorksheetLine]=Field(default_factory=list,max_length=400)

    @model_validator(mode='after')
    def unique_and_bounded(self):
        if len({r.id for r in self.lines})!=len(self.lines):raise ValueError('Duplicate lyric line IDs')
        if sum(len(r.lyric)+len(r.notation) for r in self.lines)+len(self.source)>160000:raise ValueError('Worksheet too large')
        return self


class WorksheetSave(BaseModel):
    anchor_schema:Literal[1]|None=None
    document:WorksheetDocument
    expected_version:int=Field(ge=0)


class WorksheetConflict(Exception):pass
class WorksheetUpgradeRequired(WorksheetConflict):pass


class LyricWorksheetStore:
    def __init__(self,path:Path):
        self.path=path;path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS lyric_worksheets (job_id TEXT PRIMARY KEY, document TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)')

    def read(self,job_id):
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT document,version,updated_at FROM lyric_worksheets WHERE job_id=?',(job_id,)).fetchone()
        return dict(job_id=job_id,document=json.loads(row[0]) if row else WorksheetDocument().model_dump(),version=row[1] if row else 0,updated_at=row[2] if row else None)

    def save(self,job_id,document,expected_version,anchor_schema=None):
        validated=WorksheetDocument.model_validate(document)
        omitted_anchors={line.id for line in validated.lines if 'anchor' not in line.model_fields_set}
        document=validated.model_dump();now=datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT version,document FROM lyric_worksheets WHERE job_id=?',(job_id,)).fetchone()
            if (row[0] if row else 0)!=expected_version:raise WorksheetConflict()
            previous=json.loads(row[1]) if row else {'lines':[]}
            if anchor_schema!=1 and any(line.get('anchor') is not None for line in [*previous['lines'],*document['lines']]):raise WorksheetUpgradeRequired()
            if any(line.get('anchor') is not None and line['id'] in omitted_anchors for line in previous['lines']):raise WorksheetUpgradeRequired()
            version=expected_version+1
            db.execute('INSERT INTO lyric_worksheets VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET document=excluded.document,version=excluded.version,updated_at=excluded.updated_at',(job_id,json.dumps(document,ensure_ascii=False),version,now))
        return dict(job_id=job_id,document=document,version=version,updated_at=now)
