"""Run a pinned local structure candidate into a NEW directory, never the live work DB."""
import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.song_structure import summarize_candidate, verify_source, validate_stems


def configured_model_cache(protocol, fallback):
    """Check the installed weights before starting expensive local inference."""
    for item in protocol.get('runtime_weights', []):
        verify_source(Path(item['path']), item['sha256'])
    cache = Path(protocol.get('model_cache', fallback))
    if 'model_cache' in protocol and not cache.is_dir():
        raise FileNotFoundError('Configured model cache is missing')
    return cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    source = next(s for s in protocol['sources'] if s['job'] == args.job)
    audio = Path(source['audio']).resolve()
    verify_source(audio, source['audio_sha256'])
    cache = configured_model_cache(protocol, args.out.parent / 'model-cache')
    # An existing result is evidence, not permission to overwrite or reuse stale caches.
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = dict(protocol_id=protocol['id'], protocol_sha256=hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
                    source=source, model=protocol['model'], candidate_commit=protocol['candidate_commit'],
                    device=protocol['device'], status='running')
    manifest_path = args.out / 'manifest.json'
    def save():
        temporary = manifest_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(manifest_path)
    save()
    started = time.monotonic()
    try:
        import soundfile as sf
        info = sf.info(audio)
        duration = info.frames / info.samplerate
        if abs(duration - source['root_source']['duration']) > .05:
            raise ValueError('Source duration does not match protocol')
        prep = protocol['preprocessing']
        demix = args.out / 'demix'
        # Run the original CLI in its own environment BEFORE importing the structure
        # model, so two loaded inference runtimes never compete for limited RAM.
        code = ('import random,torch; random.seed(0); torch.manual_seed(0); '
                'torch.set_num_threads(2); from demucs.separate import main; main()')
        command = [prep['python'], '-c', code, '-n', prep['model'], '-d', 'cpu',
                   '--shifts', str(prep['shifts']), '--overlap', str(prep['overlap']),
                   '-j', str(prep['jobs']), '-o', str(demix), str(audio)]
        manifest['preprocessing'] = prep
        manifest['preprocess_command'] = command
        save()
        subprocess.run(command, check=True, timeout=protocol['resource_limits']['seconds_per_song'])
        manifest['stems'] = validate_stems(demix / 'htdemucs' / audio.stem, duration)
        manifest['preprocessing_seconds'] = time.monotonic() - started
        save()
        import torch
        import allin1_infer
        torch.set_num_threads(protocol['threads'])
        torch.set_num_interop_threads(1)
        torch.manual_seed(0)
        # This path is separate from the running app and shared by this experiment's tracks.
        torch.hub.set_dir(str(cache))
        manifest['versions'] = {n: importlib.metadata.version(n) for n in
                                ['all-in-one-infer', 'demucs-infer', 'madmom-infer', 'torch', 'numpy', 'librosa', 'scipy']}
        manifest['audio'] = dict(sample_rate=info.samplerate, channels=info.channels, duration=duration)
        save()
        result = allin1_infer.analyze(audio, out_dir=args.out / 'raw', model=protocol['model'],
                                    device='cpu', multiprocess=False, include_activations=True,
                                    include_embeddings=False, keep_byproducts=True,
                                    demix_dir=demix, spec_dir=args.out / 'spec', skip_separation=True,
                                    sonify=False, visualize=False)
        raw = [dataclasses.asdict(s) for s in result.segments]
        summary = summarize_candidate(raw, duration)
        summary.update(title=source['title'], job=source['job'], fingerprint=source['root_source']['fingerprint'],
                       source_start=source['root_source']['source_start'], duration=duration)
        (args.out / 'candidate.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        verify_source(audio, source['audio_sha256'])
        manifest['checkpoints'] = {str(p.relative_to(cache)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in cache.rglob('*.pth')}
        manifest['status'] = 'candidate_ready_unreviewed'
    except Exception as error:
        manifest.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        manifest.update(elapsed_seconds=time.monotonic() - started,
                        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        save()


if __name__ == '__main__':
    main()
