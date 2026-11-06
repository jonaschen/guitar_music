"""Frozen author-stem evidence experiment. No chord changes or model downloads."""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import sha,write
from app.evaluation.chord_errors import _pitch_classes
import numpy as np


def qualify(f0,voiced,prob,rms):
    """Three consecutive 100ms cells, without padding or repairing estimates."""
    midi=np.full(len(f0),np.nan)
    good=np.isfinite(f0)&(f0>0)
    midi[good]=69+12*np.log2(f0[good]/440.)
    rounded=np.zeros(len(f0),dtype=int)
    rounded[good]=np.rint(midi[good]).astype(int)
    pc=rounded%12
    eligible=good&voiced&(prob>=.9)&(np.abs(midi-rounded)<=.35)&(rms>=.01*np.max(rms))
    stable=np.zeros(len(f0),dtype=bool)
    for i in range(1,len(f0)-1):
        stable[i]=bool(np.all(eligible[i-1:i+2]) and np.all(pc[i-1:i+2]==pc[i]))
    return pc,stable


def assess(intervals,times,pc,stable,end):
    """Only estimated-chord omission is observable; reference is evaluation only."""
    totals={k:0. for k in ['duration','known_chord','root_correct','root_wrong','stable','stable_chord',
        'stable_correct','stable_wrong','unknown_reference','unknown_estimate','flag','true_positive',
        'false_positive','correct_root_flag','stable_nonchord_bass','flag_nonchord_bass']}
    rows=[];index=0
    for row in intervals:
        a,b=row['start'],min(row['end'],end)
        if b<=a:continue
        ref,est=row['reference_label'],row['estimate_label']
        chord=ref not in ('N','X');correct=row['root_correct'] is True
        wrong=row['root_correct'] is False
        totals['duration']+=b-a
        if chord:totals['known_chord']+=b-a
        if chord and correct:totals['root_correct']+=b-a
        if chord and wrong:totals['root_wrong']+=b-a
        if ref=='X':totals['unknown_reference']+=b-a
        if est=='X':totals['unknown_estimate']+=b-a
        while index<len(times) and times[index]+.05<=a:index+=1
        j=index
        rp,ep=_pitch_classes(ref),_pitch_classes(est)
        while j<len(times) and times[j]-.05<b:
            left,right=max(a,times[j]-.05,0),min(b,times[j]+.05,end)
            sec=right-left
            if sec>0 and stable[j]:
                totals['stable']+=sec
                if chord:totals['stable_chord']+=sec
                if chord and correct:totals['stable_correct']+=sec
                if chord and wrong:totals['stable_wrong']+=sec
                supported=int(pc[j]) in rp
                if ref!='X' and not supported:totals['stable_nonchord_bass']+=sec
                # N estimate has empty pitch set; X is unknown, never a trigger.
                flag=est!='X' and int(pc[j]) not in ep
                tp=flag and row['category']=='wrong_root' and supported
                if flag and ref!='X':
                    totals['flag']+=sec
                    totals['true_positive' if tp else 'false_positive']+=sec
                    if chord and correct:totals['correct_root_flag']+=sec
                    if not supported:totals['flag_nonchord_bass']+=sec
                rows.append(dict(start=left,end=right,bass_pitch_class=int(pc[j]),reference=ref,estimate=est,
                                 observable_flag=bool(flag),reference_contains_bass=supported,true_positive=bool(tp),category=row['category']))
            j+=1
    def ratio(a,b):return totals[a]/totals[b] if totals[b]>0 else None
    metrics=dict(coverage=ratio('stable_chord','known_chord'),coverage_correct=ratio('stable_correct','root_correct'),
        coverage_wrong=ratio('stable_wrong','root_wrong'),precision=ratio('true_positive','flag'),
        recall_all_wrong_root=ratio('true_positive','root_wrong'),correct_root_false_trigger_rate=ratio('correct_root_flag','root_correct'))
    coverage=all(metrics[k] is not None and metrics[k]>=threshold for k,threshold in [('coverage',.3),('coverage_correct',.2),('coverage_wrong',.2)])
    signal=(metrics['precision'] is not None and metrics['precision']>=.8 and metrics['recall_all_wrong_root'] is not None
            and metrics['recall_all_wrong_root']>=.2 and totals['true_positive']>=10
            and metrics['correct_root_false_trigger_rate'] is not None and metrics['correct_root_false_trigger_rate']<=.05)
    outcome=('insufficient_pitch_evidence' if not coverage else
             'eligible_to_propose_recoverability_only' if signal else 'reject_fixed_observable_signal')
    return dict(totals=totals,metrics=metrics,coverage_sufficient=bool(coverage),signal_gates_passed=bool(signal),outcome=outcome),rows


