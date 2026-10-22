"""Read-only, beat-independent harmony evidence; measurements are not chord ground truth."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote
from urllib.request import urlopen

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.chords.chromagram import get_chord_templates


def summarize(similarities, times, labels, spans, start, end):
    rows = []
    for i, span in enumerate(spans):
        if span['end'] <= start or span['start'] >= end:
            continue
        left, right = max(start, span['start']), min(end, span['end'])
        trim = min(.15, (right-left)/4)
        mask = (times >= left+trim) & (times < right-trim)
        mean = np.mean(similarities[:, mask], axis=1)
        ranking = np.argsort(-mean)
        row = {**span, 'measured_interval': [left+trim, right-trim],
               'top': [{'label': labels[j], 'similarity': float(mean[j])} for j in ranking[:4]],
               'saved_label_rank': int(np.where(ranking == labels.index(span['symbol']))[0][0])+1}
        if i and start <= span['start'] < end:
            old = spans[i-1]['symbol']; new = span['symbol']; boundary = span['start']
            diff = similarities[labels.index(new)]-similarities[labels.index(old)]
            before = (times >= boundary-.35) & (times < boundary-.10)
            after = (times >= boundary+.10) & (times < boundary+.35)
            # Require preference on both sides for 120ms. No beat-grid snapping.
            crossings = []
            for j in np.flatnonzero((times >= boundary-.5) & (times <= boundary+.65)):
                pre = (times >= times[j]-.12) & (times < times[j])
                post = (times >= times[j]) & (times < times[j]+.12)
                if np.mean(diff[pre] <= 0) >= .8 and np.mean(diff[post] > 0) >= .8:
                    crossings.append(float(times[j]))
            clusters = []
            for t in crossings:
                if not clusters or t-clusters[-1][-1] > .04: clusters.append([t])
                else: clusters[-1].append(t)
            row['boundary'] = {'from': old, 'to': new, 'saved_time': boundary,
                'new_minus_old_before': float(np.median(diff[before])),
                'new_minus_old_after': float(np.median(diff[after])),
                'persistent_crossing_clusters': [[min(c), max(c)] for c in clusters]}
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.start < 1 or args.end <= args.start: parser.error('Invalid analysis-time interval')
    url = args.api.rstrip('/')+'/revisions/'+quote(args.revision, safe='')
    def read_score():
        with urlopen(url, timeout=30) as response: return json.load(response)
    score = read_score(); job = score['provenance']['parameters']['analysis_source_job_id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', job): raise ValueError('Invalid job ID')
    spans = []
    for c in score['chords']:
        if spans and spans[-1]['symbol'] == c['symbol'] and abs(spans[-1]['end']-c['start']) < 1e-8:
            spans[-1]['end'] = c['end']; spans[-1]['region_ids'].append(c['id'])
        else: spans.append({'symbol':c['symbol'], 'start':c['start'], 'end':c['end'], 'region_ids':[c['id']]})
    templates, labels = get_chord_templates()
    templates = templates/(np.linalg.norm(templates, axis=1, keepdims=True)+1e-8)
    if any(s['symbol'] not in labels for s in spans): raise ValueError('Unsupported template label')
    root = Path(__file__).resolve().parents[2]
    report = {'revision':args.revision, 'analysis_interval':[args.start,args.end], 'sources':{},
        'method':'CQT and STFT chroma on raw mixed/source-separated audio; no beat segmentation or label decoder. Span averages and persistent pairwise crossings only.',
        'limits':'Chroma representations are not independent ground truth. Shared tones, vocals, separation, smoothing and window width affect boundaries. Do not auto-delete or shift chords.',
        'parameters':{'sample_rate':22050,'hop':256,'STFT_n_fft':4096,'pre_post_seconds':.12,'required_fraction':.8}}
    for source in ('analysis-source','accompaniment-stem'):
        with sf.SoundFile(root/'output/work/jobs'/job/(source+'.wav')) as f:
            sr=f.samplerate; first=round((args.start-1)*sr); last=round((args.end+1)*sr)
            if last>len(f): raise ValueError('Audio lacks context')
            f.seek(first); y=f.read(last-first)
        if y.ndim>1:y=y.mean(axis=1)
        y=librosa.resample(y, orig_sr=sr, target_sr=22050)
        chromas={'cqt':librosa.feature.chroma_cqt(y=y,sr=22050,hop_length=256),
                 'stft':librosa.feature.chroma_stft(y=y,sr=22050,n_fft=4096,hop_length=256)}
        results={}
        for method,chroma in chromas.items():
            times=first/sr+librosa.frames_to_time(np.arange(chroma.shape[1]),sr=22050,hop_length=256)
            sim=templates@(chroma/(np.linalg.norm(chroma,axis=0,keepdims=True)+1e-8))
            results[method]=summarize(sim,times,labels,spans,args.start,args.end)
        report['sources'][source]=results
    if read_score()!=score:raise RuntimeError('Saved score changed during audit')
    report['saved_score_unchanged']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    for source,methods in report['sources'].items():
        for method,rows in methods.items():
            print(source,method)
            for row in rows:
                print(round(row['start'],3),row['symbol'],'rank',row['saved_label_rank'],'top',[(r['label'],round(r['similarity'],3)) for r in row['top']], 'cross',row.get('boundary',{}).get('persistent_crossing_clusters'))


if __name__ == '__main__':main()
