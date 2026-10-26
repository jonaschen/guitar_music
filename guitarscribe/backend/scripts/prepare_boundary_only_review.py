"""Frozen third-source ablation: change accompaniment attack pattern only.

Diagnostic manifests, not a new score/compiler policy. No snapping or inference.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'output/evaluation/confirmed-third-timing-2026-10-26'
OUTPUT = ROOT / 'output/evaluation/boundary-only-2026-10-26'


def write(name, value):
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    write('protocol.json', {
        'source_window': [20, 40], 'basis': 'Previously rejected third-source B',
        'A': 'Exact previous B manifest, full strum pattern',
        'B': 'One attack at each unchanged chord boundary, using that chord first attack voicing/direction/velocity/offsets; sustain to unchanged chord end',
        'fixed': 'Source crop, chord labels/boundaries, voicings, product voice including release tail, common audio gains',
        'limits': 'Changes attack pattern and resulting overlap/density together; cannot distinguish these mechanisms. Not a chord-accuracy grade or production candidate.',
        'decision': 'If boundary-only improves, investigate accompaniment arrangement; if neither works, revisit harmonic evidence. Do not infer whole-beat shift or relax snap threshold.',
    })
    score = json.loads((INPUT / 'B-score.json').read_text())
    a = json.loads((INPUT / 'B-manifest.json').read_text())
    b = copy.deepcopy(a)
    events, rows = [], []
    for chord in score['chords']:
        original = min((e for e in a['events'] if e['track'] == 'guitar' and e['source_id'] == chord['id']), key=lambda e: e['start'])
        event = copy.deepcopy(original)
        event.update(id='boundary-only:' + chord['id'], start=chord['start'], end=chord['end'], sustain_end=chord['end'])
        assert event['start'] + max(event['pitch_offsets']) < event['end']
        events.append(event)
        rows.append(dict(symbol=chord['symbol'], boundary=chord['start'], previous_attack=original['start'], removed_wait=original['start']-chord['start']))
    b['events'] = sorted([e for e in b['events'] if e['track'] != 'guitar'] + events, key=lambda e: (e['start'], e['id']))
    assert [e for e in a['events'] if e['track'] != 'guitar'] == [e for e in b['events'] if e['track'] != 'guitar']
    assert len(events) == len(score['chords']) == 10
    source = (INPUT / 'source.wav').read_bytes()
    sha = hashlib.sha256(source).hexdigest()
    assert sha == json.loads((INPUT / 'report.json').read_text())['source_sha256']
    (OUTPUT / 'source.wav').write_bytes(source)
    write('A-manifest.json', a)
    write('B-manifest.json', b)
    reference = (ROOT / 'frontend/public/listening/confirmed-third-timing-2026-10-26/B.wav').read_bytes()
    reference_sha = hashlib.sha256(reference).hexdigest()
    assert reference_sha == json.loads((INPUT/'render-report.json').read_text())['outputs'][1]['sha256']
    (OUTPUT/'A-reference.wav').write_bytes(reference)
    write('report.json', dict(window=[0, 20], source_sha256=sha, rows=rows,
        reference_A_sha256=reference_sha,
        attacks=[sum(e['track']=='guitar' for e in a['events']), len(events)],
        unchanged_score_sha256=hashlib.sha256((INPUT/'B-score.json').read_bytes()).hexdigest()))
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
