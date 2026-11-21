"""Source-bound learning hypotheses; no inference or mutation of other music drafts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .song_structure import StructureModel, StructureSource, Identifier, Time


class Evidence(StructureModel):
    start: Time
    end: Time
    note: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def positive(self):
        if self.end<=self.start: raise ValueError('Evidence needs a positive duration')
        return self


class Hypothesis(StructureModel):
    tonic: Annotated[str, Field(pattern=r'^[A-G][#b]?$')] | None = None
    mode: Literal['major','minor','unknown','other'] = 'unknown'
    note: str = Field(default='',max_length=2000)
    evidence: list[Evidence] = Field(default_factory=list,max_length=20)


class LocalHypothesis(Hypothesis):
    id: Identifier
    start: Time
    end: Time
    title: str = Field(default='',max_length=120)


class LearningDocument(StructureModel):
    schema_version: Literal[1] = 1
    source: StructureSource
    song: Hypothesis = Field(default_factory=Hypothesis)
    local: list[LocalHypothesis] = Field(default_factory=list,max_length=200)

    @model_validator(mode='after')
    def within_source(self):
        ids=[]
        for hypothesis in [self.song,*self.local]:
            start,end=(0.,self.source.duration) if hypothesis is self.song else (hypothesis.start,hypothesis.end)
            if end<=start or end>self.source.duration: raise ValueError('Hypothesis range is outside recording')
            if any(e.start<start or e.end>end for e in hypothesis.evidence): raise ValueError('Evidence is outside the chosen scope')
            if isinstance(hypothesis,LocalHypothesis):ids.append(hypothesis.id)
        if len(set(ids))!=len(ids):raise ValueError('Local hypothesis IDs must be unique')
        return self


class LearningSave(StructureModel):
    expected_version: int = Field(ge=0)
    document: LearningDocument


class LearningConflict(ValueError): pass


class LearningStore:
    def __init__(self,path):self.path=Path(path)

    def read(self,job):
        row=None
        if self.path.is_file():
            with sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learning_practice'").fetchone():
                    row=db.execute('SELECT document,version,updated_at FROM learning_practice WHERE job_id=?',(job,)).fetchone()
        return dict(job_id=job,document=json.loads(row[0]) if row else None,version=row[1] if row else 0,updated_at=row[2] if row else None)

    def history(self,job):
        if not self.path.is_file():return []
        with sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learning_history'").fetchone():return []
            return [dict(version=v,document=json.loads(d),updated_at=t) for v,d,t in db.execute(
                'SELECT version,document,updated_at FROM learning_history WHERE job_id=? ORDER BY version DESC LIMIT 50',(job,))]

    def save(self,job,value,expected_version,source_provider):
        document=LearningDocument.model_validate(value)
        if type(expected_version) is not int or expected_version<0:raise ValueError('Invalid version')
        def check():
            current=StructureSource.model_validate(source_provider())
            if current.job_id!=job or current!=document.source:raise LearningConflict('錄音來源已變動，請保留筆記並重新載入。')
        check()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            check()
            db.execute('CREATE TABLE IF NOT EXISTS learning_practice(job_id TEXT PRIMARY KEY,document TEXT NOT NULL,version INTEGER NOT NULL,updated_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS learning_history(job_id TEXT NOT NULL,version INTEGER NOT NULL,document TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(job_id,version))')
            row=db.execute('SELECT document,version,updated_at FROM learning_practice WHERE job_id=?',(job,)).fetchone()
            if (row[1] if row else 0)!=expected_version:raise LearningConflict('另一頁已更新學習筆記；請保留草稿後重新載入。')
            if row:
                if LearningDocument.model_validate_json(row[0]).source!=document.source:raise LearningConflict('舊筆記屬於不同錄音，不能覆蓋。')
                db.execute('INSERT INTO learning_history VALUES(?,?,?,?)',(job,row[1],row[0],row[2]))
            now=datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO learning_practice VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET document=excluded.document,version=excluded.version,updated_at=excluded.updated_at',(job,document.model_dump_json(),expected_version+1,now))
        return dict(job_id=job,document=document.model_dump(mode='json'),version=expected_version+1,updated_at=now)
