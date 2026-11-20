from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from types import SimpleNamespace

import pytest

from app.services.chord_practice import ChordPracticeStore, ChordSave, ChordConflict
from app.services.song_structure import SongStructureStore
from app.services.chord_reuse import ChordReuseService, ReuseRequest, ReuseApply, ReuseUndo


@pytest.fixture
def setup(tmp_path):
    source = dict(job_id='song', fingerprint='a'*64, audio_sha256='b'*64, duration=14., source_start=42.)
    sections = [dict(id=i, start=a, end=b, label=label, display_label='同名段落')
                for i, a, b, label in [('source',0.,6.,'verse'),('target',6.,12.,'verse'),('outro',12.,14.,'outro')]]
    structure = SongStructureStore(tmp_path/'structure.sqlite3')
    structure.save('song', dict(schema_version=1, source=source, candidate_sha256=None, sections=sections), 0)
    specs = [('s0',0,1,'C','C/E'),('s1',1,2,'C','N.C.'),('s2',2,3,'Am',None),
             ('s3',3,4,'Am','G7'),('s4',4,6,'F','Dm'),('t0',6,8.5,'F',None),
             ('t1',8.5,9,'F','F'),('t2',9,10.25,'G',None),('t3',10.25,11,'G','N.C.'),
             ('t4',11,12,'G',None),('end',12,14,None,None)]
    doc = dict(schema_version=1, source=source, segments=[dict(id=i,start=float(a),end=float(b),
        original_symbol=original,symbol=symbol,status='confirmed' if symbol else 'pending')
        for i,a,b,original,symbol in specs])
    initial = deepcopy(doc)
    for row in initial['segments']: row.update(symbol=None,status='pending')
    store = ChordPracticeStore(tmp_path/'chords.sqlite3')
    provider = lambda: (deepcopy(source),deepcopy(initial))
    first = deepcopy(initial)
    first['segments'][:5] = deepcopy(doc['segments'][:5])
    store.save('song',ChordSave(expected_version=0,structure_version=1,section_id='source',document=first),provider,structure.path)
    store.save('song',ChordSave(expected_version=1,structure_version=1,section_id='target',document=doc),provider,structure.path)
    request = dict(expected_version=2,structure_version=1,source_section_id='source',target_section_id='target',
                   source_range=dict(start=.5,end=4.5),target_range=dict(start=6.5,end=10.5),
                   fingerprint=source['fingerprint'],audio_sha256=source['audio_sha256'],alignment_confirmed=True)
    service = ChordReuseService(store,structure.path)
    return SimpleNamespace(store=store,structure=structure,source=source,document=doc,initial=initial,
                           provider=provider,service=service,request=request)


def plan(s, **overrides):
    return s.service.plan('song',ReuseRequest.model_validate({**s.request,**overrides}),lambda: s.source)


def apply(s, preview=None, selected=None):
    preview = preview or plan(s)
    rows = [r['id'] for r in preview['rows'] if r['status']=='fillable'] if selected is None else selected
    return s.service.apply('song',ReuseApply(plan_id=preview['plan_id'],request=preview['request'],selected_row_ids=rows),lambda:s.source)


def undo(s, op, version, structure_version=1):
    return s.service.undo('song',op['id'],ReuseUndo(expected_version=version,structure_version=structure_version,
        fingerprint=s.source['fingerprint'],audio_sha256=s.source['audio_sha256']),lambda:s.source)


def at(doc, time):
    return next(r for r in doc['segments'] if r['start']<=time<r['end'])


def test_preview_intersects_seconds_preserves_unknown_and_protected_without_writes(setup):
    s=setup; before=s.store.path.read_bytes(); structure=s.structure.path.read_bytes()
    result=plan(s)
    assert [r['status'] for r in result['rows']]==['fillable','fillable','source_unknown','target_protected','fillable','fillable','target_protected']
    assert [r['symbol'] for r in result['rows'] if r['status']=='fillable']==['C/E','N.C.','G7','Dm']
    assert result['rows'][0]['start']==6.5 and result['rows'][0]['source_start']==.5
    assert result['counts']['fillable']==4 and result['can_apply']
    assert not plan(s,alignment_confirmed=False)['can_apply']
    assert s.store.path.read_bytes()==before and s.structure.path.read_bytes()==structure


