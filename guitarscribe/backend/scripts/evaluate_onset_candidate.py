"""Independent, fixed-rule checkpoint for the experimental audio-boundary decoder.

Consumes existing diagnostic artifacts, never jobs/revision databases. Extra
controls are independently authored; failures are retained, not used to tune.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_synthetic_transcription import REFERENCE, render, match_notes
from app.models.melody_contour import MelodyContour
from app.models.audio import NormalizedAudio
from app.models.analysis import BeatAnalysis
from app.analyzers.melody.pyin_adapter import PyinVocalMelodyAnalyzer
from app.evaluation.conservative_notes import decode_bounded


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def gate(reference, notes):
    metrics=match_notes(reference, notes)
    reasons=[]
    if metrics['missing'] or metrics['extra']:
        reasons.append('missing_or_extra_notes')
    if any(abs(x)>.05 for x in metrics['onset_errors_seconds']):
        reasons.append('onset_error_over_50ms')
    if any(abs(x)>.05 for x in metrics['offset_errors_seconds']):
        reasons.append('offset_error_over_50ms')
    for i,j in metrics['pairs']:
        if abs(reference[i]['end']-reference[i]['start']-.075)<1e-6:
            duration=notes[j]['end']-notes[j]['start']
            if not .05<=duration<=.1:
                reasons.append('75ms_note_duration_outside_50_to_100ms')
    return dict(metrics=metrics, passed=not reasons, failure_reasons=reasons)


def independent_controls():
    # Invariance control, fixed before the candidate is evaluated.
    shifted=[dict(id='shift-'+n['id'],start=n['start']+.137,end=n['end']+.137,
                  midi=n['midi']+5) for n in REFERENCE]
    yield 'C01-shifted-transposed', shifted, render(shifted, harmonic=True), 22050
    # One sustained note with smooth vibrato/tremolo, not a series of attacks.
    sr=22050
    audio=np.zeros(8*sr)
    first,last=round(.65*sr),round(6.6*sr)
    t=np.arange(last-first)/sr
    pitch=69+.3*np.sin(2*np.pi*5*t)
    phase=2*np.pi*np.cumsum(440*2**((pitch-69)/12))/sr
    tone=.18*np.sin(phase)*(1+.12*np.sin(2*np.pi*4*t))
    edge=round(.012*sr)
    tone[:edge]*=np.linspace(0,1,edge)
    tone[-edge:]*=np.linspace(1,0,edge)
    audio[first:last]=tone
    yield 'C02-sustained-vibrato', [dict(start=.65,end=6.6,midi=69)],audio,sr


async def run(source, output):
    from app.evaluation.onset_notes import decode_onset_aware
    output.mkdir(parents=True,exist_ok=False)
    began=time.monotonic()
    implementation=Path(__file__).resolve().parents[1]/'app/evaluation/onset_notes.py'
    report=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        candidate_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest(),
        evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Controlled mechanism checks; no real-song accuracy or listening acceptance.',
        gate='One-to-one exact pitch/onset100ms matching; zero missing/extra; all paired onsets/offsets <=50ms; 75ms note length 50..100ms. Mixed-audio negative control excluded.',
        cases={})
    write(output/'report.json',report)
    cases=[]
    for name in ['B01-sine','B02-harmonic','B06-normalized','B05-mixture']:
        contour=MelodyContour.model_validate_json((source/f'{name}-contour.json').read_bytes())
        cases.append((name,REFERENCE,source/f'{name}.wav',contour))
    ideal=MelodyContour.model_validate_json((source/'ideal-contour.json').read_bytes())
    cases.insert(0,('ideal-F0-with-audio',REFERENCE,source/'B01-sine.wav',ideal))
    for name,reference,audio,sr in independent_controls():
        path=output/f'{name}.wav'
        sf.write(path,audio,sr,subtype='PCM_16')
        analysis=await PyinVocalMelodyAnalyzer().analyze(
            NormalizedAudio(path=path,sample_rate=sr,channels=1,duration_seconds=len(audio)/sr),BeatAnalysis(bpm=120))
        write(output/f'{name}-contour.json',analysis.contour.model_dump(mode='json'))
        cases.append((name,reference,path,analysis.contour))
    for name,reference,path,contour in cases:
        samples,sr=sf.read(path)
        original=contour.model_dump_json()
        baseline=[n.model_dump(mode='json') for n in decode_bounded(contour)]
        candidate=[n.model_dump(mode='json') for n in decode_onset_aware(contour,samples,sr)]
        assert original==contour.model_dump_json(), 'Candidate mutated contour'
        assert all(np.isfinite(n['start']+n['end']) and n['end']>n['start'] and 0<=n['midi']<=127 for n in candidate)
        assert all(a['end']<=b['start']+1e-9 for a,b in zip(candidate,candidate[1:])), 'Overlapping notes'
        write(output/f'{name}-reference.json',reference)
        write(output/f'{name}-baseline.json',baseline)
        write(output/f'{name}-candidate.json',candidate)
        report['cases'][name]=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            baseline=gate(reference,baseline),candidate=gate(reference,candidate),
            required=name!='B05-mixture')
        report['passed']=all(c['candidate']['passed'] for c in report['cases'].values() if c['required'])
        report['wall_seconds']=time.monotonic()-began
        write(output/'report.json',report)
        print(name,json.dumps(report['cases'][name]),flush=True)
    assert hashlib.sha256(implementation.read_bytes()).hexdigest()==report['candidate_sha256'], 'Candidate changed mid-run'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=asyncio.run(run(args.source,args.output))
    raise SystemExit(0 if result['passed'] else 1)
