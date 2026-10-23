import json

from fastapi.testclient import TestClient

from app.evaluation.anchor_capture import create_capture_app


def client(tmp_path):
    packet=tmp_path/'packet';packet.mkdir()
    config={'config_id':'source','revision':'score','audio_sha256':'hash','analysis_start':10,'content_duration':3,
            'anchors':[{'phrase':'今天','character':'天','character_index':1}]}
    score={'beats':[{'time':11,'beat':1,'measure':1}],'chords':[]}
    for name,data in [('config',config),('score',score),('manifest',{'events':[]})]:
        (packet/f'{name}.json').write_text(json.dumps(data))
    return TestClient(create_capture_app(packet,tmp_path/'receipts'))


def payload(**kwargs):
    obs={'anchor_index':0,'raw_seconds':1.1,'seconds':1.0,'reviewed':True,'skipped':False}
    obs.update(kwargs)
    return {'config_id':'source','observations':[obs]}


def test_stores_original_and_adjusted_time_in_separate_immutable_receipts(tmp_path):
    c=client(tmp_path)
    a=c.post('/marks',json=payload());b=c.post('/marks',json=payload())
    assert a.status_code==b.status_code==200
    assert a.json()['receipt_id']!=b.json()['receipt_id']
    files=list((tmp_path/'receipts').glob('*.json'));assert len(files)==2
    record=json.loads(files[0].read_text())
    assert record['observations'][0]['raw_seconds']==1.1
    assert record['observations'][0]['seconds']==1.0
    assert record['analysis_start']==10


def test_rejects_stale_duplicate_out_of_range_or_empty_marks_without_saving(tmp_path):
    c=client(tmp_path)
    stale=payload();stale['config_id']='old'
    assert c.post('/marks',json=stale).status_code==409
    duplicate=payload();duplicate['observations']*=2
    for p in [duplicate,payload(seconds=4),payload(anchor_index=1),payload(raw_seconds=None),
              payload(skipped=True),payload(skipped=True,seconds=None,raw_seconds=None)]:
        assert c.post('/marks',json=p).status_code==422
    assert not (tmp_path/'receipts').exists()
