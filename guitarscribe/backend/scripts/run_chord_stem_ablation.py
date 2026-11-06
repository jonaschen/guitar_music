"""Frozen offline input-source ablation; never imports or mutates live services."""
from __future__ import annotations
import argparse
import datetime as dt
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import (sha, write, parity, historical_events,
    projected_events, clipped_events)
from app.models.analysis import ChordEvent
from app.models.score import SongScore
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.chord_errors import diagnose_chord_errors


def decision(rows):
    """One candidate, every source guard, and equal-weight HU33 mean."""
    evaluated = []
    for row in rows:
        b, c = row['baseline'], row['no_vocals']
        changes = {k: c['summary']['metrics'][k]['accuracy']-b['summary']['metrics'][k]['accuracy']
                   for k in ('root', 'majmin')}
        changes['missed_false_seconds'] = sum(c['summary']['category_seconds'][k]-b['summary']['category_seconds'][k]
                                             for k in ('missed_chord', 'false_chord'))
        for k in ('precision', 'recall'):
            old, new = b['boundaries'][k], c['boundaries'][k]
            changes['boundary_'+k] = new-old if old is not None and new is not None else None
        guards = {k: math.isfinite(changes[k]) and changes[k] >= -.02-1e-12 for k in ('root', 'majmin')}
        guards['missed_false'] = math.isfinite(changes['missed_false_seconds']) and changes['missed_false_seconds'] <= .25+1e-12
        for k in ('boundary_precision', 'boundary_recall'):
            v = changes[k]
            guards[k] = v is not None and math.isfinite(v) and v >= -.05-1e-12
        # Metrics must have exactly the same reference domain/coverage.
        guards['reference_coverage'] = all(
            abs(b['summary']['metrics'][k]['scored_seconds']-c['summary']['metrics'][k]['scored_seconds']) <= 1e-8
            for k in ('root', 'majmin')) and b['summary']['interval'] == c['summary']['interval']
        evaluated.append(dict(recording_id=row['recording_id'], changes=changes, guards=guards))
    hu = [r['changes']['root'] for r in evaluated if r['recording_id'].startswith('SWD_HU33_')]
    mean = sum(hu)/len(hu) if hu else None
    improved = sum(v >= .05-1e-12 for v in hu)
    passed = (len(rows) == 9 and len({r['recording_id'] for r in rows}) == 9 and len(hu) == 3
              and mean >= .05-1e-12 and improved >= 2 and all(all(r['guards'].values()) for r in evaluated))
    return dict(passed=bool(passed), hu33_mean_root_delta=mean, hu33_improved_count=improved,
                sources=evaluated, outcome='confirmation_only' if passed else 'reject_fixed_source_intervention')


def separate(config):
    import random
    import numpy as np
    import soundfile as sf
    import torch
    import librosa
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    from demucs.htdemucs import HTDemucs
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    random.seed(0); np.random.seed(0); torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    checkpoint = Path(config['checkpoint'])
    if sha(checkpoint) != config['checkpoint_sha256'] or sha(config['audio']) != config['audio_sha256']:
        raise ValueError('Separation input/weights changed')
    # LocalRepo never falls back to a remote model URL.
    model = get_model('955717e8', repo=checkpoint.parent).cpu().eval()
    if not isinstance(model, HTDemucs) or model.sources != ['drums', 'bass', 'other', 'vocals']:
        raise ValueError('Unexpected model architecture/sources')
    if model.samplerate != 44100 or model.audio_channels != 2 or float(model.segment) != 7.8:
        raise ValueError('Unexpected model sample/channel/segment contract')
    y, sr = librosa.load(config['audio'], sr=44100)
    if not np.isfinite(y).all() or not len(y):
        raise ValueError('Invalid input waveform')
    wav = torch.from_numpy(y).repeat(2, 1)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std()
    if not torch.isfinite(std) or std <= 0:
        raise ValueError('Zero or invalid input variance')
    started = time.monotonic()
    with torch.inference_mode():
        sources = apply_model(model, ((wav-mean)/std)[None], device='cpu', shifts=1,
                              split=True, overlap=.25, progress=False, num_workers=0,
                              segment=None)[0]
        # Exactly the Demucs CLI denormalization, no extra gain/clipping.
        sources = sources*std+mean
    if tuple(sources.shape) != (4, 2, len(y)) or not torch.isfinite(sources).all():
        raise ValueError('Separated waveform shape/finiteness mismatch')
    arrays = {name: data.numpy().T for name, data in zip(model.sources, sources)}
    arrays['no_vocals'] = sources[:3].sum(0).numpy().T
    arrays['reconstruction'] = sources.sum(0).numpy().T
    output = Path(config['output']); output.mkdir(exist_ok=False)
    artifacts = {}
    for name, data in arrays.items():
        path = output/(name+'.wav')
        sf.write(path, data, sr, subtype='FLOAT')
        info = sf.info(path)
        if info.frames != len(y) or info.samplerate != sr or info.channels != 2:
            raise ValueError('Saved waveform contract failed')
        artifacts[name] = dict(path=str(path), sha256=sha(path), frames=info.frames,
                               peak=float(np.max(np.abs(data))))
    residual = arrays['reconstruction']-y[:, None]
    write(output/'separation.json', dict(artifacts=artifacts, separation_seconds=time.monotonic()-started,
         model_segment=float(model.segment), input_mean=float(mean), input_std=float(std),
         reconstruction_rmse=float(np.sqrt(np.mean(residual.astype('float64')**2))),
         reconstruction_max_absolute_error=float(np.max(np.abs(residual))),
         note='Four-track sum is diagnostic only; no reconstruction projection or winner selection'))


