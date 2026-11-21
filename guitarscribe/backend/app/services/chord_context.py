"""Observed context at adoption, separate from legacy chord documents.

A context match is not an accuracy verdict. Missing evidence stays unknown;
changed roots or boundaries never delete or rewrite the user's chord names.
"""
import json
import sqlite3
from .root_practice import PracticeDocument


def roots_context(path, job, source):
    path=path.with_name('root-practice.sqlite3')
    if not path.is_file():return dict(state='absent',segments=[])
    try:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='root_practice'").fetchone():return dict(state='absent',segments=[])
            row=db.execute('SELECT document FROM root_practice WHERE job_id=?',(job,)).fetchone()
        if row is None:return dict(state='absent',segments=[])
        document=PracticeDocument.model_validate_json(row[0]).model_dump(mode='json')
        expected={k:v for k,v in source.items() if k!='audio_sha256'}
        if document['source']!=expected:return dict(state='source_mismatch',segments=[])
        return dict(state='available',segments=document['segments'])
    except (sqlite3.Error,ValueError):return dict(state='unavailable',segments=[])


def context_for(segment, roots, structure):
    overlaps=lambda item:item['start']<segment['end'] and item['end']>segment['start']
    return dict(roots=dict(state=roots['state'],segments=[{k:r[k] for k in ('id','start','end','root','status')} for r in roots['segments'] if overlaps(r)]),
        structure=[{k:s[k] for k in ('id','start','end')} for s in structure['sections'] if overlaps(s)] if structure else None)


def decision(segment):return {k:segment[k] for k in ('id','start','end','symbol','status')}


def record_context(db,store,job,before,after,structure,section):
    roots=roots_context(store.path,job,after['source'])
    db.execute('CREATE TABLE IF NOT EXISTS chord_context(job_id TEXT NOT NULL,segment_id TEXT NOT NULL,basis TEXT NOT NULL,PRIMARY KEY(job_id,segment_id))')
    previous={r['id']:r for r in before['segments']}
    for segment in after['segments']:
        if segment['status']!='confirmed' or previous.get(segment['id'])==segment:continue
        if segment['end']<=section['start'] or segment['start']>=section['end']:continue
        prior=db.execute('SELECT basis FROM chord_context WHERE job_id=? AND segment_id=?',(job,segment['id'])).fetchone()
        if prior:
            old_basis=json.loads(prior[0])
            if old_basis['source']==after['source'] and old_basis['decision']==decision(segment):continue
        basis=dict(source=after['source'],decision=decision(segment),context=context_for(segment,roots,structure))
        db.execute('INSERT INTO chord_context VALUES(?,?,?) ON CONFLICT(job_id,segment_id) DO UPDATE SET basis=excluded.basis',
            (job,segment['id'],json.dumps(basis,ensure_ascii=False,sort_keys=True)))


def review_context(store,job,document,structure):
    saved={}
    if store.path.is_file():
        with sqlite3.connect(store.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chord_context'").fetchone():
                saved={identifier:json.loads(raw) for identifier,raw in db.execute('SELECT segment_id,basis FROM chord_context WHERE job_id=?',(job,))}
    roots=roots_context(store.path,job,document['source']);result={}
    for segment in document['segments']:
        if segment['status']!='confirmed':continue
        basis=saved.get(segment['id']);changed=[]
        if not basis or basis['source']!=document['source'] or basis['decision']!=decision(segment):
            result[segment['id']]=dict(state='unknown',changed=[]);continue
        current=context_for(segment,roots,structure)
        for kind in ('roots','structure'):
            if current[kind]!=basis['context'][kind]:changed.append(kind)
        uncertain=roots['state'] in ('source_mismatch','unavailable') or not structure
        result[segment['id']]=dict(state='needs_review' if changed or uncertain else 'current',changed=changed)
    return result
