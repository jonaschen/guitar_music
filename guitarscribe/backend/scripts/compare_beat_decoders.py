"""Offline, same-logits comparison. No job writes or production configuration changes.

Requires isolated madmom source installation documented in Downbeat_Rhythm_2026-10-31.md.
Usage: python compare_beat_decoders.py WORK_DIR OUTPUT_DIR JOB_ID [JOB_ID ...]
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(work, output, jobs):
    import numpy as np
    import torch
    from beat_this.inference import Audio2Frames
    from beat_this.preprocessing import load_audio
    from beat_this.model.postprocessor import Postprocessor
    from app.analyzers.beats.learned_projection import project_learned_beats
    from app.analyzers.beats.timing_diagnostics import describe_observations

    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    processors = {name: Postprocessor(name) for name in ('minimal', 'dbn')}
    predictor = Audio2Frames(checkpoint_path='small0', device='cpu', float16=False)
    checkpoint = Path(torch.hub.get_dir()) / 'checkpoints/beat_this-small0.ckpt'
    db = sqlite3.connect(f'file:{work / "jobs/jobs.sqlite3"}?mode=ro', uri=True)
    for job_id in jobs:
        started = time.monotonic()
        payload = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()[0]
        job = json.loads(payload)
        assert job['status'] == 'completed'
        source = work / 'jobs' / job_id / ('analysis-source.wav' if job.get('skip_seconds') or job.get('analysis_seconds') is not None else 'input.wav')
        folder = output / job_id
        folder.mkdir()
        normalized = folder / 'normalized.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-ar', '44100', '-ac', '1',
                        '-sample_fmt', 's16', '-f', 'wav', str(normalized)], check=True)
        signal, sample_rate = load_audio(normalized)
        logits = predictor(signal, sample_rate)
        np.savez_compressed(folder / 'logits.npz', beat=logits[0].numpy(), downbeat=logits[1].numpy())
        report = {'job': job_id, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'job_payload_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                  'weights_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                  'beat_this': version('beat-this'), 'madmom': version('madmom'),
                  'dbn': dict(beats_per_bar=[3, 4], min_bpm=55, max_bpm=215, fps=50, transition_lambda=100),
                  'decoders': {}}
        for name, processor in processors.items():
            beats, downbeats = ([float(t) for t in values] for values in processor(*logits))
            result = describe_observations(beats, downbeats)
            try:
                projected = project_learned_beats(beats, downbeats, version('beat-this'))
                result['projection'] = projected.model_dump(mode='json')
                result['structural_gate'] = 'passed'
            except ValueError as error:
                result['structural_gate'] = 'failed'
                result['reason'] = str(error)
            report['decoders'][name] = result
        evidence_path = work / 'jobs' / job_id / 'timing-rejection.json'
        if evidence_path.exists():
            previous = json.loads(evidence_path.read_text())
            parity = all(report['decoders']['minimal'][k] == previous[k] for k in ('beats', 'downbeats'))
        else:
            previous = job['score']['beats']
            parity = report['decoders']['minimal']['beats'] == [b['time'] for b in previous]
            parity = parity and report['decoders']['minimal']['downbeats'] == [b['time'] for b in previous if b['beat'] == 1]
        report['baseline_exact_parity'] = parity
        report['elapsed_seconds'] = time.monotonic() - started
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({'job': job_id, 'parity': parity, 'decoders': {
            k: dict(gate=v['structural_gate'], beats=len(v['beats']), downbeats=len(v['downbeats']),
                    bpm=v.get('projection', {}).get('bpm')) for k, v in report['decoders'].items()},
            'seconds': report['elapsed_seconds']}), flush=True)
        if not parity:
            raise RuntimeError('Minimal decoder differs from original observations; stop comparison')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('work', type=Path); parser.add_argument('output', type=Path); parser.add_argument('jobs', nargs='+')
    args = parser.parse_args()
    main(args.work, args.output, args.jobs)