def alignment(mix,stem,band):
    from scipy.signal import butter,sosfiltfilt,correlate,correlation_lags
    if abs(len(mix)-len(stem))/4000>.1 or len(stem)<357*4000:
        return dict(passed=False,reason='length_or_coverage',mix_frames=len(mix),stem_frames=len(stem))
    size=min(len(mix),len(stem));sos=butter(4,band,btype='bandpass',fs=4000,output='sos')
    a=sosfiltfilt(sos,mix[:size]);b=sosfiltfilt(sos,stem[:size]);rows=[]
    for name,left,right in [('whole',0,size)]+[(str(i+1),i*size//3,(i+1)*size//3) for i in range(3)]:
        x=a[left:right]-a[left:right].mean();y=b[left:right]-b[left:right].mean()
        norm=float(np.linalg.norm(x)*np.linalg.norm(y))
        if not math.isfinite(norm) or norm==0:return dict(passed=False,reason='zero_energy')
        corr=correlate(x,y,mode='full',method='fft');lags=correlation_lags(len(x),len(y));mask=np.abs(lags)<=8000
        values=corr[mask]/norm;candidate=lags[mask];best=int(np.argmax(values))
        threshold=(.5 if name=='whole' else .3) if band[0]==35 else (.25 if name=='whole' else .15)
        lag=float(candidate[best]/4000);peak=float(values[best])
        rows.append(dict(section=name,lag_seconds=lag,normalized_correlation=peak,minimum_correlation=threshold,
                         passed=abs(lag)<=.025 and peak>=threshold))
    return dict(passed=all(x['passed'] for x in rows),checks=rows)


def truncated_triangular_transition(n_states,width):
    """Retain a fixed odd triangular prior, restrict destination states, normalize."""
    from scipy.signal import get_window
    if width<1 or width%2!=1 or n_states<2:raise ValueError('Unexpected transition dimensions')
    window=get_window('triangle',width,fftbins=False)
    positions=np.arange(n_states)[None,:]-np.arange(n_states)[:,None]+width//2
    valid=(positions>=0)&(positions<width)
    matrix=np.zeros((n_states,n_states))
    matrix[valid]=window[positions[valid]]
    return matrix/matrix.sum(axis=1,keepdims=True)


def run(root,plan_path,output):
    import soundfile as sf
    import librosa
    root,plan_path,output=root.resolve(),plan_path.resolve(),output.resolve()
    plan=json.loads(plan_path.read_text());plan_hash=sha(plan_path);began=time.monotonic();deadline=began+3600
    if plan.get("absolute_deadline_utc"):
        remaining=(dt.datetime.fromisoformat(plan["absolute_deadline_utc"])-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining<=0:raise TimeoutError("Original absolute deadline reached")
        deadline=min(deadline,began+remaining)
    output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='2'
    def checked(entry):
        p=Path(entry['path']);p=p if p.is_absolute() else root/p
        if sha(p)!=entry['sha256']:raise ValueError('Frozen hash mismatch: '+str(p))
        return p
    try:
        for entry in plan['implementation']:checked(entry)
        mixed=checked(plan['mix']);diagnostic=checked(plan['diagnostic']);checked(plan['author_api']);checked(plan['author_page']);ffmpeg=checked(plan['ffmpeg'])
        for name,version in plan['packages'].items():
            if importlib.metadata.version(name)!=version:raise ValueError('Package version changed: '+name)
        write(output/'before-download-manifest.json',dict(plan_sha256=plan_hash,runner_sha256=sha(__file__),limits=plan['limits'],
            actual_python_argv=[sys.executable,*sys.argv],parent_launcher=Path(f'/proc/{os.getppid()}/cmdline').read_bytes().replace(b'\x00',b' ').decode(),
            thread_environment={key:os.environ.get(key) for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}))
        if plan.get('reuse'):
            reuse=plan['reuse'];cached=json.loads(checked(reuse['before_pitch_manifest']).read_text())
            for entry in reuse['source_artifacts']:checked(entry)
            downloads=cached['downloads'];waves={}
            for role,entry in reuse['wave_artifacts'].items():
                path=checked(entry);y,sr=sf.read(path,dtype='float32')
                if sr!=4000 or not np.isfinite(y).all():raise ValueError('Invalid reused waveform')
                waves[role]=y
            gates=json.loads(checked(reuse['alignment']).read_text())
            if not cached['alignment_passed'] or not all(g['passed'] for g in gates.values()):raise ValueError('Cannot reuse failed alignment')
        else:
            sources={}; downloads=[]
            for item in plan['archives']:
                archive=output/(item['role']+'.zip');digest=hashlib.sha1();size=0
                with urllib.request.urlopen(urllib.request.Request(item['url'],headers=plan.get('download_headers',{})),timeout=min(60,max(1,deadline-time.monotonic()))) as response,archive.open('xb') as h:
                    if response.status!=200:raise ValueError('Archive HTTP failure')
                    while chunk:=response.read(1048576):
                        size+=len(chunk)
                        if size>item['bytes'] or time.monotonic()>deadline:raise ValueError('Download resource limit')
                        digest.update(chunk);h.write(chunk)
                if size!=item['bytes'] or base64.b32encode(digest.digest()).decode().rstrip('=')!=item['sha1_base32']:
                    raise ValueError('Author archive size/SHA1 mismatch')
                with zipfile.ZipFile(archive) as z:
                    candidates=[i for i in z.infolist() if i.filename.replace('\\','/').rsplit('/',1)[-1]==item['member']]
                    if len(candidates)!=1 or candidates[0].file_size>100_000_000:raise ValueError('Unexpected archive member')
                    source=output/(item['role']+'.flac')
                    with z.open(candidates[0]) as src,source.open('xb') as dst:
                        while chunk:=src.read(1048576):dst.write(chunk)
                sources[item['role']]=source
                downloads.append(dict(role=item['role'],archive_sha256=sha(archive),source_sha256=sha(source),bytes=size,member=candidates[0].filename))
            waves={}
            for role,source in dict(mix=mixed,**sources).items():
                path=output/(role+'-4000.wav')
                with (output/(role+'-ffmpeg.log')).open('x') as log:
                    subprocess.run([str(ffmpeg),'-nostdin','-n','-i',str(source),'-ar','4000','-ac','1','-c:a','pcm_f32le',str(path)],
                                   env=env,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.monotonic()))
                y,sr=sf.read(path,dtype='float32')
                if sr!=4000 or not np.isfinite(y).all():raise ValueError('Invalid decoded waveform')
                waves[role]=y
            gates={role:alignment(waves['mix'],waves[role],band) for role,band in [('bass',(35,180)),('piano',(200,1800))]}
        write(output/'alignment.json',gates)
        write(output/'before-pitch-manifest.json',dict(plan_sha256=plan_hash,downloads=downloads,
            wave_sha256={role:sha(checked(plan['reuse']['wave_artifacts'][role])) if plan.get('reuse') else sha(output/(role+'-4000.wav')) for role in waves},alignment_passed=all(g['passed'] for g in gates.values())))
        if not all(g['passed'] for g in gates.values()):
            for entry in plan['implementation']:checked(entry)
            for key in ('mix','diagnostic','author_api','author_page','ffmpeg'):checked(plan[key])
            if sha(plan_path)!=plan_hash:raise ValueError('Plan changed during alignment')
            write(output/'result.json',dict(plan_sha256=plan_hash,original_hashes_verified_after=True,outcome='recording_alignment_unproven_inconclusive',alignment=gates,
                 wall_seconds=time.monotonic()-began,pitch_runs=0,downloads=downloads,product_modified=False));return
        if sha(plan_path)!=plan_hash:raise ValueError('Plan changed before pitch inference')
        for entry in plan['implementation']:checked(entry)
        original_transition=librosa.sequence.transition_local
        def compatible_transition(n_states,width,*,window='triangle',wrap=False):
            if n_states==361 and width==431 and window=='triangle' and not wrap:
                return truncated_triangular_transition(n_states,width)
            return original_transition(n_states,width,window=window,wrap=wrap)
        librosa.sequence.transition_local=compatible_transition
        try:
            f0,voiced,prob=librosa.pyin(waves['bass'],fmin=32.7031956626,fmax=261.625565301,sr=4000,
                frame_length=1024,hop_length=400,center=True,n_thresholds=100,beta_parameters=(2,18),
                boltzmann_parameter=2,resolution=.1,max_transition_rate=35.92,switch_prob=.01,no_trough_prob=.01,fill_na=np.nan)
        finally:
            librosa.sequence.transition_local=original_transition
        rms=librosa.feature.rms(y=waves['bass'],frame_length=1024,hop_length=400,center=True)[0]
        if len(rms)!=len(f0):raise ValueError('Pitch/RMS frame mismatch')
        times=np.arange(len(f0))*.1;pc,stable=qualify(f0,voiced,prob,rms)
        np.savez_compressed(output/'bass-pitch.npz',times=times,f0=f0,voiced=voiced,voiced_prob=prob,rms=rms,pitch_class=pc,stable=stable)
        data=json.loads(diagnostic.read_text());result,rows=assess(data['intervals'],times,pc,stable,357.)
        write(output/'stable-bass-evidence.json',rows)
        for entry in plan['implementation']:checked(entry)
        if plan.get('reuse'):
            for entry in plan['reuse']['source_artifacts']:checked(entry)
            for entry in plan['reuse']['wave_artifacts'].values():checked(entry)
        checked(plan['mix']);checked(plan['diagnostic']);checked(plan['author_api']);checked(plan['author_page']);checked(plan['ffmpeg'])
        if sha(plan_path)!=plan_hash:raise ValueError('Frozen plan changed')
        write(output/'result.json',dict(**result,plan_sha256=plan_hash,alignment=gates,downloads=downloads,
            wall_seconds=time.monotonic()-began,pitch_runs=1,product_modified=False))
        print(json.dumps(result),flush=True)
    except Exception as e:
        write(output/'failure.json',dict(error=repr(e),wall_seconds=time.monotonic()-began));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.plan,a.output)
