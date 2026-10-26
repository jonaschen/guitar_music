"""One fixed descriptive chroma audit; no decoder, threshold tuning or edits."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
JOB = 'db79e1145ea046088b8aa5ef421d0e3f'
OUT = ROOT / 'output/evaluation/user-chord-evidence-2026-10-26'


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=False)
    fixed = dict(job=JOB, window=[10, 40], sample_rate=22050, hop=512,
                 feature='librosa chroma_stft, n_fft=2048, norm=2, tuning=0',
                 sources=['analysis-source.wav', 'accompaniment-stem.wav'],
                 comparison='mean cosine similarity of binary chord pitch-class sets; original versus preceding accepted chord',
                 restriction='Descriptive only; no calibrated threshold, no causal claim, no new model; all 18 original events included',
                 known_limit='Chroma loses octave/bass voicing and contains melody/harmonics; slash bass counted as a pitch class only')
    write(OUT/'protocol.json', fixed)
    with sqlite3.connect(f'file:{ROOT}/output/work/jobs/jobs.sqlite3?mode=ro', uri=True) as db:
        score = json.loads(db.execute('select payload from jobs where id=?', (JOB,)).fetchone()[0])['score']
    raw = json.loads((ROOT/f'output/work/jobs/{JOB}/chord-analysis.json').read_text())
    original = json.loads((ROOT/'docs/diagnostics/2026-10-26/frozen-chords.json').read_text())
    accepted = json.loads((ROOT/'docs/diagnostics/2026-10-26/user-chord-omissions.json').read_text())
    # Exact pitch-class spellings for the fixed existing labels, not simplified triads.
    pcs = {'C':[0,4,7], 'F':[5,9,0], 'G':[7,11,2], 'Am':[9,0,4], 'Em':[4,7,11],
           'F6':[5,9,0,2], 'Fmaj7':[5,9,0,4], 'F/G':[5,9,0,7], 'C6':[0,4,7,9], 'Am7':[9,0,4,7]}
    templates = {}
    for symbol, pitches in pcs.items():
        v = np.zeros(12); v[pitches] = 1
        templates[symbol] = v/np.linalg.norm(v)
    rows = []
    for c in original['chords']:
        absolute_start = 10+c['start']
        saved = next(s for s in score['chords'] if s['start'] <= absolute_start+1e-7 < s['end'])
        r = next(s for s in raw['chords'] if s['id'] == saved['id'])
        assert (r['symbol'],r['start'],r['end']) == (saved['symbol'],saved['start'],saved['end'])
        midpoint = (c['start']+c['end'])/2
        target = next(s for s in accepted['chords'] if s['start'] <= midpoint < s['end'])['symbol']
        rows.append(dict(**c, full_event_duration=saved['end']-saved['start'],
                         user_named_omission=any(abs(c['start']-s['start'])<1e-8 for s in accepted['omitted']),
                         accepted_followalong_symbol=target, confidence=saved['confidence'],
                         review_reasons=saved['review_reasons'], raw_matches_score=True, acoustic={}))
    hashes = {}
    for source in fixed['sources']:
        path = ROOT/f'output/work/jobs/{JOB}'/source
        hashes[source] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Compute on full stored source to avoid crop-edge feature differences.
        y, sr = librosa.load(path, sr=22050)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=2048, hop_length=512, norm=2, tuning=0)
        times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=512)
        np.savez_compressed(OUT/f'{source}.features.npz', times=times, chroma=chroma)
        for row in rows:
            mask = (times>=10+row['start']) & (times<10+row['end'])
            vectors = chroma[:,mask]
            a = templates[row['symbol']] @ vectors
            b = templates[row['accepted_followalong_symbol']] @ vectors
            row['acoustic'][source] = dict(frames=int(mask.sum()), original_similarity=float(a.mean()),
                                          accepted_similarity=float(b.mean()),
                                          accepted_minus_original=float((b-a).mean()))
    report = dict(protocol=fixed, source_sha256=hashes, librosa_version=librosa.__version__, rows=rows,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  seconds=time.monotonic()-started,
                  decision='No automatic candidate produced; interpret descriptors with user feedback, never as ground truth')
    write(OUT/'report.json', report)
    for r in rows:
        if r['user_named_omission']:
            print(r['start'],r['symbol'],'->',r['accepted_followalong_symbol'],r['review_reasons'],
                  {s:round(v['accepted_minus_original'],4) for s,v in r['acoustic'].items()})
    print('seconds',report['seconds'])


if __name__ == '__main__':
    main()
