"""Evaluate saved official ensemble labs under frozen domains; no inference."""
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import sha,projected_events
from app.evaluation.chord_errors import diagnose_chord_errors,diagnostic_label
from app.evaluation.annotations import QualityAnnotation
from app.models.analysis import ChordEvent
from app.models.score import SongScore


def parse_lab(text,end):
    events=[];cursor=0.0
    for i,line in enumerate(text.splitlines()):
        if not line.strip():continue
        a,b,label=line.split(maxsplit=2);a,b=float(a),float(b)
        if not all(math.isfinite(v)for v in(a,b))or a<cursor-1e-9 or b<=a:raise ValueError('Invalid model intervals')
        diagnostic_label(label);cursor=b
        if a<end and b>0:events.append(ChordEvent(id=str(i),start=max(0,a),end=min(end,b),symbol=label))
    if not events:raise ValueError('Empty model lab')
    return events


def run(root):
    out=root/'output/evaluation/ismir2019-comparison-2026-11-05'
    plan_path=root/'docs/evaluation/ismir2019-plan-2026-11-05.json';p=json.loads(plan_path.read_text())
    manifest=json.loads((out/'inference-manifest.json').read_text())
    if manifest['plan_sha256']!=sha(plan_path):raise ValueError('Plan hash changed')
    cases=json.loads((root/p['input_plan']['path']).read_text())['cases'];g=p['gates'];rows=[]
    for case in cases:
        rid=case['recording_id'];lab=out/(rid+'.lab')
        if sha(lab)!=manifest['outputs'][rid]:raise ValueError('Model output changed')
        for k in ('audio','annotation','estimate'):
            if sha(root/case[k]['path'])!=case[k]['sha256']:raise ValueError('Input changed')
        score=SongScore.model_validate_json((root/case['estimate']['path']).read_text());ann=QualityAnnotation.model_validate_json((root/case['annotation']['path']).read_text())
        # Same historical evaluation representation on both systems.
        case={**case,'historical_score_projection':'identity'if rid.startswith('SWD_')else'guitarset-merged'}
        events=projected_events(parse_lab(lab.read_text(),case['interval'][1]),case)
        baseline=diagnose_chord_errors(score,ann);candidate=diagnose_chord_errors(score.model_copy(update={'chords':events}),ann)
        b,c=baseline['summary'],candidate['summary'];bd,cd=baseline['boundaries'],candidate['boundaries']
        delta={k:c['metrics'][k]['accuracy']-b['metrics'][k]['accuracy']for k in('root','majmin')}
        delta['missed_false_seconds']=sum(c['category_seconds'][k]-b['category_seconds'][k]for k in('missed_chord','false_chord'))
        for k in('precision','recall'):delta['boundary_'+k]=cd[k]-bd[k]if cd[k]is not None and bd[k]is not None else None
        guards={'root':delta['root']>=-g['all_max_root_drop']-1e-12,'majmin':delta['majmin']>=-g['all_max_majmin_drop']-1e-12,'missed_false':delta['missed_false_seconds']<=g['all_max_missed_false_increase_seconds']+1e-12}
        for k in('precision','recall'):guards['boundary_'+k]=delta['boundary_'+k]is not None and delta['boundary_'+k]>=-g['all_max_boundary_'+k+'_drop']-1e-12
        row={'recording_id':rid,'baseline':{'summary':b,'boundaries':bd},'candidate':{'summary':c,'boundaries':cd},'delta':delta,'guards':guards}
        rows.append(row)
    hu=[r['delta']['root']for r in rows if r['recording_id'].startswith('SWD_')];funk=next(r['delta']['root']for r in rows if r['recording_id']=='05_Funk2-119-G_comp')
    targets={'funk2':funk>=g['funk2_root_min_gain'],'hu33_mean':sum(hu)/len(hu)>=g['hu33_mean_root_min_gain'],'hu33_two':sum(x>=g['hu33_at_least_two_root_gain']for x in hu)>=2}
    passed=all(targets.values())and all(all(r['guards'].values())for r in rows)
    return {'plan_sha256':sha(plan_path),'inference_manifest':manifest,'sources':rows,'targets':targets,'hu33_mean_root_gain':sum(hu)/len(hu),'decision':'research_candidate_only'if passed else'reject_fixed_model','product_changed':False}


if __name__=='__main__':print(json.dumps(run(Path(sys.argv[1])),ensure_ascii=False,indent=2))
