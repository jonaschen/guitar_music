"""Verify a previously fixed second-source grid before any timing application."""
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

root=Path(__file__).resolve().parents[2]
prior=root/'output/evaluation/accompaniment-regression-2026-10-26/third-candidate.json'
score=json.loads(prior.read_text())
source=root/'output/evaluation/cross-source-chords-2026-10-26-verified/third-source.wav'
report=json.loads((source.parent/'report.json').read_text())[0]
assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256']
out=root/'output/evaluation/third-source-click-2026-10-26';out.mkdir(parents=True,exist_ok=False)
public=root/'frontend/public/listening/third-source-click-2026-10-26';public.mkdir(parents=True,exist_ok=False)
config=dict(job=report['job'],window=[20,40],score_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),
            source_sha256=report['source_sha256'],beats=score['beats'],reason='Existing fixed regression window; verify unconfirmed downbeats before timing candidate',
            timing_changed=False)
(out/'frozen-inputs.json').write_text(json.dumps(config,indent=2)+'\n')
original,sr=sf.read(source,always_2d=True);assert len(original)==20*sr
clicks=np.zeros_like(original);events=[]
for beat in score['beats']:
    index=round(beat['time']*sr);length=min(round(.045*sr),len(clicks)-index)
    assert 0<=index<len(clicks) and length>0
    t=np.arange(length)/sr;accent=beat['beat']==1
    clicks[index:index+length]+=(.65 if accent else .5)*np.cos(2*np.pi*(1500 if accent else 950)*t)[:,None]*np.exp(-t[:,None]/.009)
    events.append(dict(sample=index,accent=accent,time=beat['time']))
source_gain=.65/max(float(np.max(np.abs(original))),1e-9)
mix=original*source_gain+clicks;gain=min(1.,.95/max(float(np.max(np.abs(mix))),1e-9))
audio=public/'original-plus-click.wav';sf.write(audio,mix*gain,sr,subtype='PCM_16')
decoded,read_sr=sf.read(audio,always_2d=True)
assert read_sr==sr and decoded.shape==original.shape
assert np.max(np.abs(decoded-mix*gain))<=1/32768+1e-12
assert np.max(np.abs(decoded))<.951
html=(root/'frontend/scripts/frozen-click.html').read_text()
html=html.replace('30 秒','20 秒').replace('原曲 10–40 秒，包含先前 Bar 8–15 的問題片段。不是修正版。','第三來源原曲 20–40 秒，沿用既有固定片段。這段拍格尚未確認，沒有修正時間。')
(public/'index.html').write_text(html)
result=dict(events=events,samplerate=sr,frames=len(decoded),peak=float(np.max(np.abs(decoded))),source_gain=source_gain,
            common_gain=gain,audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),musical_verdict='pending')
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
print('20 seconds;',len(events),'clicks; peak',result['peak'])
