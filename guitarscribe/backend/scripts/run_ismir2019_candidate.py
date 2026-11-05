"""Bounded original five-model local ensemble; preserves raw authors output."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


WORKER='''import numpy as np
np.int=int
import torch
torch.set_num_threads(2)
from chord_recognition import chord_recognition
import sys
chord_recognition(sys.argv[1],sys.argv[2],'submission')
'''


def run(root):
    root=root.resolve();out=root/'output/evaluation/ismir2019-comparison-2026-11-05'
    plan_path=root/'docs/evaluation/ismir2019-plan-2026-11-05.json';p=json.loads(plan_path.read_text());plan_hash=sha(plan_path)
    source=Path(p['source_path'])
    for name,digest in p['source_sha256'].items():
        if sha(source/name)!=digest:raise ValueError('Source/checkpoint changed')
    ip=root/p['input_plan']['path']
    if sha(ip)!=p['input_plan']['sha256']:raise ValueError('Input plan changed')
    cases=json.loads(ip.read_text())['cases'];deadline=dt.datetime.fromisoformat(p['deadline_utc'].replace('Z','+00:00'))
    env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=''
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='2'
    for case in cases:
        rid=case['recording_id'];lab=out/(rid+'.lab')
        if lab.exists()or(out/(rid+'.log')).exists():raise FileExistsError('No inference retries: '+rid)
        for key in ('audio','annotation','estimate'):
            if sha(root/case[key]['path'])!=case[key]['sha256']:raise ValueError('Input changed')
        remaining=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining<=0:raise TimeoutError('Original segment deadline reached')
        with(out/(rid+'.log')).open('x')as log:
            subprocess.run(['/home/jonas/.cache/guitarscribe-ismir2019/env/bin/python','-c',WORKER,str(root/case['audio']['path']),str(lab)],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=min(600,remaining))
        if not lab.is_file():raise ValueError('Missing raw lab')
        print(rid,'complete',flush=True)
    if sha(plan_path)!=plan_hash:raise ValueError('Plan changed')
    (out/'inference-manifest.json').write_text(json.dumps({'plan_sha256':plan_hash,'runner_sha256':sha(Path(__file__)),'music_ensemble_runs':len(cases),'music_submodel_forwards':5*len(cases),'outputs':{c['recording_id']:sha(out/(c['recording_id']+'.lab'))for c in cases}},indent=2)+'\n')


if __name__=='__main__':run(Path(sys.argv[1]))