def run(root, plan_path, output):
    root, plan_path, output = root.resolve(), plan_path.resolve(), output.resolve()
    plan = json.loads(plan_path.read_text()); plan_hash = sha(plan_path)
    output.mkdir(parents=True, exist_ok=False)
    began = time.monotonic(); deadline = began+7200
    env = dict(os.environ, PYTHONPATH='/home/jonas/.cache/guitarscribe-chordino-diagnostic/python')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        env[name] = '2'
    def checked(entry):
        path = Path(entry['path'])
        if not path.is_absolute(): path = root/path
        if sha(path) != entry['sha256']: raise ValueError('Frozen hash mismatch: '+str(path))
        return path
    def execute(command, log):
        remaining = deadline-time.monotonic()
        if remaining <= 0: raise TimeoutError('Two-hour wall limit reached')
        with log.open('x') as h:
            subprocess.run(command, env=env, cwd=output, stdout=h, stderr=subprocess.STDOUT,
                           check=True, timeout=remaining)
    try:
        for entry in plan['implementation']: checked(entry)
        checked(plan['checkpoint'])
        for name, version in plan['packages'].items():
            if importlib.metadata.version(name) != version: raise ValueError('Package version changed: '+name)
        library = checked(plan['library'])
        if (library.parent/'chord.dict').exists(): raise ValueError('External dictionary present')
        env['VAMP_PATH'] = str(library.parent)
        for case in plan['inputs']:
            for k in ('audio', 'annotation', 'estimate', 'raw_cache', 'prepared_audio'): checked(case[k])
        write(output/'before-inference-manifest.json', dict(plan_sha256=plan_hash, runner_sha256=sha(__file__),
              started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), packages=plan['packages'],
              limits=plan['limits'], checkpoint=plan['checkpoint']))
        rows = []
        def chord(case, variant, audio):
            rid = case['recording_id']; target = output/(rid+'-'+variant+'-events.json')
            config = dict(audio=str(audio), audio_sha256=sha(audio), duration_seconds=case['analysis_duration'],
                          library=str(library), library_sha256=sha(library), output=str(target))
            conf = output/(rid+'-'+variant+'-config.json'); write(conf, config)
            execute([sys.executable,str(root/'backend/scripts/run_chord_bass_ablation.py'),'worker',str(conf)],
                    output/(rid+'-'+variant+'.log'))
            result = json.loads(target.read_text())
            raw = historical_events(result['raw_events'], case['analysis_duration'], case['historical_decoder'])
            events = projected_events(raw, case)
            reference = SongScore.model_validate_json(checked(case['estimate']).read_text())
            if variant == 'baseline':
                cached = [ChordEvent.model_validate(e) for e in json.loads(checked(case['raw_cache']).read_text())['chords']]
                gates = dict(full_raw=parity(cached,raw,1e-9),
                    domain_raw=parity(clipped_events(cached,*case['interval']),clipped_events(raw,*case['interval']),1e-9),
                    projected_score=parity(reference.chords,events,1e-9))
                write(output/(rid+'-parity.json'),gates)
                if not all(g['passed'] for g in gates.values()): raise ValueError('Baseline parity failed: '+rid)
            report = diagnose_chord_errors(reference.model_copy(update={'chords':events}),
                      QualityAnnotation.model_validate_json(checked(case['annotation']).read_text()))
            write(output/(rid+'-'+variant+'-diagnostic.json'),report)
            print(json.dumps(dict(recording_id=rid,variant=variant,root=report['summary']['metrics']['root']['accuracy'])),flush=True)
            return dict(summary=report['summary'],boundaries=report['boundaries'],inference_seconds=result['inference_seconds'])
        # Complete all baseline gates before any separation or candidate.
        for case in plan['inputs']:
            rows.append(dict(recording_id=case['recording_id'],baseline=chord(case,'baseline',checked(case['prepared_audio']))))
        for case,row in zip(plan['inputs'],rows):
            rid=case['recording_id']; folder=output/(rid+'-stems')
            config=dict(audio=str(checked(case['prepared_audio'])),audio_sha256=case['prepared_audio']['sha256'],
                        checkpoint=str(checked(plan['checkpoint'])),checkpoint_sha256=plan['checkpoint']['sha256'],output=str(folder))
            conf=output/(rid+'-separate-config.json'); write(conf,config)
            execute([sys.executable,str(Path(__file__).resolve()),'separate',str(conf)],output/(rid+'-separate.log'))
            row['separation']=json.loads((folder/'separation.json').read_text())
            for variant in ('no_vocals','reconstruction'):
                row[variant]=chord(case,variant,checked(row['separation']['artifacts'][variant]))
        if sha(plan_path)!=plan_hash: raise ValueError('Frozen plan changed')
        for case in plan['inputs']:
            for k in ('audio','annotation','estimate','raw_cache','prepared_audio'): checked(case[k])
        for entry in plan['implementation']: checked(entry)
        checked(plan['checkpoint']); checked(plan['library'])
        result=dict(plan_sha256=plan_hash,decision=decision(rows),sources=rows,wall_seconds=time.monotonic()-began,
                    baseline_runs=9,separation_runs=9,candidate_chordino_runs=9,reconstruction_chordino_runs=9,
                    external_requests=0,product_modified=False,original_hashes_verified_after=True)
        write(output/'result.json',result)
        print(json.dumps(result['decision']),flush=True)
    except Exception as e:
        write(output/'failure.json',dict(error=repr(e),wall_seconds=time.monotonic()-began))
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['run','separate'])
    parser.add_argument('path',type=Path); parser.add_argument('--root',type=Path); parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.mode=='separate': separate(json.loads(args.path.read_text()))
    else: run(args.root,args.path,args.output)
