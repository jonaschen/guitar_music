from copy import deepcopy
import pytest
from app.services.learning_practice import LearningDocument, LearningStore, LearningConflict


def document():
    return dict(schema_version=1,source=dict(job_id='song',fingerprint='a'*64,audio_sha256='b'*64,duration=12.,source_start=42.),
        song=dict(tonic=None,mode='unknown',note='',evidence=[]),local=[])


def test_unknown_hypotheses_and_local_evidence_preserve_source_and_reopen(tmp_path):
    doc=document();doc['song'].update(tonic='C',mode='major',note='句尾停留仍需比較')
    doc['local']=[dict(id='phrase',start=4.,end=8.,title='副歌末句',tonic='A',mode='minor',note='也可能仍是C大調',evidence=[dict(start=6.,end=7.,note='收束處')])]
    store=LearningStore(tmp_path/'learning.sqlite3')
    assert store.read('song')['document'] is None and not store.path.exists()
    source=lambda:doc['source']
    result=store.save('song',doc,0,source)
    assert result['version']==1
    assert LearningStore(store.path).read('song')['document']==LearningDocument.model_validate(doc).model_dump(mode='json')
    next_doc=deepcopy(doc);next_doc['song'].update(tonic=None,mode='other')
    store.save('song',next_doc,1,source)
    assert store.history('song')[0]['document']['song']['tonic']=='C'
    assert list(tmp_path.iterdir())==[store.path]


def test_version_and_recording_change_cannot_overwrite_hypotheses(tmp_path):
    store=LearningStore(tmp_path/'learning.sqlite3');doc=document();source=lambda:doc['source']
    store.save('song',doc,0,source)
    with pytest.raises(LearningConflict):store.save('song',doc,0,source)
    with pytest.raises(LearningConflict):store.save('song',doc,1,lambda:{**doc['source'],'audio_sha256':'c'*64})
    assert store.read('song')['version']==1 and store.history('song')==[]


@pytest.mark.parametrize('change',[
 lambda d:d['song'].update(tonic='H'),
 lambda d:d['song'].update(mode='definitely-correct'),
 lambda d:d['song'].update(evidence=[dict(start=11.,end=13.,note='outside')]),
 lambda d:d.update(local=[dict(id='same',start=1.,end=3.,title='x',tonic=None,mode='unknown',note='',evidence=[])]*2),
 lambda d:d.update(local=[dict(id='phrase',start=4.,end=8.,title='x',tonic='C',mode='major',note='',evidence=[dict(start=2.,end=3.,note='outside phrase')])]),
])
def test_invalid_or_outside_source_evidence_is_rejected(change):
    doc=document();change(doc)
    with pytest.raises(ValueError):LearningDocument.model_validate(doc)


def test_source_provider_is_rechecked_inside_write_transaction(tmp_path):
    store=LearningStore(tmp_path/'learning.sqlite3');doc=document();calls=[]
    def source():
        calls.append(True)
        return doc['source'] if len(calls)==1 else {**doc['source'],'fingerprint':'d'*64}
    with pytest.raises(LearningConflict):store.save('song',doc,0,source)
    assert store.read('song')['version']==0


def test_api_unknown_read_does_not_create_database_and_source_loss_retains_saved_notes(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    import wave
    from app.models.jobs import JobStatus
    from app.models.score import SongScore
    from app.learning_practice_api import create_learning_router,get_learning_store
    path=tmp_path/'analysis-source.wav'
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\0\0'*96000)
    job=SimpleNamespace(id='song',status=JobStatus.COMPLETED,skip_seconds=42.,analysis_seconds=12.,
        score=SongScore.model_validate(dict(song=dict(title='fixture',duration_seconds=12.,source_start_seconds=42.),chords=[])))
    service=SimpleNamespace(get=lambda _:job,store=SimpleNamespace(job_dir=lambda _:tmp_path))
    store=LearningStore(tmp_path/'learning.sqlite3');app=FastAPI();app.include_router(create_learning_router(lambda:service));app.dependency_overrides[get_learning_store]=lambda:store
    with TestClient(app) as client:
        url='/api/v1/jobs/song/learning-practice';reply=client.get(url);assert reply.status_code==200
        body=reply.json();assert body['document']['song']['tonic'] is None and body['source_matches']
        assert not store.path.exists()
        document=body['document'];document['song'].update(tonic='A',mode='minor')
        assert client.put(url,json=dict(document=document,expected_version=0)).status_code==200
        assert client.put(url,json=dict(document=document,expected_version=0)).status_code==409
        bad=deepcopy(document);bad['song']['tonic']='H'
        assert client.put(url,json=dict(document=bad,expected_version=1)).status_code==422
        job.status=JobStatus.QUEUED
        assert client.put(url,json=dict(document=document,expected_version=1)).status_code==409
        job.status=JobStatus.COMPLETED;path.unlink()
        saved=client.get(url).json();assert not saved['source_matches'] and saved['document']['song']['tonic']=='A'
        assert client.put(url,json=dict(document=document,expected_version=1)).status_code==404
        assert store.read('song')['version']==1
