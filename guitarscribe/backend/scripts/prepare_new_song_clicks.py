"""Render frozen raw-beat checks from existing audits. No inference or score writes."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from app.analyzers.beats.timing_diagnostics import describe_observations


def prepare(root: Path, output: Path):
    inputs=[('S8RWhc_LmMc','1de2b4da3efc4b7491b98dae67ba0060'),
            ('WObbdwgB41c','8a89fde02c614127bf6332d7d8db8be1')]
    output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for number,(video,job) in enumerate(inputs,1):
        directory=root/'output/work/jobs'/job
        source=directory/'analysis-source.wav';audit_path=directory/'timing-audit.json'
        audit=json.loads(audit_path.read_text())
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        assert source_hash==audit['sha256'], 'Source differs from frozen timing audit'
        original,sr=sf.read(source,always_2d=True)
        assert abs(len(original)/sr-45)<.01
        evidence=describe_observations(audit['beats'],audit['downbeats'])
        assert evidence['aligned_observations']
        clicks=np.zeros_like(original);events=[]
        for time in audit['beats']:
            sample=round(time*sr)
            assert 0<=sample<len(original)
            length=min(round(.045*sr),len(original)-sample)
            t=np.arange(length)/sr
            clicks[sample:sample+length]+=.5*np.cos(2*np.pi*950*t)[:,None]*np.exp(-t[:,None]/.009)
            events.append(dict(time=time,sample=sample))
        source_gain=.65/max(float(np.max(np.abs(original))),1e-9)
        mixed=original*source_gain+clicks
        gain=min(1.,.95/max(float(np.max(np.abs(mixed))),1e-9))
        audio_hashes={}
        for name,data in [('source',original*source_gain*gain),('click',mixed*gain)]:
            path=output/f'song-{number}-{name}.wav';sf.write(path,data,sr,subtype='PCM_16')
            decoded,actual_sr=sf.read(path,always_2d=True)
            assert actual_sr==sr and decoded.shape==original.shape
            assert np.max(np.abs(decoded-data))<=1/32768+1e-12
            assert np.max(np.abs(decoded))<.951
            audio_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        reports.append(dict(video=video,job=job,source_sha256=source_hash,audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                            sample_rate=sr,frames=len(original),source_gain=source_gain,common_gain=gain,
                            audio_sha256=audio_hashes,events=events,evidence=evidence))
    (output/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
    template=root/'frontend/scripts/new-song-clicks.html'
    (output/'index.html').write_text(template.read_text())
    print(json.dumps([dict(video=r['video'],beats=len(r['events']),spans=r['evidence']['structurally_consistent_spans']) for r in reports],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(Path(__file__).resolve().parents[2],args.output)