@pytest.mark.parametrize('fault',['version','structure_version','fingerprint','audio','same_section','missing_section','unequal','outside','overlap'])
def test_invalid_or_stale_plan_never_writes(setup,fault):
    s=setup; req=deepcopy(s.request); before=s.store.path.read_bytes()
    if fault=='version': req['expected_version']=1
    if fault=='structure_version': req['structure_version']=0
    if fault=='fingerprint': req['fingerprint']='c'*64
    if fault=='audio': req['audio_sha256']='c'*64
    if fault=='same_section': req['target_section_id']='source'
    if fault=='missing_section': req['source_section_id']='gone'
    if fault=='unequal': req['target_range']['end']=10.
    if fault=='outside': req['source_range']=dict(start=3.,end=7.)
    if fault=='overlap': req['target_range']=dict(start=3.,end=7.)
    with pytest.raises((ValueError,ChordConflict)): plan(s,**req)
    assert s.store.path.read_bytes()==before


def test_apply_offsets_full_symbols_and_only_fills_selected_pending_fragments_atomically(setup):
    s=setup; structure=s.structure.path.read_bytes(); preview=plan(s)
    result=apply(s,preview); doc=result['snapshot']['document']; op=result['operation']
    assert result['snapshot']['version']==3 and op['applied_version']==3 and op['can_undo']
    for point,symbol in [(6.25,None),(6.75,'C/E'),(7.5,'N.C.'),(8.25,None),(8.75,'F'),(9.5,'G7'),(10.1,'Dm'),(10.4,'N.C.'),(11.5,None)]:
        assert at(doc,point)['symbol']==symbol
    for row in doc['segments']:
        midpoint=(row['start']+row['end'])/2
        assert row['original_symbol']==at(s.document,midpoint)['original_symbol']
        if midpoint<6.5 or midpoint>=10.5: assert row['symbol']==at(s.document,midpoint)['symbol']
    assert s.store.history('song')[0]['document']==s.document
    assert s.structure.path.read_bytes()==structure
    assert s.service.ledger('song',lambda:s.source)['operations'][0]['id']==op['id']
    with pytest.raises(ChordConflict): apply(s,preview)
    assert s.store.read('song')['version']==3


@pytest.mark.parametrize('fault',['unconfirmed','protected','unknown','tampered','duplicate','empty'])
def test_apply_rejects_nonfillable_or_unconfirmed_and_tampered_preview(setup,fault):
    s=setup; preview=plan(s,alignment_confirmed=fault!='unconfirmed')
    chosen=[r['id'] for r in preview['rows'] if r['status']=='fillable']
    if fault=='protected': chosen=[next(r['id'] for r in preview['rows'] if r['status']=='target_protected')]
    if fault=='unknown': chosen=[next(r['id'] for r in preview['rows'] if r['status']=='source_unknown')]
    if fault=='tampered': preview['plan_id']='c'*64
    if fault=='duplicate': chosen=chosen[:1]*2
    if fault=='empty': chosen=[]
    before=s.store.path.read_bytes()
    with pytest.raises((ValueError,ChordConflict)): apply(s,preview,chosen)
    assert s.store.path.read_bytes()==before


def test_partial_apply_and_undo_preserve_later_outside_changes_and_retained_cuts(setup):
    s=setup; p=plan(s); result=apply(s,p,[p['rows'][0]['id']]); doc=result['snapshot']['document']
    assert at(doc,6.75)['symbol']=='C/E' and at(doc,7.5)['symbol'] is None
    doc=deepcopy(doc); at(doc,12.5).update(symbol='Am7/E',status='confirmed')
    s.store.save('song',ChordSave(expected_version=3,structure_version=1,section_id='outro',document=doc),s.provider,s.structure.path)
    result=undo(s,result['operation'],4)
    assert result['snapshot']['version']==5
    assert at(result['snapshot']['document'],6.75)['symbol'] is None
    assert at(result['snapshot']['document'],12.5)['symbol']=='Am7/E'
    assert result['operation']['status']=='undone' and not result['operation']['can_undo']
    assert not s.service.ledger('song',lambda:s.source)['operations'][0]['can_undo']


