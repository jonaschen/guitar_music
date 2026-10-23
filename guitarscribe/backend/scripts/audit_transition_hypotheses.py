"""Read-only, off-grid transition hypotheses with competing labels and wider search windows."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.chords.chromagram import get_chord_templates


def analyze(sim, times, labels, hypothesis):
    left, right = hypothesis['search']
    old, new = labels.index(hypothesis['from']), labels.index(hypothesis['to'])
    diff = sim[new] - sim[old]
    crossings = []
    for i in np.flatnonzero((times >= left) & (times <= right)):
        pre = (times >= times[i]-.12) & (times < times[i])
        post = (times >= times[i]) & (times < times[i]+.12)
        if pre.any() and post.any() and np.mean(diff[pre] <= 0) >= .8 and np.mean(diff[post] > 0) >= .8:
            crossings.append(float(times[i]))
    clusters = []
    for time in crossings:
        if not clusters or time-clusters[-1][-1] > .04:
            clusters.append([time])
        else:
            clusters[-1].append(time)
    support = []
    for cluster in clusters:
        center=(cluster[0]+cluster[-1])/2
        before=(times>=center-.55)&(times<center-.10)
        after=(times>=center+.10)&(times<center+.55)
        support.append({'time':center,'old_pre_fraction':float(np.mean(diff[before]<0)),
                        'new_post_fraction':float(np.mean(diff[after]>0)),
                        'old_pre_median_margin':float(np.median(-diff[before])),
                        'new_post_median_margin':float(np.median(diff[after]))})
    intervals = []
    for start in np.arange(left, right-.05, .2):
        end = min(float(start+.2), right)
        mask = (times >= start) & (times < end)
        values = sim[:,mask].mean(axis=1)
        order = np.argsort(-values)
        intervals.append({'start':float(start),'end':end,
                          'new_minus_old':float(values[new]-values[old]),
                          'top':[{'label':labels[i],'similarity':float(values[i])} for i in order[:3]]})
    return {**hypothesis, 'crossings':[[c[0],c[-1]] for c in clusters], 'intervals':intervals, 'sustained_support':support}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--hypotheses',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Preserve prior audits; choose a new output file')
    hypotheses=json.loads(args.hypotheses.read_text())
    score=json.loads((args.packet/'score.json').read_text())
    config=json.loads((args.packet/'config.json').read_text())
    job=score['provenance']['parameters']['analysis_source_job_id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',job):raise ValueError('Invalid job')
    templates,labels=get_chord_templates()
    for h in hypotheses:
        if h['from'] not in labels or h['to'] not in labels or not 1<=h['search'][0]<h['search'][1]:
            raise ValueError('Invalid transition hypothesis')
    start=min(h['search'][0] for h in hypotheses)-1
    end=max(h['search'][1] for h in hypotheses)+1
    templates=templates/(np.linalg.norm(templates,axis=1,keepdims=True)+1e-8)
    root=Path(__file__).resolve().parents[2]
    report={'config_id':config['config_id'],'revision':config['revision'],'job':job,
            'method':'Raw audio windows, no beat snapping or lyric timestamps. CQT and two STFT window sizes.',
            'limits':['Crossings are preference changes, not exact chord onsets.',
                      'Passing notes, inversions and shared tones can create competing transitions.',
                      'These are related representations; require musical validation before correction.'],
            'parameters':{'sample_rate':22050,'hop':256,'STFT_windows':[2048,4096],'persistence':.12,'fraction':.8},'sources':{}}
    for source in ('analysis-source','accompaniment-stem'):
        with sf.SoundFile(root/'output/work/jobs'/job/(source+'.wav')) as f:
            sr=f.samplerate;first=round(start*sr);last=round(end*sr)
            if last>len(f):raise ValueError('Insufficient audio context')
            f.seek(first);y=f.read(last-first)
        digest=hashlib.sha256(y.tobytes()).hexdigest()
        if y.ndim>1:y=y.mean(axis=1)
        y=librosa.resample(y,orig_sr=sr,target_sr=22050)
        chromas={'cqt':librosa.feature.chroma_cqt(y=y,sr=22050,hop_length=256)}
        chromas.update({f'stft_{size}':librosa.feature.chroma_stft(y=y,sr=22050,hop_length=256,n_fft=size) for size in (2048,4096)})
        result={'frames':[first,last],'sample_rate':sr,'decoded_samples_sha256':digest,'methods':{}}
        for method,chroma in chromas.items():
            times=first/sr+librosa.frames_to_time(np.arange(chroma.shape[1]),sr=22050,hop_length=256)
            sim=templates@(chroma/(np.linalg.norm(chroma,axis=0,keepdims=True)+1e-8))
            rows=[analyze(sim,times,labels,h) for h in hypotheses]
            result['methods'][method]=rows
            for row in rows:print(source,method,row['name'],row['crossings'])
        report['sources'][source]=result
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
