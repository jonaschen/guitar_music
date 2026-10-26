"""Publish two immutable follow-along comparisons from existing audit output."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import soundfile as sf

root=Path(__file__).resolve().parents[2]
source=root/'output/evaluation/cross-source-chords-2026-10-26-verified'
public=root/'frontend/public/listening/cross-source-chords-2026-10-26'
if (public/'index.html').exists():
    raise FileExistsError('Do not overwrite a published review')
public.mkdir(parents=True,exist_ok=True)
reports=json.loads((source/'report.json').read_text())
groups=[];checks=[]
for i,report in enumerate(reports):
    path=source/f"{report['id']}-source.wav"
    assert hashlib.sha256(path.read_bytes()).hexdigest()==report['source_sha256']
    samples,sr=sf.read(path,always_2d=True)
    assert abs(len(samples)/sr-report['duration'])<=1/sr
    original_peak=float(np.max(np.abs(samples)))
    gain=min(1.,.9/max(original_peak,1e-12))
    samples=samples*gain  # One shared original audio for A and B; no per-variant gain.
    name=f'{report["id"]}.wav';sf.write(public/name,samples,sr,subtype='PCM_16')
    restored,actual_sr=sf.read(public/name,always_2d=True)
    assert actual_sr==sr and restored.shape==samples.shape
    assert np.max(np.abs(restored-samples))<=1/32768+1e-12
    mapping={'A':'mix','B':'stem'} if i==0 else {'A':'stem','B':'mix'}
    groups.append(dict(title='第三來源 · 原曲 20–40 秒' if i==0 else '小手拉大手 · 既有固定片段',
                       duration=report['duration'],audio=name,A=report[mapping['A']],B=report[mapping['B']]))
    checks.append(dict(id=report['id'],mapping=mapping,frames=len(samples),samplerate=sr,
                       original_peak=original_peak,shared_audio_gain=gain,
                       peak=float(np.max(np.abs(restored))),sha256=hashlib.sha256((public/name).read_bytes()).hexdigest()))
(public/'packet.json').write_text(json.dumps(dict(groups=groups),ensure_ascii=False,indent=2)+'\n')
shutil.copy2(root/'frontend/scripts/cross-source-chords.html',public/'index.html')
(source/'listening-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
