"""Compare sparse vs continuous attacks with identical chord entries/releases.

Diagnostic only. Does not change the compiler, score or production policy.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / 'output/evaluation/boundary-only-2026-10-26'
FULL = ROOT / 'output/evaluation/confirmed-third-timing-2026-10-26'
OUT = ROOT / 'output/evaluation/matched-entry-2026-10-26'


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    write('protocol.json', {
        'feedback': 'B 好像變好了 — tentative preference, not quality acceptance',
        'source_window': [20, 40],
        'A': 'Exact previously preferred sparse B audio/manifest',
        'B': 'Same sparse attacks, plus original subsequent attacks within each chord; all sustain ends equal unchanged chord end',
        'fixed': 'Chord labels/boundaries, first attack pitches/offsets/velocity/direction, voice/release tail, source, original mix gains',
        'variable': 'Additional attacks and their resulting resonance/density only',
        'decision': 'If B retains improvement, matched entries may allow continuous playing; if A remains better, retain sparse baseline and investigate density/resonance. Neither result proves chord accuracy or cross-source quality.',
    })
    score = read(FULL/'B-score.json')
    original = read(FULL/'B-manifest.json')
    a = read(PREVIOUS/'B-manifest.json')
    b = copy.deepcopy(a)
    added, rows = [], []
    for chord in score['chords']:
        events = sorted((e for e in original['events'] if e['track']=='guitar' and e['source_id']==chord['id']), key=lambda e:e['start'])
        first = next(e for e in a['events'] if e['track']=='guitar' and e['source_id']==chord['id'])
        assert first['start'] == chord['start'] and first['sustain_end'] == chord['end']
        for event in events[1:]:
            extra = copy.deepcopy(event)
            extra['end'] = min(extra['end'], chord['end'])
            extra['sustain_end'] = chord['end']
            assert first['start'] < extra['start'] < extra['end']
            assert extra['start']+max(extra['pitch_offsets']) < extra['sustain_end']
            added.append(extra)
        rows.append(dict(symbol=chord['symbol'], boundary=chord['start'], end=chord['end'], additional_attacks=len(events)-1))
    b['events'] = sorted(b['events']+added, key=lambda e:(e['start'],e['id']))
    original_ids = {e['id'] for e in a['events']}
    assert sorted((e for e in b['events'] if e['id'] in original_ids),key=lambda e:e['id']) == sorted(a['events'],key=lambda e:e['id'])
    assert len({e['id'] for e in b['events']}) == len(b['events'])
    assert len(added)==44
    for label, manifest in [('A',a),('B',b)]:
        write(label+'-manifest.json',manifest)
    source = (PREVIOUS/'source.wav').read_bytes()
    sha = hashlib.sha256(source).hexdigest()
    assert sha==read(PREVIOUS/'report.json')['source_sha256']
    (OUT/'source.wav').write_bytes(source)
    reference = (ROOT/'frontend/public/listening/boundary-only-2026-10-26/B.wav').read_bytes()
    sha_reference = hashlib.sha256(reference).hexdigest()
    render = read(PREVIOUS/'render-report.json')
    assert sha_reference == render['outputs'][1]['sha256']
    (OUT/'A-reference.wav').write_bytes(reference)
    write('report.json',dict(window=[0,20],source_sha256=sha,reference_A_sha256=sha_reference,
        frozen_guitar_gain=render['levels']['guitarGain'], attacks=[10,54],rows=rows,
        preserved_sparse_events=True, unchanged_score_sha256=hashlib.sha256((FULL/'B-score.json').read_bytes()).hexdigest()))
    print('Verified 10 identical chord entries; restored 44 subsequent attacks; frozen source and gain.')


if __name__=='__main__':
    main()
