"""Fixed-parameter baseline on preselected real guitar recordings; no per-song tuning."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import mir_eval
import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.analyzers.beats.librosa_beats import LibrosaBeatAnalyzer
from app.analyzers.chords.chromagram import ChromagramChordAnalyzer
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.quality_report import evaluate_quality_layers, _boundary_scores, _mir_eval_chord_label
from app.models.audio import NormalizedAudio
from app.models.analysis import BeatAnalysis, BeatInfo
from app.models.score import SongScore, AnalysisSummary


def merged(regions, start, end, label_key):
    out=[]
    for r in regions:
        left,right=max(start,r['start']),min(end,r['end'])
        if right<=left:continue
        label=_mir_eval_chord_label(r[label_key]).split('/')[0]
        if out and out[-1]['label']==label and abs(out[-1]['end']-left)<1e-7:out[-1]['end']=right
        else:out.append({'start':left,'end':right,'label':label})
    return out


def reference(jams, audio_path):
    data=json.loads(jams.read_text());annotations=data['annotations']
    chord_tracks=[a for a in annotations if a['namespace']=='chord']
    performed=[a for a in chord_tracks if 'manual verification' in a['annotation_metadata'].get('data_source','')]
    if len(performed)!=1:raise ValueError('Expected one performance-informed chord annotation')
    info=sf.info(audio_path);end=min(info.duration,data['file_metadata']['duration'],60)
    beat_track=next(a for a in annotations if a['namespace']=='beat_position')
    tempo=next(a for a in annotations if a['namespace']=='tempo')['data'][0]['value']
    chords=merged([{'start':r['time'],'end':r['time']+r['duration'],'label':r['value']}for r in performed[0]['data']],0,end,'label')
    # Refuse gaps rather than invent silence where annotations are missing.
    if not chords or chords[0]['start']!=0 or abs(chords[-1]['end']-end)>1e-6:
        raise ValueError('Chord annotation does not cover excerpt')
    if any(abs(a['end']-b['start'])>1e-6 for a,b in zip(chords,chords[1:])):raise ValueError('Annotation gaps')
    points=[r for r in beat_track['data'] if 0<=r['time']<end]
    ann=QualityAnnotation(recording_id=audio_path.stem.removesuffix('_mic'),evaluation_tier='quality_gate',
        annotation_status='reviewed',reviewed_by='GuitarSet authors; dataset performance-informed chord annotation',
        source_file=audio_path.name,source_sha256=hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        rights_note='GuitarSet v1.1.0, Xi et al., Zenodo 3371780, CC BY 4.0; original audio unmodified.',
        difficulty='easy',excerpt_start=0,excerpt_end=end,tempo_bpm=tempo,
        beats=[{'time':r['time']}for r in points],downbeats=[{'time':r['time']}for r in points if r['value']['position']==1],chords=chords,
        listening_notes=['Dataset chord boundaries/root derived from chord sheets; not independently reviewed precise acoustic change times. No lead melody annotation imported.'])
    beats=BeatAnalysis(bpm=tempo,beats=[BeatInfo(time=r['time'],beat=r['value']['position'],measure=r['value']['measure'])for r in points])
    return ann,beats,info


def score_metrics(beats,chords,ann):
    regions=merged([e.model_dump()for e in chords.chords],0,ann.excerpt_end,'symbol')
    # Evaluate merged harmony labels; beat-sliced duplicate regions are not chord changes.
    score=SongScore(analysis=AnalysisSummary(bpm=beats.bpm),beats=beats.beats,
        chords=[{'id':f'c{i}','start':r['start'],'end':r['end'],'symbol':r['label']}for i,r in enumerate(regions)])
    metrics=evaluate_quality_layers(score,ann)
    metrics['chord']['merged_boundary_100ms']=_boundary_scores([r.start for r in ann.chords[1:]],[r['start'] for r in regions[1:]],.10)
    ref_labels=[r.label for r in ann.chords];dur=np.array([r.end-r.start for r in ann.chords])
    eligible=mir_eval.chord.majmin(ref_labels,ref_labels)>=0
    metrics['chord']['majmin_reference_coverage']=float(dur[eligible].sum()/dur.sum())
    return score,metrics


async def run(args):
    if args.output.exists():raise ValueError('Choose new output directory')
    protocol=json.loads(args.protocol.read_text());args.output.mkdir(parents=True)
    results=[]
    for identifier in protocol['recordings']:
        print('Analyzing',identifier,flush=True)
        try:
            ann,reference_beats,info=reference(args.dataset/(identifier+'.jams'),args.dataset/(identifier+'_mic.wav'))
            audio=NormalizedAudio(path=args.dataset/(identifier+'_mic.wav'),sample_rate=44100,channels=info.channels,duration_seconds=ann.excerpt_end)
            started=time.perf_counter()
            beats=await LibrosaBeatAnalyzer().analyze(audio)
            chord_analyzer=ChromagramChordAnalyzer()
            chords=await chord_analyzer.analyze(audio,beats)
            seconds=time.perf_counter()-started
            score,metrics=score_metrics(beats,chords,ann)
            diagnostic_start=time.perf_counter()
            diagnostic_chords=await chord_analyzer.analyze(audio,reference_beats)
            diag_score,diag_metrics=score_metrics(reference_beats,diagnostic_chords,ann)
            row={'recording_id':identifier,'status':'ok','duration_seconds':ann.excerpt_end,
                 'automatic':metrics,'reference_beats_diagnostic_only':diag_metrics,
                 'automatic_wall_seconds':seconds,'diagnostic_wall_seconds':time.perf_counter()-diagnostic_start,
                 'manual_per_recording_edits':0,'engine':{'chord':chords.engine_version,'parameters':chord_analyzer.parameters},
                 'audio_sha256':ann.source_sha256}
            for suffix,value in [('annotation',ann),('automatic-score',score),('reference-beat-score',diag_score)]:
                (args.output/f'{identifier}.{suffix}.json').write_text(value.model_dump_json(indent=2))
        except Exception as error:
            row={'recording_id':identifier,'status':'failed','error':repr(error)}
        results.append(row)
        (args.output/'report.json').write_text(json.dumps({'protocol':protocol,'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'recordings':results,
            'status':'running' if len(results)<len(protocol['recordings']) else 'complete',
            'limitations':'Guitar-only baseline; no product playback/melody/mixed-song acceptance. Annotated-beat run is diagnostic, never automatic.'},indent=2))
        print(json.dumps(row),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    asyncio.run(run(p.parse_args()))
