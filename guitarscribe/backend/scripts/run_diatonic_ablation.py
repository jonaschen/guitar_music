"""A21: freeze baseline-derived key and mask cached emissions, author HMM unchanged."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import importlib.metadata
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import sha,write,historical_events,projected_events,parity
from scripts.run_chord_stem_ablation import decision as guarded_decision
from app.analyzers.chords.chordino import decode_chord_events
from app.analyzers.chords.chromagram import estimate_key_from_chords,ROOT_TO_PITCH
from app.evaluation.chord_errors import diagnose_chord_errors,_pitch_classes,_identity
from app.evaluation.chord_dictionary import DictionaryAvailability
from app.evaluation.annotations import QualityAnnotation
from app.models.score import SongScore


def scales(key,mode):
    if key not in ROOT_TO_PITCH or mode not in ('major','minor'):raise ValueError('Unsupported frozen key/mode')
    tonic=ROOT_TO_PITCH[key]
    forms=[(0,2,4,5,7,9,11)] if mode=='major' else [(0,2,3,5,7,8,10),(0,2,3,5,7,8,11)]
    return [{(tonic+pc)%12 for pc in form} for form in forms]


def profile_mask(dictionary,key,mode):
    allowed=[];forms=scales(key,mode)
    for index,entry in enumerate(dictionary):
        weights=entry['weights']
        if entry['index']!=index or len(weights)!=24 or any(not math.isfinite(v) for v in weights):raise ValueError('Invalid indexed dictionary')
        pitches={(i%12+9)%12 for i,v in enumerate(weights) if v>0}
        allowed.append(entry['label']=='N' or bool(pitches) and any(pitches<=form for form in forms))
    if dictionary[-1]['label']!='N' or sum(e['label']=='N' for e in dictionary)!=1:raise ValueError('Expected only final state N')
    return np.array(allowed,dtype=bool)


def raw_events(trace,path):
    frames=trace['frames'];dictionary=trace['dictionary']
    if len(frames)!=len(path) or not frames:raise ValueError('Path/frame count mismatch')
    times=[f['sec']+f['nsec']*1e-9 for f in frames]
    if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Invalid timestamps')
    result=[dict(timestamp=times[0],label=dictionary[int(path[0])]['label'])];old=len(dictionary)-1
    for i in range(1,len(path)):
        state=int(path[i])
        if state!=old:result.append(dict(timestamp=times[i],label=dictionary[state]['label']));old=state
    result.append(dict(timestamp=times[-1],label='N'))
    return result


def raw_parity(expected,actual):
    if len(expected)!=len(actual):return dict(passed=False,expected=len(expected),actual=len(actual))
    for i,(a,b) in enumerate(zip(expected,actual)):
        if a['label']!=b['label'] or abs(a['timestamp']-b['timestamp'])>1e-9:return dict(passed=False,index=i,expected=a,actual=b)
    return dict(passed=True,count=len(actual))


def overlay(before,after,dictionary,allowed,key,mode):
    result=dict(changed_label_seconds=0.,baseline_n_seconds=0.,candidate_n_seconds=0.,root_rescued_seconds=0.,root_harmed_seconds=0.,majmin_rescued_seconds=0.,majmin_harmed_seconds=0.,baseline_strict_missing_reference_seconds=0.,lost_strict_reference_candidate_seconds=0.,reference_outside_frozen_scales_seconds=0.)
    availability=DictionaryAvailability(dictionary);forms=scales(key,mode)
    for row in before['intervals']:
        ref=row['reference_label'];seconds=row['seconds']
        if ref not in ('N','X'):
            if not any(_pitch_classes(ref)<=form for form in forms):result['reference_outside_frozen_scales_seconds']+=seconds
            strict=availability.classify(ref)['matches'].get('strict',[])
            if not strict:result['baseline_strict_missing_reference_seconds']+=seconds
            elif not any(allowed[e['index']] for e in strict):result['lost_strict_reference_candidate_seconds']+=seconds
    i=j=0;a=before['intervals'];b=after['intervals']
    while i<len(a) and j<len(b):
        left,right=max(a[i]['start'],b[j]['start']),min(a[i]['end'],b[j]['end']);seconds=max(0,right-left)
        if seconds:
            x,y=a[i]['estimate_label'],b[j]['estimate_label']
            if _identity(x)!=_identity(y):result['changed_label_seconds']+=seconds
            if x=='N':result['baseline_n_seconds']+=seconds
            if y=='N':result['candidate_n_seconds']+=seconds
            for metric in ('root','majmin'):
                old,new=a[i][metric+'_correct'],b[j][metric+'_correct']
                if old is False and new is True:result[metric+'_rescued_seconds']+=seconds
                if old is True and new is False:result[metric+'_harmed_seconds']+=seconds
        old_end,new_end=a[i]['end'],b[j]['end']
        if old_end<=new_end:i+=1
        if new_end<=old_end:j+=1
    return result


def decision(rows):
    result=guarded_decision([dict(recording_id=r['recording_id'],baseline=r['baseline'],no_vocals=r['candidate']) for r in rows])
    result['outcome']='independent_confirmation_only' if result['passed'] else 'reject_fixed_estimated_key_and_diatonic_mask'
    return result


def run(root,plan_path,output):
    root,plan_path,output=root.resolve(),plan_path.resolve(),output.resolve();plan=json.loads(plan_path.read_text());plan_hash=sha(plan_path)
    output.mkdir(parents=True,exist_ok=False);started=time.monotonic();deadline=started+3600
    env=dict(os.environ)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='2'
    def checked(entry):
        p=Path(entry['path']);p=p if p.is_absolute() else root/p
        if sha(p)!=entry['sha256']:raise ValueError('Frozen hash mismatch: '+str(p))
        return p
    def execute(command,log):
        seconds=deadline-time.monotonic()
        if seconds<=0:raise TimeoutError('Original60min reached')
        with log.open('x') as h:subprocess.run(command,cwd=output,env=env,stdout=h,stderr=subprocess.STDOUT,check=True,timeout=seconds)
    try:
        if sys.byteorder!='little':raise ValueError('Expected frozen little-endian platform')
        for entry in plan['implementation']:checked(entry)
        for name,version in plan['packages'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('Package changed: '+name)
        for key in ('author_cpp','author_header','author_chordino','wrapper','compiler'):checked(plan[key])
        checked(plan['human_plan']);checked(plan['trace_run']);checked(plan['trace_plan']);checked(plan['input_plan']);checked(plan['preparation'])
        cases=plan['inputs']
        if len(cases)!=9:raise ValueError('Expected nine frozen cases')
        for case in cases:
            for key in ('audio','annotation','estimate','raw_cache','trace','trace_events'):checked(case[key])
        manifest=dict(plan_sha256=plan_hash,started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),runner_sha256=sha(__file__),keys={c['recording_id']:c['frozen_key'] for c in cases},limits=plan['limits'])
        write(output/'before-replay-manifest.json',manifest)
        author=checked(plan['author_cpp']);header=checked(plan['author_header']);wrapper=checked(plan['wrapper']);binary=output/'author-viterbi'
        execute([str(checked(plan['compiler'])),'-O2','-std=c++17','-I',str(header.parent),str(wrapper),str(author),'-o',str(binary)],output/'build.log')
        write(output/'build-manifest.json',dict(binary_sha256=sha(binary),author_sha256=sha(author),header_sha256=sha(header),compiler=subprocess.check_output([str(checked(plan['compiler'])),'--version'],text=True).splitlines()[0]))
        rows=[]
        def replay(case,variant,trace,allowed):
            values=np.asarray([f['emission'] for f in trace['frames']],dtype='<f8')
            if values.shape!=(len(trace['frames']),217) or not np.isfinite(values).all() or np.any(values<0) or np.max(np.abs(values.sum(axis=1)-1))>1e-9:raise ValueError('Invalid cached emission')
            if variant=='candidate':values[:,~allowed]=0.
            if np.any(values[:,-1]<=0):raise ValueError('Missing retained N support')
            rid=case['recording_id'];input_path=output/(rid+'-'+variant+'.bin');path_file=output/(rid+'-'+variant+'-path.bin')
            with input_path.open('xb') as h:h.write(struct.pack('<QQ',*values.shape));h.write(values.tobytes())
            execute([str(binary),str(input_path),str(path_file)],output/(rid+'-'+variant+'.log'))
            path=np.fromfile(path_file,dtype='<i4')
            if len(path)!=len(trace['frames']) or np.any(path<0) or np.any(path>=217):raise ValueError('Invalid decoder path')
            if variant=='baseline' and not np.array_equal(path,np.array([f['hmm'] for f in trace['frames']])):raise ValueError('Baseline exact index path mismatch: '+rid)
            if variant=='candidate' and not np.all(allowed[path]):raise ValueError('Excluded state selected')
            raw=raw_events(trace,path);write(output/(rid+'-'+variant+'-raw-events.json'),raw)
            events=historical_events(raw,case['analysis_duration'],case['historical_decoder']);projected=projected_events(events,case)
            saved=SongScore.model_validate_json(checked(case['estimate']).read_text())
            if variant=='baseline':
                observed=json.loads(checked(case['trace_events']).read_text())
                historic=historical_events(observed['raw_events'],case['analysis_duration'],case['historical_decoder'])
                gates=dict(exact_path=True,raw_events=raw_parity(observed['raw_events'],raw),historical_events=parity(historic,events,1e-9),projected_score=parity(saved.chords,projected,1e-9))
                write(output/(rid+'-baseline-gates.json'),gates)
                if not gates['raw_events']['passed'] or not gates['historical_events']['passed'] or not gates['projected_score']['passed']:raise ValueError('Baseline event gate failed: '+rid)
            annotation=QualityAnnotation.model_validate_json(checked(case['annotation']).read_text());report=diagnose_chord_errors(saved.model_copy(update={'chords':projected}),annotation)
            write(output/(rid+'-'+variant+'-diagnostic.json'),report)
            return report
        # All nine gates before the first masked replay.
        for case in cases:
            trace=json.loads(checked(case['trace']).read_text());allowed=profile_mask(trace['dictionary'],*case['frozen_key'])
            if len(allowed)!=217:raise ValueError('Dictionary state count changed')
            report=replay(case,'baseline',trace,allowed)
            rows.append(dict(recording_id=case['recording_id'],frozen_key=case['frozen_key'],old_key_fields=case['old_key_fields'],retained_profiles=int(allowed.sum()),baseline=dict(summary=report['summary'],boundaries=report['boundaries'])))
            print(case['recording_id'],'baseline gates passed',flush=True)
        for case,row in zip(cases,rows):
            trace=json.loads(checked(case['trace']).read_text());allowed=profile_mask(trace['dictionary'],*case['frozen_key']);report=replay(case,'candidate',trace,allowed)
            before=json.loads((output/(case['recording_id']+'-baseline-diagnostic.json')).read_text());row['candidate']=dict(summary=report['summary'],boundaries=report['boundaries']);row['overlay']=overlay(before,report,trace['dictionary'],allowed,*case['frozen_key'])
            print(case['recording_id'],'candidate completed',flush=True)
        for entry in plan['implementation']:checked(entry)
        for key in ('author_cpp','author_header','author_chordino','wrapper','compiler'):checked(plan[key])
        checked(plan['human_plan']);checked(plan['trace_run']);checked(plan['trace_plan']);checked(plan['input_plan']);checked(plan['preparation'])
        for case in cases:
            for key in ('audio','annotation','estimate','raw_cache','trace','trace_events'):checked(case[key])
        if sha(plan_path)!=plan_hash:raise ValueError('Plan changed during replay')
        write(output/'result.json',dict(plan_sha256=plan_hash,sources=rows,decision=decision(rows),wall_seconds=time.monotonic()-started,baseline_replays=9,candidate_replays=9,audio_model_inferences=0,external_requests=0,product_modified=False,input_hashes_verified_after=True))
        print(json.dumps(decision(rows)),flush=True)
    except Exception as e:
        write(output/'failure.json',dict(error=repr(e),wall_seconds=time.monotonic()-started));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.root,args.plan,args.output)