def test_modified_target_blocks_undo_and_ledger_after_reopening(setup):
    s=setup; result=apply(s); doc=deepcopy(result['snapshot']['document'])
    at(doc,6.75).update(symbol='Em')
    s.store.save('song',ChordSave(expected_version=3,structure_version=1,section_id='target',document=doc),s.provider,s.structure.path)
    service=ChordReuseService(ChordPracticeStore(s.store.path),s.structure.path)
    assert not service.ledger('song',lambda:s.source)['operations'][0]['can_undo']
    before=s.store.path.read_bytes()
    with pytest.raises(ChordConflict): undo(s,result['operation'],4)
    assert s.store.path.read_bytes()==before


def test_two_apply_calls_only_commit_one_batch(setup):
    s=setup; preview=plan(s)
    def run():
        try: return apply(s,preview)['snapshot']['version']
        except ChordConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:run(),range(2)))
    assert sorted(map(str,results))==['3','conflict']
    assert len(s.service.ledger('song',lambda:s.source)['operations'])==1


def test_ledger_read_does_not_create_missing_database(tmp_path):
    store=ChordPracticeStore(tmp_path/'missing.sqlite3')
    result=ChordReuseService(store,tmp_path/'structure.sqlite3').ledger('song',lambda:None)
    assert result['operations']==[] and result['version']==0 and not store.path.exists()


def test_later_source_decision_does_not_block_undo(setup):
    s=setup; result=apply(s); doc=deepcopy(result['snapshot']['document'])
    at(doc,.75).update(symbol='Em7')
    s.store.save('song',ChordSave(expected_version=3,structure_version=1,section_id='source',document=doc),s.provider,s.structure.path)
    assert s.service.ledger('song',lambda:s.source)['operations'][0]['can_undo']
    restored=undo(s,result['operation'],4)['snapshot']['document']
    assert at(restored,.75)['symbol']=='Em7' and at(restored,6.75)['symbol'] is None


