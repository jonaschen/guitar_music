"""Fixed existing-recording comparison. Never writes jobs or changes live models.

Usage: python benchmark_timing_checkpoints.py GUITARSCRIBE_ROOT OUTPUT_DIR
Uses existing isolated DBN dependencies. First run downloads official final0.
One fixed checkpoint, CPU float32, identical minimal/DBN parameters for all cases.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.timing_quality import timing_quality


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, output):
    import numpy as np
    import torch
    from beat_this.inference import Audio2Frames
    from beat_this.preprocessing import load_audio
    from beat_this.model.postprocessor import Postprocessor
    from importlib.metadata import version

    root = root.resolve(); output.mkdir(parents=True, exist_ok=False)
    summary = json.loads((root/'output/evaluation/cross-song-decoders-2026-11-02/summary-guarded/report.json').read_text())
    by_job = {}
    for work in (root/'output/work', root/'output/web-preview/work'):
        connection = sqlite3.connect(f'file:{work}/jobs/jobs.sqlite3?mode=ro', uri=True)
        for job_id, payload in connection.execute('SELECT id,payload FROM jobs'):
            by_job[job_id] = (work, payload)
        connection.close()
    cases = [dict(job=r['job'], baseline_report=str(root/r['report']),
                  previous_action=r['proposed_action']) for r in summary['rows']]
    cases.extend(dict(job=j, baseline_report=None, previous_action='keep_unmetered') for j in (
        'cd754fa6b231407290c076c2351e917c', '10de4472b18247d99326c42f41d04b0d'))
    for case in cases:
        work, payload = by_job[case['job']]; job = json.loads(payload)
        source = work/'jobs'/case['job']/'input.wav'
        assert job['status']=='completed' and not job['skip_seconds'] and job['analysis_seconds'] is None
        case.update(work=str(work),source=str(source),title=job['score']['song']['title'],
                    source_url=job['source_url'],duration=job['score']['song']['duration_seconds'],
                    source_sha256=digest(source),payload_sha256=hashlib.sha256(payload.encode()).hexdigest())
    plan = dict(checkpoint='final0',control_checkpoint='small0',threads=2,device='cpu',float16=False,
                decoders=['minimal','dbn'],dbn=dict(beats_per_bar=[3,4],min_bpm=55,max_bpm=215,fps=50,transition_lambda=100),
                cases=cases,corpus_kind='previously_seen_recording_regression',automatic_promotion=False)
    (output/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    torch.set_num_threads(2)
    print('Frozen 15 recordings; loading official final0',flush=True)
    predictor = Audio2Frames(checkpoint_path='final0', device='cpu', float16=False)
    checkpoint = Path(torch.hub.get_dir())/'checkpoints/beat_this-final0.ckpt'
    model_sha = digest(checkpoint)
    decoders = {name:Postprocessor(name) for name in ('minimal','dbn')}
    rows = []
    for case in cases:
        started = time.monotonic(); folder=output/case['job']; folder.mkdir()
        source=Path(case['source'])
        baseline_path=Path(case['baseline_report']) if case['baseline_report'] else None
        normalized=baseline_path.parent/'normalized.wav' if baseline_path else folder/'normalized.wav'
        if not normalized.exists():
            normalized=folder/'normalized.wav'
            subprocess.run(['ffmpeg','-v','error','-i',str(source),'-ar','44100','-ac','1',
                            '-sample_fmt','s16','-f','wav',str(normalized)],check=True)
        if baseline_path:
            old=json.loads(baseline_path.read_text())
            assert old['source_sha256']==case['source_sha256']
            baseline=old['decoders']
        else:
            old=json.loads((Path(case['work'])/'jobs'/case['job']/'timing-recovery.json').read_text())
            baseline=dict(minimal=old['primary'],dbn=old['candidate'])
        audio, rate=load_audio(normalized)
        logits=predictor(audio,rate)
        np.savez_compressed(folder/'logits.npz',beat=logits[0].numpy(),downbeat=logits[1].numpy())
        result=dict(case=case,checkpoint='final0',weights_sha256=model_sha,beat_this=version('beat-this'),
                    normalized_sha256=digest(normalized),decoders={},baseline={})
        for name,decoder in decoders.items():
            beats,downs=([float(t) for t in values] for values in decoder(*logits))
            result['decoders'][name]=timing_quality(beats,downs,case['duration'],version('beat-this'))
            result['baseline'][name]=timing_quality(baseline[name]['beats'],baseline[name]['downbeats'],case['duration'])
        result['elapsed_seconds']=time.monotonic()-started
        (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        brief=dict(job=case['job'],title=case['title'],seconds=round(result['elapsed_seconds'],2),
                   final={n:r['issues'] for n,r in result['decoders'].items()},small={n:r['issues'] for n,r in result['baseline'].items()})
        rows.append(brief);(output/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        print(json.dumps(brief,ensure_ascii=False),flush=True)
        connection=sqlite3.connect(f"file:{case['work']}/jobs/jobs.sqlite3?mode=ro",uri=True)
        current=connection.execute('SELECT payload FROM jobs WHERE id=?',(case['job'],)).fetchone()[0];connection.close()
        assert hashlib.sha256(current.encode()).hexdigest()==case['payload_sha256']
        assert digest(source)==case['source_sha256']


if __name__=='__main__':
    run(Path(sys.argv[1]),Path(sys.argv[2]))
