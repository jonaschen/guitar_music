import asyncio
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from app.api import app, get_job_service, get_lyric_worksheet_store, get_caption_drafts
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.lyric_worksheets import LyricWorksheetStore, WorksheetConflict, WorksheetDocument
from app.services.caption_drafts import CaptionDraftService, CaptionUnavailable, caption_tracks, parse_json3

DOC={'source':'自行填寫','lines':[{'id':'a','lyric':'副歌  一','notation':" 5  0 - #1' ",'anchor':None,'start':None,'end':None},{'id':'b','lyric':'副歌  一','notation':'','anchor':None,'start':None,'end':None}]}

def test_cas_reopen_clear_crossjob(tmp_path):
    store=LyricWorksheetStore(tmp_path/'s.sqlite3')
    def put(_):
        try:store.save('a',DOC,0);return 1
        except WorksheetConflict:return 0
    with ThreadPoolExecutor(max_workers=12) as pool:assert sum(pool.map(put,range(12)))==1
    assert LyricWorksheetStore(store.path).read('a')['document']==DOC
    assert store.read('b')['version']==0
    store.save('a',{'lines':[]},1)
    with pytest.raises(WorksheetConflict):store.save('a',DOC,1)
    assert store.read('a')['document']['lines']==[]

@pytest.mark.parametrize('doc',[{'lines':[DOC['lines'][0]]*2},{'lines':[dict(DOC['lines'][0],lyric='x'*2001)]},{'lines':[dict(DOC['lines'][0],start=2,end=1)]},{'lines':[dict(DOC['lines'][0],start=float('nan'))]}])
def test_document_validation(doc):
    with pytest.raises(ValidationError):WorksheetDocument.model_validate(doc)

@pytest.mark.asyncio
async def test_api_independence_expiry_and_no_network_when_disabled(tmp_path,monkeypatch):
    store=LyricWorksheetStore(tmp_path/'s.sqlite3');score=SongScore();before=score.model_dump_json();expired=False
    def get(job):
        if expired or job=='missing':raise FileNotFoundError()
        return SimpleNamespace(id=job,status=JobStatus.COMPLETED if job=='a' else JobStatus.QUEUED,score=score,source_type='youtube',source_url='https://youtube.com/watch?v=abcdefghijk')
    captions=SimpleNamespace(tracks=AsyncMock(return_value=[{'id':'manual:es','language':'es','kind':'manual','url':'private'}]),preview=AsyncMock())
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=get)
    app.dependency_overrides[get_lyric_worksheet_store]=lambda:store
    app.dependency_overrides[get_caption_drafts]=lambda:captions
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            url='/api/v1/jobs/a/lyric-worksheet'
            assert (await c.get(url)).json()['version']==0
            assert (await c.put(url,json={'document':DOC,'expected_version':0})).status_code==200
            assert (await c.put(url,json={'document':DOC,'expected_version':0})).status_code==409
            assert (await c.get('/api/v1/jobs/missing/lyric-worksheet')).status_code==404
            assert (await c.get('/api/v1/jobs/pending/lyric-worksheet')).status_code==409
            from app.api import Settings
            monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:SimpleNamespace(youtube_enabled=False)))
            for suffix in ['lyric-caption-tracks','lyric-caption-preview']:
                r=await c.get('/api/v1/jobs/a/'+suffix) if suffix.endswith('tracks') else await c.post('/api/v1/jobs/a/'+suffix,json={'track_id':'manual:es'})
                assert r.status_code==503
            captions.tracks.assert_not_awaited();captions.preview.assert_not_awaited()
            monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:SimpleNamespace(youtube_enabled=True)))
            response=(await c.get('/api/v1/jobs/a/lyric-caption-tracks')).json()
            assert response['tracks']==[{'id':'manual:es','language':'es','kind':'manual'}]
            expired=True
            assert (await c.get(url)).json()['document']==DOC
            assert (await c.put(url,json={'document':DOC,'expected_version':1})).status_code==200
        assert score.model_dump_json()==before
    finally:
        for dep in [get_job_service,get_lyric_worksheet_store,get_caption_drafts]:app.dependency_overrides.pop(dep,None)


def track(lang,extra=''):
    return [{'ext':'json3','url':f'https://www.youtube.com/api/timedtext?lang={lang}{extra}'}]

def test_track_language_and_translation_filters():
    meta={'language':'ko','subtitles':{'es':track('es')},'automatic_captions':{'ko-orig':track('ko'),'en':track('ko','&tlang=en'),'fr':track('ko'),'ko':track('ko','&tlang=ko')}}
    assert [t['id'] for t in caption_tracks(meta)]==['manual:es','automatic:ko-orig']
    assert caption_tracks({'subtitles':[],'automatic_captions':{'en':[{'ext':'json3','url':None}]}})==[]


def event(text,start=10000,length=2000):return {'tStartMs':start,'dDurationMs':length,'segs':[{'utf8':text}]}

def test_caption_offset_repeats_unknown_and_crop():
    rows=parse_json3({'events':[event('副歌',9000),event('副歌'),event('末尾',14000,3000),{'segs':[{'utf8':'未對時'}]},event('之前',0)]},10,5)
    assert rows==[{'lyric':'副歌','start':0.,'end':1.},{'lyric':'副歌','start':0.,'end':2.},{'lyric':'末尾','start':4.,'end':5},{'lyric':'未對時','start':None,'end':None}]

