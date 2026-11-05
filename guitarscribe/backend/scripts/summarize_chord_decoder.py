"""Re-evaluate saved frame traces without inference."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.evaluation.chord_decoder_trace import summarize
from scripts.run_chord_bass_ablation import sha

def run(root):
    out=root/'output/evaluation/chord-decoder-trace-2026-11-05'
    plan=root/'docs/evaluation/chord-decoder-trace-plan-2026-11-05.json'
    recorded=json.loads((out/'run-result.json').read_text())
    if recorded['plan_sha256']!=sha(plan):raise ValueError('Plan changed')
    sources=[]
    for row in recorded['sources']:
        rid=row['recording_id'];path=out/(rid+'-trace.json')
        if sha(path)!=row['trace_sha256']:raise ValueError('Trace changed')
        if not all(v['passed']for v in row['gates'].values()):raise ValueError('Changed events')
        old=json.loads((root/'output/evaluation/chord-error-localization-2026-11-05-v2'/(rid+'.json')).read_text())
        a,b=old['summary']['interval']
        result=summarize(json.loads(path.read_text()),old['intervals'],a,b)
        sources.append({'recording_id':rid,**result})
    keys=next(iter(sources))['four_way_seconds'].keys()
    totals={k:sum(r['four_way_seconds'][k]for r in sources)for k in keys}
    hu=sum(r['positive_margin_hmm_harm_seconds']>.05*r['eligible_seconds'] for r in sources if r['recording_id'].startswith('SWD_')and r['eligible_seconds']>0)
    propose=totals['local_correct_hmm_wrong']>totals['local_wrong_hmm_correct']and hu>=2
    return {'sources':sources,'four_way_seconds':totals,'hu33_above_positive_harm_threshold':hu,
            'decision':'propose_separate_self_transition_reduction_experiment' if propose else 'stop_localization_mixed_evidence',
            'inferences':recorded['inferences'],'product_changed':False,'plan_sha256':sha(plan),
            'summarizer_sha256':sha(Path(__file__)),'classifier_sha256':sha(Path(__file__).resolve().parents[1]/'app/evaluation/chord_decoder_trace.py')}

if __name__=='__main__':print(json.dumps(run(Path(sys.argv[1])),ensure_ascii=False,indent=2))
