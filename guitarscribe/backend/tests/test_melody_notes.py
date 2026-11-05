from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import app, get_job_service, get_melody_note_store
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.melody_notes import MelodyNoteStore, NoteConflict


def test_notes_survive_reopen_and_clear_without_old_version_resurrection(tmp_path):
    store=MelodyNoteStore(tmp_path/'notes.sqlite3')
    assert store.read('a')['version']==0
    text='自己抓 G 大調\n旋律：5 6 1；保留原字 <script>'
    assert store.save('a',text,0)['version']==1
    assert MelodyNoteStore(store.path).read('a')['text']==text
    assert store.read('b')['text']==''
    store.save('a','',1)
    with pytest.raises(NoteConflict):store.save('a',text,1)
    assert store.read('a')['text']==''


def test_two_writers_cannot_silently_overwrite_each_other(tmp_path):
    store=MelodyNoteStore(tmp_path/'notes.sqlite3')
    def put(i):
        try:store.save('a',str(i),0);return True
        except NoteConflict:return False
    with ThreadPoolExecutor(max_workers=8)as pool:assert sum(pool.map(put,range(8)))==1
    assert store.read('a')['version']==1


@pytest.mark.asyncio
async def test_api_persistence_conflict_validation_and_score_independence(tmp_path):
    store=MelodyNoteStore(tmp_path/'notes.sqlite3');score=SongScore();before=score.model_dump_json()
    expired=False
    def get(job):
        if job=='missing' or expired:raise FileNotFoundError()
        return SimpleNamespace(status=JobStatus.COMPLETED if job=='a' else JobStatus.QUEUED,score=score)
    app.dependency_overrides[get_job_service]=lambda:SimpleNamespace(get=get)
    app.dependency_overrides[get_melody_note_store]=lambda:store
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test')as c:
            url='/api/v1/jobs/a/melody-notes'
            assert (await c.get(url)).json()['text']==''
            assert (await c.put(url,json={'text':'G 大調\n5 6 1','expected_version':0})).status_code==200
            assert (await c.put(url,json={'text':'stale','expected_version':0})).status_code==409
            assert (await c.get(url)).json()['text']=='G 大調\n5 6 1'
            assert (await c.put(url,json={'text':'x'*16001,'expected_version':1})).status_code==422
            assert (await c.get('/api/v1/jobs/missing/melody-notes')).status_code==404
            assert (await c.get('/api/v1/jobs/pending/melody-notes')).status_code==409
            expired=True
            assert (await c.get(url)).json()['text']=='G 大調\n5 6 1'
            assert (await c.put(url,json={'text':'音訊到期後仍保留手記','expected_version':1})).status_code==200
        assert score.model_dump_json()==before
    finally:
        app.dependency_overrides.pop(get_job_service,None)
        app.dependency_overrides.pop(get_melody_note_store,None)
