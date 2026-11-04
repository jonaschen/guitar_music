"""One fixed continuation experiment on cached final0 logits; no model reruns.

Usage: python benchmark_tempo_continuity.py MAIN_MODEL_BATCH OUTPUT_DIR
"""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.analyzers.beats.tempo_continuity import tempo_reference,decode_continuity
from app.evaluation.timing_quality import timing_quality


def run(prior,output):
    import numpy as np
    import torch
    torch.set_num_threads(2)
    plan=json.loads((prior/'plan.json').read_text())
    assert len(json.loads((prior/'summary.json').read_text()))==len(plan['cases'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'plan.json').write_text(json.dumps(dict(policy='duration-majority-tempo-v1',
        prior=str(prior.resolve()),band_fraction=.15,minimum_support=.75,
        unchanged_other_dbn_parameters=plan['dbn'],cases=[c['job'] for c in plan['cases']]),indent=2))
    rows=[]
    for case in plan['cases']:
        started=time.monotonic();old=json.loads((prior/case['job']/'report.json').read_text())
        base=old['decoders']['dbn'];reference=None;selected=base;action='retained'
        if not base['engineering_pass']:
            reference=tempo_reference(base['beats'])
            action='rejected_reference'
            if reference['eligible']:
                with np.load(prior/case['job']/'logits.npz') as cache:
                    beats,downs=decode_continuity(torch.from_numpy(cache['beat']),torch.from_numpy(cache['downbeat']),reference)
                selected=timing_quality(beats,downs,case['duration'],old['beat_this'])
                action='candidate' if selected['engineering_pass'] else 'rejected_candidate'
        folder=output/case['job'];folder.mkdir()
        report=dict(case=case,checkpoint='final0',weights_sha256=old['weights_sha256'],
                    beat_this=old['beat_this'],selected_decoder='dbn' if action=='retained' else 'continuity',
                    decoders=dict(dbn=base,continuity=selected),reference=reference,action=action)
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        row=dict(job=case['job'],source=case['source_url'],action=action,
                 reference=reference,issues=selected['issues'],seconds=round(time.monotonic()-started,2))
        rows.append(row);(output/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        print(json.dumps(row,ensure_ascii=False),flush=True)


if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