@pytest.mark.parametrize('payload',[None,[],{}, {'events':None},{'events':[{'segs':None}]},{'events':[event('x'*2001)]},{'events':[event('bad',10**1000)]},{'events':[{'segs':[{'utf8':'x'}]}]*401}])
def test_malformed_or_oversized_caption_is_readable_error(payload):
    with pytest.raises(CaptionUnavailable):parse_json3(payload,0,30)

@pytest.mark.asyncio
async def test_metadata_cancellation_reaps_process(monkeypatch):
    from app.services import caption_drafts as module
    started=asyncio.Event()
    async def read(_):
        if process.returncode is not None:return b''
        started.set();await asyncio.Event().wait()
    process=SimpleNamespace(stdout=SimpleNamespace(read=read),stderr=SimpleNamespace(read=read),returncode=None)
    process.kill=lambda:setattr(process,'returncode',-9)
    process.wait=AsyncMock(return_value=-9)
    create=AsyncMock(return_value=process);monkeypatch.setattr(module.asyncio,'create_subprocess_exec',create)
    service=CaptionDraftService();task=asyncio.create_task(service._metadata('https://youtube.com/watch?v=abcdefghijk'))
    await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert process.returncode==-9;process.wait.assert_awaited()
    args=create.call_args.args
    assert '--skip-download' in args and '--no-config' in args and '--dump-single-json' in args

@pytest.mark.asyncio
async def test_metadata_oversized_pipe_does_not_deadlock(tmp_path):
    binary=tmp_path/'fake-ytdlp'
    binary.write_text('#!/usr/bin/python3\nimport os,time\nos.write(1,b"x"*(6*1024*1024))\ntime.sleep(60)\n');binary.chmod(0o700)
    with pytest.raises(CaptionUnavailable):await asyncio.wait_for(CaptionDraftService(binary=str(binary))._metadata('https://www.youtube.com/watch?v=abc'),7)

@pytest.mark.asyncio
async def test_unknown_caption_selection_never_fetches(monkeypatch):
    service=CaptionDraftService();service._metadata=AsyncMock(return_value={'subtitles':{'es':track('es')}})
    job=SimpleNamespace(id='a',source_url='https://youtube.com/watch?v=abc')
    with pytest.raises(CaptionUnavailable,match='選項不存在'):await service.preview(job,'automatic:en')
    # Repeated lists reuse metadata rather than starting a new subprocess.
    assert [r['id'] for r in await service.tracks(job)]==['manual:es']
    service._metadata.assert_awaited_once()

ANCHOR=dict(time=2,end=6,source_start_seconds=10,duration_seconds=12,kind='metered',grid_id='grid-v1')

def test_anchor_roundtrip_explicit_unlink_and_old_client_protection(tmp_path):
    from app.services.lyric_worksheets import WorksheetUpgradeRequired
    store=LyricWorksheetStore(tmp_path/'anchors.sqlite3')
    doc=WorksheetDocument.model_validate(DOC).model_dump();doc['lines'][0]['anchor']=ANCHOR
    assert store.save('a',doc,0,1)['document']['lines'][0]['anchor']==ANCHOR
    for old in [DOC,{'lines':[]}]:
        with pytest.raises(WorksheetUpgradeRequired):store.save('a',old,1)
        assert store.read('a')['version']==1 and store.read('a')['document']==doc
    omitted=WorksheetDocument.model_validate(DOC).model_dump();omitted['lines'][0].pop('anchor')
    with pytest.raises(WorksheetUpgradeRequired):store.save('a',omitted,1,1)
    doc['lines'][0]['anchor']=None
    assert store.save('a',doc,1,1)['document']['lines'][0]['anchor'] is None
    assert store.save('a',DOC,2)['version']==3

@pytest.mark.parametrize('anchor',[dict(ANCHOR,time=12),dict(ANCHOR,end=2),dict(ANCHOR,end=13),dict(ANCHOR,grid_id=None),dict(ANCHOR,source_start_seconds=-1),dict(ANCHOR,time=float('inf'))])
def test_invalid_anchor_rejected(anchor):
    from app.services.lyric_worksheets import WorksheetAnchor
    with pytest.raises(ValidationError):WorksheetAnchor.model_validate(anchor)

@pytest.mark.asyncio
async def test_old_tab_cannot_clear_anchors_even_with_current_version(tmp_path):
    store=LyricWorksheetStore(tmp_path/'anchors.sqlite3');doc=WorksheetDocument.model_validate(DOC).model_dump();doc['lines'][0]['anchor']=ANCHOR
    store.save('a',doc,0,1)
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=lambda _:None)
    app.dependency_overrides[get_lyric_worksheet_store]=lambda:store
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            for document in [DOC,{'source':'','lines':[]}]:
                response=await c.put('/api/v1/jobs/a/lyric-worksheet',json={'document':document,'expected_version':1})
                assert response.status_code==409 and '重新整理' in response.json()['detail']
                assert store.read('a')['document']==doc
            response=await c.put('/api/v1/jobs/a/lyric-worksheet',json={'document':DOC,'expected_version':1,'anchor_schema':1})
            assert response.status_code==200 and response.json()['document']['lines'][0]['anchor'] is None
    finally:
        app.dependency_overrides.pop(get_job_service,None);app.dependency_overrides.pop(get_lyric_worksheet_store,None)
