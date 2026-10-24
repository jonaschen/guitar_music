"""Separate acoustic, segmentation and decoder errors without song-specific tuning.

All runs use annotated beats. The oracle-boundary run additionally uses annotated
chord boundaries; none of these results are automatic-system acceptance scores.
"""
import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import librosa
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.chords.chromagram import (
    ChordDecoderConfig, _detect_harmonic_regions, _decode_region_sequence,
    _group_segments, decode_beat_synchronous_chords, estimate_key_from_chords,
    get_chord_templates,
)
from app.evaluation.chord_evidence import root_evidence_report
from app.models.analysis import ChordAnalysis
from app.models.audio import NormalizedAudio
from app.analyzers.beats.librosa_beats import LibrosaBeatAnalyzer
from benchmark_guitarset_pilot import reference, score_metrics


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(args.protocol.read_text())
    report = {
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Chord diagnosis; baseline and duration_weighted use the named timing source. Oracle always uses reference chord boundaries and is never an automatic result.',
        'timing_source': args.timing,
        'protocol': protocol,
        'analyzer_sha256': hashlib.sha256((Path(__file__).resolve().parents[1] / 'app/analyzers/chords/chromagram.py').read_bytes()).hexdigest(),
        'librosa_version': librosa.__version__,
        'status': 'running',
        'config': ChordDecoderConfig().parameters(),
        'records': [],
    }
    for identifier in protocol['recordings']:
        started = time.perf_counter()
        audio_path = args.dataset / (identifier + '_mic.wav')
        ann, beats, info = reference(args.dataset / (identifier + '.jams'), audio_path)
        if args.timing == 'librosa':
            beats = asyncio.run(LibrosaBeatAnalyzer().analyze(NormalizedAudio(
                path=audio_path, sample_rate=44100, channels=info.channels,
                duration_seconds=ann.excerpt_end)))
        y, sr = librosa.load(str(audio_path), sr=44100)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
        templates, labels = get_chord_templates()
        similarities = (templates / (np.linalg.norm(templates, axis=1, keepdims=True) + 1e-6)) @ (
            chroma / (np.linalg.norm(chroma, axis=0) + 1e-6))
        times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=2048)
        config = ChordDecoderConfig()
        boundaries = sorted({0.0, ann.excerpt_end, *[
            b.time for b in beats.beats if .02 < b.time < ann.excerpt_end - .02]})
        regions = _detect_harmonic_regions(similarities, times, boundaries, config.change_threshold)
        raw = _group_segments([(start, end, labels[int(np.argmax(scores))], 0)
                               for start, end, scores in regions])
        decoded = decode_beat_synchronous_chords(
            similarities, times, beats, ann.excerpt_end, labels, config, preserve_regions=True)
        # One predeclared ablation, not a parameter search: remove all music priors
        # and change penalties while retaining the same regions and emissions.
        neutral = replace(config, base_change_penalty=0, short_event_change_penalty=0,
                          circle_fifths_bonus=0, tonal_prior_scale=0)
        key, mode = estimate_key_from_chords(raw)
        neutral_events = _group_segments(_decode_region_sequence(regions, labels, key, mode, neutral))
        weighted_events = _group_segments(_decode_region_sequence(
            regions, labels, key, mode, replace(config, duration_weighted_emissions=True)))
        oracle_regions = []
        for chord in ann.chords:
            mask = (times >= chord.start) & (times < chord.end)
            if not mask.any():
                raise ValueError('Reference interval has no audio frames')
            oracle_regions.append((chord.start, chord.end, similarities[:, mask].mean(axis=1)))
        oracle = _group_segments([(start, end, labels[int(np.argmax(scores))], 0)
                                  for start, end, scores in oracle_regions])
        variants = {}
        for name, events in [('baseline', decoded), ('no_priors', neutral_events),
                             ('duration_weighted', weighted_events), ('oracle_boundaries', oracle)]:
            analysis = ChordAnalysis(chords=[e for e in events if e.symbol != 'N'], key=key, mode=mode)
            _, metrics = score_metrics(beats, analysis, ann)
            variants[name] = metrics['chord']
        row = {
            'recording_id': identifier, 'audio_sha256': ann.source_sha256,
            'duration_seconds': ann.excerpt_end, 'evaluation_tier': ann.evaluation_tier,
            'manual_edits': 0, 'variants': variants,
            'region_evidence': root_evidence_report(regions, labels, ann.chords),
            'oracle_evidence': root_evidence_report(oracle_regions, labels, ann.chords),
            'decoded_regions': [e.model_dump() for e in decoded],
            'wall_seconds': time.perf_counter() - started,
        }
        report['records'].append(row)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(identifier, {name: round(value['root_weighted_accuracy'], 4)
                           for name, value in variants.items()}, flush=True)
    report['status'] = 'complete'
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timing', choices=['reference', 'librosa'], default='reference')
    run(parser.parse_args())
