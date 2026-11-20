from copy import deepcopy
import pytest
from app.evaluation.structure_review_summary import review_summary


def document():
    source=dict(job_id='song',fingerprint='a'*64,audio_sha256='b'*64,duration=12.,source_start=0.)
    sections=[]
    for i,label in enumerate(['intro','intro','chorus']):
        original=dict(id=f'm{i}',start=float(i*4),end=float((i+1)*4),label=label)
        sections.append(dict(**original,display_label=label,model_sections=[original]))
    return dict(schema_version=1,source=source,candidate_sha256='c'*64,sections=sections)


def test_confirmation_is_not_correction_or_independent_accuracy():
    doc=document();first=review_summary(doc)
    assert first['pending_sections']==3
    assert first['net_changed_original_fraction']==0
    for s in doc['sections']:
        s.update(name_review_status='user_confirmed',boundary_review_status='user_confirmed')
    result=review_summary(doc)
    assert result['pending_sections']==0
    assert result['net_changed_original_fraction']==0
    assert result['semantic_accuracy'] is None and result['active_review_seconds'] is None
    assert result['independent_reference'] is False


def test_merge_and_rename_measure_net_change_without_double_counting():
    doc=document();a,b,c=doc['sections'];a.update(end=8.,model_sections=a['model_sections']+b['model_sections'])
    c.update(label='verse',name_review_status='user_corrected')
    doc['sections']=[a,c];result=review_summary(doc)
    assert result['original_sections']==3 and result['current_sections']==2
    assert result['removed_internal_boundaries']==1
    assert result['name_changed_original_sections']==1
    assert result['boundary_changed_original_sections']==2
    assert result['net_changed_original_fraction']==1
    assert result['section_count_reduction']==1


def test_missing_or_partial_model_history_is_unknown_not_zero():
    doc=document();doc['candidate_sha256']=None
    for s in doc['sections']:s['model_sections']=[]
    result=review_summary(doc)
    assert result['net_changed_original_fraction'] is None
    doc=document();doc['sections'][-1]['model_sections']=[]
    assert review_summary(doc)['baseline_complete'] is False
    doc=document();doc['sections'][1]['model_sections']=[deepcopy(doc['sections'][0]['model_sections'][0])]
    doc['sections'][1]['model_sections'][0]['label']='verse'
    with pytest.raises(ValueError):review_summary(doc)


def test_report_refuses_stale_api_snapshots_and_duplicate_recordings(tmp_path):
    import json
    import runpy
    from pathlib import Path
    report=runpy.run_path(str(Path(__file__).parents[1]/'scripts/report_structure_review.py'))['report']
    path=tmp_path/'source.json';doc=document()
    path.write_text(json.dumps(dict(document=doc,current_source=doc['source'],source_matches=False)))
    with pytest.raises(ValueError,match='current audio'):report([path])
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='same recording'):report([path,path])
    assert report([path])['music_accuracy_claim'] is False
