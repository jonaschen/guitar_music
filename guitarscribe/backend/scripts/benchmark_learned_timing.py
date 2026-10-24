"""Fixed Beat This diagnostics with explicit training-overlap or official recording exclusion."""
import argparse
import asyncio
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time
import sys

import mir_eval
import numpy as np
import torch
from beat_this.inference import File2Beats

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.benchmark_guitarset_pilot import reference, score_metrics
from app.analyzers.chords.chromagram import ChromagramChordAnalyzer
from app.analyzers.beats.learned_projection import project_learned_beats
from app.models.audio import NormalizedAudio


async def run(args):
    if args.output.exists():raise ValueError('Preserve previous results; use a new directory')
    protocol=json.loads(args.protocol.read_text())
    scope="TRAINING-OVERLAP DIAGNOSTIC ONLY: official Beat This training includes GuitarSet."
    exclusion=None
    if args.checkpoint == "fold3":
        if args.exclusion_split is None:raise ValueError("fold3 requires the official split file")
        split=dict(line.split() for line in args.exclusion_split.read_text().splitlines() if line.strip())
        if any(split.get(identifier+"_mix")!="3" for identifier in protocol["recordings"]):
            raise ValueError("Every recording must be excluded by official fold3")
        scope="OFFICIAL RECORDING-EXCLUSION DIAGNOSTIC: fold3 validation recordings; same progressions may occur in training. Not cross-dataset generalization."
        exclusion={"split_sha256":hashlib.sha256(args.exclusion_split.read_bytes()).hexdigest(),"fold":3}
    args.output.mkdir(parents=True)
    torch.set_num_threads(2)
    started=time.perf_counter()
    tracker=File2Beats(checkpoint_path=args.checkpoint,device='cpu',dbn=False)
    setup=time.perf_counter()-started
    report={'model':args.checkpoint,'package_version':version('beat-this'),'torch':torch.__version__,
            'device':'cpu','threads':2,'dbn':False,'setup_wall_seconds':setup,
            'evaluation_scope':scope,'exclusion':exclusion,
            'records':[],'status':'running'}
    checkpoint=Path(torch.hub.get_dir())/f'checkpoints/beat_this-{args.checkpoint}.ckpt'
    if checkpoint.exists():report['checkpoint_sha256']=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    for identifier in protocol['recordings']:
        audio_path=args.dataset/(identifier+'_mic.wav')
        row={'recording_id':identifier,'manual_timing_edits':0}
        print('Analyzing',identifier,flush=True)
        try:
            started=time.perf_counter()
            beats,downbeats=tracker(str(audio_path))
            row['inference_wall_seconds']=time.perf_counter()-started
            beats=[float(t) for t in beats];downbeats=[float(t) for t in downbeats]
            row['raw_beats']=beats;row['raw_downbeats']=downbeats
            # Annotations enter only after acoustic prediction, never as model inputs.
            ann,_,info=reference(args.dataset/(identifier+'.jams'),audio_path)
            row['raw_timing']={'beat_f_measure':float(mir_eval.beat.f_measure(np.asarray([b.time for b in ann.beats]),np.asarray(beats))),
                               'downbeat_f_measure':float(mir_eval.beat.f_measure(np.asarray([b.time for b in ann.downbeats]),np.asarray(downbeats)))}
            try:
                projected=project_learned_beats(beats,downbeats,version('beat-this'))
                row['projection_status']='supported'
                (args.output/(identifier+'.beats.json')).write_text(projected.model_dump_json(indent=2))
                audio=NormalizedAudio(path=audio_path,sample_rate=44100,channels=info.channels,duration_seconds=ann.excerpt_end)
                chords=await ChromagramChordAnalyzer().analyze(audio,projected)
                score,metrics=score_metrics(projected,chords,ann)
                row['projected_quality']=metrics
                (args.output/(identifier+'.score.json')).write_text(score.model_dump_json(indent=2))
            except ValueError as error:
                row['projection_status']='rejected';row['projection_error']=str(error)
            row['status']='ok';row['audio_sha256']=ann.source_sha256
        except Exception as error:
            row['status']='failed';row['error']=repr(error)
        report['records'].append(row)
        report['status']='complete' if len(report['records'])==len(protocol['recordings']) else 'running'
        (args.output/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:v for k,v in row.items() if k not in ['raw_beats','raw_downbeats','projected_quality']}),flush=True)
    if any(r['status']=='failed' for r in report['records']):raise RuntimeError('One or more inference failures; inspect report')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--checkpoint',choices=['small0','fold3'],default='small0')
    p.add_argument('--exclusion-split',type=Path)
    asyncio.run(run(p.parse_args()))