def test_failure_writing_ledger_rolls_back_document_and_history(setup):
    s=setup; p=plan(s); before=s.store.read('song'); history=s.store.history('song')
    with sqlite3.connect(s.store.path) as db:
        db.execute('CREATE TABLE chord_reuse_ledger (job_id TEXT,id TEXT,payload TEXT,applied_version INTEGER,undone_version INTEGER)')
        db.execute("CREATE TRIGGER reject_ledger BEFORE INSERT ON chord_reuse_ledger BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected failure'): apply(s,p)
    assert s.store.read('song')==before and s.store.history('song')==history
    assert not s.service.ledger('song',lambda:s.source)['operations']


@pytest.mark.parametrize('journal_mode',['delete','wal'])
def test_apply_rechecks_live_hash_and_holds_structure_lock_during_source_check(setup,journal_mode):
    s=setup; p=plan(s); body=ReuseApply(plan_id=p['plan_id'],request=p['request'],
        selected_row_ids=[p['rows'][0]['id']])
    with sqlite3.connect(s.structure.path) as db: db.execute('PRAGMA journal_mode='+journal_mode)
    before=s.store.read('song'); checked=[]
    def changed_source():
        with sqlite3.connect(s.structure.path,timeout=0) as db:
            with pytest.raises(sqlite3.OperationalError,match='locked'): db.execute('BEGIN IMMEDIATE')
        checked.append(True)
        return {**s.source,'audio_sha256':'c'*64}
    with pytest.raises(ChordConflict): s.service.apply('song',body,changed_source)
    assert checked and s.store.read('song')==before


def test_structure_change_invalidates_preview_but_current_valid_structure_allows_undo(setup):
    s=setup; preview=plan(s); result=apply(s,preview)
    structure=s.structure.read('song')['document']
    structure['sections'][0]['display_label']='第一段'
    s.structure.save('song',structure,1)
    with pytest.raises(ChordConflict): undo(s,result['operation'],3)
    restored=undo(s,result['operation'],3,structure_version=2)
    assert restored['snapshot']['version']==4
    assert at(restored['snapshot']['document'],6.75)['symbol'] is None


def test_audio_loss_keeps_readable_ledger_but_disables_undo(setup):
    s=setup; apply(s)
    listing=s.service.ledger('song',lambda:None)
    assert not listing['source_matches'] and len(listing['operations'])==1
    assert not listing['operations'][0]['can_undo']


@pytest.mark.parametrize('edge',['left','right'])
def test_crossing_pending_segment_only_changes_core_and_undo_keeps_outside_semantics(setup,edge):
    import json
    s=setup; doc=deepcopy(s.document)
    if edge=='left':
        doc['segments'][4:6]=[{**doc['segments'][5],'id':'cross','start':4.}]
    else:
        doc['segments'][7:]=[{**doc['segments'][7],'id':'cross','end':14.}]
    with sqlite3.connect(s.store.path) as db:
        db.execute('UPDATE chord_practice SET document=? WHERE job_id=?',(json.dumps(doc),'song'))
    result=apply(s); after=result['snapshot']['document']
    for point in [0.5,4.5,5.9,6.1,10.75,11.5,12.5,13.9]:
        assert at(after,point)['symbol']==at(doc,point)['symbol']
        assert at(after,point)['original_symbol']==at(doc,point)['original_symbol']
    restored=undo(s,result['operation'],3)['snapshot']['document']
    for row in restored['segments']:
        midpoint=(row['start']+row['end'])/2
        assert row['symbol']==at(doc,midpoint)['symbol']
        assert row['original_symbol']==at(doc,midpoint)['original_symbol']


@pytest.mark.asyncio
async def test_api_preview_apply_reload_undo_and_errors_preserve_score_and_roots(setup,monkeypatch,tmp_path):
    from httpx import ASGITransport, AsyncClient
    from app.api import app,get_job_service
    from app.models.jobs import JobStatus
    from app.models.score import SongScore
    from app.services.song_structure import StructureSource
    from app.chord_practice_api import get_chord_practice_store,get_chord_structure_path
    import app.chord_practice_api as routes
    s=setup; audio=tmp_path/'audio.wav'; audio.write_bytes(b'audio')
    roots=tmp_path/'root-practice.sqlite3'; roots.write_bytes(b'root sentinel')
    job=SimpleNamespace(status=JobStatus.COMPLETED,score=SongScore.model_validate({'song':{'duration_seconds':14},'chords':[]}))
    score_before=job.score.model_dump_json(); roots_before=roots.read_bytes()
    def source(*_):
        if not audio.exists(): raise FileNotFoundError()
        return StructureSource.model_validate(s.source)
    monkeypatch.setattr(routes,'source_for_job',source)
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=lambda _:job,store=SimpleNamespace(job_dir=lambda _:tmp_path))
    app.dependency_overrides[get_chord_practice_store]=lambda:s.store
    app.dependency_overrides[get_chord_structure_path]=lambda:s.structure.path
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            prefix='/api/v1/jobs/song/chord-practice'
            p=(await client.post(prefix+'/reuse-plan',json=s.request)).json()
            body=dict(plan_id=p['plan_id'],request=p['request'],selected_row_ids=[p['rows'][0]['id']])
            result=await client.post(prefix+'/reuse-apply',json=body)
            assert result.status_code==200, result.text
            saved=result.json(); assert saved['snapshot']['source_matches']
            assert saved['snapshot']['current_source']==s.source
            assert (await client.post(prefix+'/reuse-apply',json=body)).status_code==409
            assert (await client.post(prefix+'/reuse-plan',json={**s.request,'expected_version':3,'source_range':dict(start=-1,end=3)})).status_code==422
            ledger=(await client.get(prefix+'/reuse-ledger')).json()
            assert ledger['operations'][0]['can_undo']
            undo_body=dict(expected_version=3,structure_version=1,fingerprint=s.source['fingerprint'],audio_sha256=s.source['audio_sha256'])
            assert (await client.post(prefix+'/reuse-ledger/missing/undo',json=undo_body)).status_code==404
            audio.unlink()
            assert not (await client.get(prefix+'/reuse-ledger')).json()['operations'][0]['can_undo']
            endpoint=prefix+'/reuse-ledger/'+saved['operation']['id']+'/undo'
            assert (await client.post(endpoint,json=undo_body)).status_code==404
            audio.write_bytes(b'audio')
            restored=await client.post(endpoint,json=undo_body)
            assert restored.status_code==200,restored.text
            assert restored.json()['operation']['status']=='undone'
            assert (await client.post(endpoint,json={**undo_body,'expected_version':4})).status_code==409
        assert job.score.model_dump_json()==score_before and roots.read_bytes()==roots_before
    finally:
        for dep in (get_job_service,get_chord_practice_store,get_chord_structure_path): app.dependency_overrides.pop(dep,None)
