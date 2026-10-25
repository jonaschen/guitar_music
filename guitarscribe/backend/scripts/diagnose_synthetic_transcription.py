"""Independent additive-wave fixtures: mechanism diagnostics, not vocal quality gates.

No GuitarScribe compiler/renderer creates the reference or the input audio.
Writes a new output directory only; never opens the user's job/revision stores.
"""
import argparse
import asyncio
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import time

import mido
import numpy as np
import soundfile as sf
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.melody.pyin_adapter import (PyinVocalMelodyAnalyzer, PYIN_SAMPLE_RATE,
    PYIN_HOP_LENGTH, PYIN_RESOLUTION, PYIN_THRESHOLDS)
from app.analyzers.chords.chordino import ChordinoChordAnalyzer
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.analyzers.preprocessor import FFmpegPreprocessor
from app.evaluation.conservative_notes import decode_bounded
from app.models.analysis import BeatAnalysis
from app.models.audio import NormalizedAudio, AudioAsset, SourceType
from app.models.melody_contour import MelodyContour
from app.services.audio_crop import crop_analysis_audio

RATE = 22050
DURATION = 8.0
ONSET_TOLERANCE = .1
# Hand-authored events, including adjacent repeated pitch, 75ms ornament,
# rest, offbeat onset, and a sustained note across the 6-second bar line.
REFERENCE = [dict(id=f'n{i}', start=a, end=b, midi=p) for i, (a,b,p) in enumerate([
    (.5,1,60), (1,1.5,60), (1.75,2,64), (2,2.5,67),
    (3,3.075,65), (3.25,3.5,64), (3.5,4,62), (4,6.25,69), (6.5,7,67),
])]
CHORDS = [dict(start=a, end=a+2, symbol=s, pitches=p) for a,s,p in [
    (0,'C',[48,52,55]), (2,'Am',[45,48,52]),
    (4,'F',[41,45,48]), (6,'G',[43,47,50])]]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def render(notes, harmonic=False):
    audio = np.zeros(round(DURATION*RATE), dtype=np.float64)
    for note in notes:
        first, last = round(note['start']*RATE), round(note['end']*RATE)
        t = np.arange(last-first)/RATE
        frequency = 440 * 2**((note['midi']-69)/12)
        y = np.sin(2*np.pi*frequency*t)
        if harmonic:
            y = (y + .35*np.sin(4*np.pi*frequency*t) + .15*np.sin(6*np.pi*frequency*t))/1.5
        edge = min(round(.005*RATE), len(y)//2)
        envelope = np.ones(len(y))
        envelope[:edge] = np.linspace(0,1,edge)
        envelope[-edge:] = np.linspace(1,0,edge)
        audio[first:last] += .2*y*envelope
    return audio


def reference_midi(path):
    midi = mido.MidiFile(ticks_per_beat=960)
    track = mido.MidiTrack(); midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    events = []
    for note in REFERENCE:
        events += [(round(note['start']*1920),1,note['midi']), (round(note['end']*1920),0,note['midi'])]
    previous = 0
    for tick, on, pitch in sorted(events):
        track.append(mido.Message('note_on' if on else 'note_off', note=pitch, velocity=90 if on else 0, time=tick-previous))
        previous = tick
    midi.save(path)


def match_notes(reference, predicted):
    # Maximum-cardinality pitch+onset matching; a prediction cannot explain
    # multiple reference notes. Dummy columns represent missed notes.
    cost = np.full((len(reference), len(predicted)+len(reference)), 100.0)
    for i, ref in enumerate(reference):
        for j, pred in enumerate(predicted):
            delta = abs(pred['start']-ref['start'])
            cost[i,j] = delta/ONSET_TOLERANCE if pred['midi']==ref['midi'] and delta<=ONSET_TOLERANCE else 1e6
    rows, cols = linear_sum_assignment(cost)
    pairs = [(int(i),int(j)) for i,j in zip(rows,cols) if j<len(predicted) and cost[i,j]<100]
    onset = [predicted[j]['start']-reference[i]['start'] for i,j in pairs]
    offset = [predicted[j]['end']-reference[i]['end'] for i,j in pairs]
    return dict(reference_count=len(reference), predicted_count=len(predicted), matched=len(pairs),
        missing=len(reference)-len(pairs), extra=len(predicted)-len(pairs), pairs=pairs,
        onset_errors_seconds=onset, offset_errors_seconds=offset,
        onset_abs_p95=float(np.percentile(np.abs(onset),95)) if onset else None,
        offset_abs_p95=float(np.percentile(np.abs(offset),95)) if offset else None,
        offset_within_100ms=sum(abs(x)<=.1 for x in offset),
        short_under_100ms=sum(n['end']-n['start']<.1 for n in predicted))


def frame_metrics(contour):
    counts = dict(reference_voiced=0, correctly_pitched=0, missing_voicing=0, wrong_pitch=0,
                  octave_errors=0, reference_rest=0, voiced_in_rest=0)
    # Frame centre time; 50ms exclusion around reference boundaries declared
    # before running to separate pitch interiors from windowed onset effects.
    boundaries = [n[k] for n in REFERENCE for k in ('start','end')]
    for index, frequency in enumerate(contour.frequencies_hz):
        t = index*contour.hop_seconds
        if t>=DURATION or min(abs(t-b) for b in boundaries)<.05:
            continue
        expected = next((n['midi'] for n in REFERENCE if n['start']<=t<n['end']),None)
        pitch = None if frequency is None else 69+12*np.log2(frequency/440)
        if expected is None:
            counts['reference_rest'] += 1
            counts['voiced_in_rest'] += pitch is not None
        else:
            counts['reference_voiced'] += 1
            if pitch is None:
                counts['missing_voicing'] += 1
            else:
                error = abs(pitch-expected)
                counts['correctly_pitched'] += error<=.5
                counts['wrong_pitch'] += error>.5
                counts['octave_errors'] += abs(error-12)<=.5
    return {key:int(value) for key,value in counts.items()}


async def run(output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    sine, harmonic = render(REFERENCE), render(REFERENCE, True)
    chord_notes = [dict(start=c['start'],end=c['end'],midi=p) for c in CHORDS for p in c['pitches']]
    chord_wave = render(chord_notes, True)*.6
    pulse = np.zeros(len(sine))
    for i in range(16):
        t=np.arange(round(.04*RATE))/RATE
        y=.3*np.exp(-t*90)*np.sin(2*np.pi*(1600 if i%4==0 else 800)*t)
        first=round(i*.5*RATE); pulse[first:first+len(y)]+=y
    waves={'B01-sine':sine, 'B02-harmonic':harmonic, 'B03-chords':chord_wave,
           'B04-pulses':pulse, 'B05-mixture':(harmonic+chord_wave+pulse)*.7}
    reference_midi(output/'reference.mid')
    save(output/'reference.json', dict(notes=REFERENCE,chords=CHORDS,beats=[i*.5 for i in range(16)],
        downbeats=[i*2 for i in range(4)],bpm=120,duration=DURATION))
    report=dict(scope='Mechanism fixtures only: additive sine/harmonics, not realistic vocals or guitar. No Demucs. No musical quality acceptance.',
        renderer='Independent NumPy additive oscillators, fixed phase reset, no randomness, 5ms linear attack/release, zero additional latency',
        sample_rate=RATE, matching='One-to-one exact MIDI + onset within100ms, offsets reported independently',
        frame_pitch_rule='within50cents, excluding50ms around all reference edges',
        commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), cases={})
    report['diagnostic_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['versions']={name:version(name) for name in ['librosa','numpy','scipy','soundfile','beat-this','torch']}
    report['implementation_sha256']={name:hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
        for name in ['app/analyzers/melody/pyin_adapter.py','app/evaluation/conservative_notes.py',
                     'app/analyzers/chords/chordino.py','app/analyzers/beats/beat_this_adapter.py',
                     'app/analyzers/preprocessor.py','app/services/audio_crop.py']}
    report['pyin_parameters']=dict(sample_rate=PYIN_SAMPLE_RATE,hop_length=PYIN_HOP_LENGTH,
        frame_length=2048,resolution=PYIN_RESOLUTION,n_thresholds=PYIN_THRESHOLDS)
    # Exact source pitch control: an F0-only interface has no onset information
    # for adjacent equal-pitch articulations. Test this before blaming pYIN.
    exact_pitch=[next((n['midi'] for n in REFERENCE if n['start']<=i*.005<n['end']),None) for i in range(1600)]
    ideal=MelodyContour(source_artifact_sha256='0'*64,source_start=0,source_end=8,hop_seconds=.005,
        frequencies_hz=[None if p is None else 440*2**((p-69)/12) for p in exact_pitch],
        voiced_probabilities=[0 if p is None else 1 for p in exact_pitch])
    exact_notes=decode_bounded(ideal)
    save(output/'ideal-contour.json',ideal.model_dump(mode='json'))
    save(output/'ideal-contour-G.json',[n.model_dump(mode='json') for n in exact_notes])
    report['ideal_contour_control']=match_notes(REFERENCE,[n.model_dump() for n in exact_notes])
    save(output/'report.json',report)
    for name,wave in waves.items():
        sf.write(output/f'{name}.wav',wave,RATE,subtype='PCM_16')
    sf.write(output/'B06-prefixed.wav',np.concatenate([np.zeros(round(1.25*RATE)),sine]),RATE,subtype='PCM_16')
    await crop_analysis_audio(output/'B06-prefixed.wav',output/'B06-cropped.wav',1.25,DURATION)
    original,_=sf.read(output/'B01-sine.wav')
    cropped,_=sf.read(output/'B06-cropped.wav')
    report['crop_control']=dict(prefix_seconds=1.25,original_frames=len(original),cropped_frames=len(cropped),
        max_sample_error=float(np.max(np.abs(original-cropped))) if len(original)==len(cropped) else None)
    # Retain actual normalized output for offset/resampling audit.
    normalized=await FFmpegPreprocessor().normalize(AudioAsset(path=output/'B06-cropped.wav',source_type=SourceType.LOCAL))
    import shutil
    shutil.copyfile(normalized.path,output/'B06-normalized.wav')
    if normalized.temporary_directory:
        shutil.rmtree(normalized.temporary_directory)
    names=[*waves, 'B06-normalized']
    for name in names:
        path=output/f'{name}.wav'; info=sf.info(path)
        result=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sample_rate=info.samplerate,
            duration=info.duration,source_offset=1.25 if name.startswith('B06') else 0)
        audio=NormalizedAudio(path=path,sample_rate=info.samplerate,channels=info.channels,duration_seconds=info.duration)
        if name in ['B01-sine','B02-harmonic','B05-mixture','B06-normalized']:
            try:
                analysis=await PyinVocalMelodyAnalyzer().analyze(audio,BeatAnalysis(bpm=120))
            except Exception as error:
                result['melody_error']=f'{type(error).__name__}: {error}'
                report['cases'][name]=result
                report['wall_seconds']=time.monotonic()-started
                save(output/'report.json',report)
                raise
            save(output/f'{name}-pyin.json',analysis.model_dump(mode='json'))
            save(output/f'{name}-contour.json',analysis.contour.model_dump(mode='json'))
            bounded=decode_bounded(analysis.contour)
            save(output/f'{name}-G.json',[n.model_dump(mode='json') for n in bounded])
            result['contour']=frame_metrics(analysis.contour)
            result['raw_notes']=match_notes(REFERENCE,[n.model_dump() for n in analysis.notes])
            result['G_notes']=match_notes(REFERENCE,[n.model_dump() for n in bounded])
        if name in ['B03-chords','B05-mixture']:
            try:
                chords=await ChordinoChordAnalyzer().analyze(audio,BeatAnalysis(bpm=120))
                save(output/f'{name}-chords.json',chords.model_dump(mode='json'))
                correct=sum(max(0,min(c.end,r['end'])-max(c.start,r['start'])) for c in chords.chords for r in CHORDS if c.symbol==r['symbol'])
                result['chords']=dict(exact_label_duration_fraction=correct/DURATION,
                    events=len(chords.chords),boundary_errors_seconds=[min((abs(c.start-r['start']) for c in chords.chords),default=None) for r in CHORDS[1:]],
                    boundary_rule='nearest predicted change to each internal reference change; extra changes separately visible in event count; not F1')
            except Exception as error:
                result['chord_error']=str(error)
        if name in ['B04-pulses','B05-mixture']:
            try:
                analyzer=BeatThisBeatAnalyzer()
                beats=await analyzer.analyze(audio)
                save(output/f'{name}-beats.json',beats.model_dump(mode='json'))
                result['beats']=dict(times=[b.time for b in beats.beats],downbeats=[b.time for b in beats.beats if b.beat==1],parameters=analyzer.parameters)
            except Exception as error:
                result['beat_error']=str(error)
                # Preserve raw detections even when conservative projection rejects them.
                if analyzer._predictor is not None:
                    raw_b,raw_d=await asyncio.to_thread(analyzer._predictor,str(path))
                    save(output/f'{name}-raw-beats.json',dict(beats=raw_b.tolist(),downbeats=raw_d.tolist()))
        report['cases'][name]=result
        report['wall_seconds']=time.monotonic()-started
        save(output/'report.json',report)
        print(name, json.dumps(result),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    asyncio.run(run(args.output))
