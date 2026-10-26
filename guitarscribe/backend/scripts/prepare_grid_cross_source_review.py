"""Freeze a second-source review: same continuous performance, eighth-grid only."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.chord_grid_candidate import build_chord_grid_candidate
from app.services.chord_entry_performance import build_entry_performance
from app.exporters.midi import export_manifest_midi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/evaluation/grid-cross-source-2026-10-27'
PRIOR = ROOT / 'output/evaluation/entry-performance-regression-2026-10-26'

def read(path):
    return json.loads(path.read_text())

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    write('protocol.json', dict(window=[10, 40], source='Previously reviewed live recording of 情非得已',
        mode='continuous for both A and B', only_score_change='nearest-eighth-v1 chord boundaries',
        control='Previous continuous B, acoustically checked then reused as A',
        decision='A better / B better / similar / both wrong; unclear is valid',
        stop='One fixed comparison; do not tune to a preferred answer or promote a global default',
        limitations='Second recording and song relative to 小手 grid trial; not melody validation'))
    path = ROOT / 'output/evaluation/chord-attack-diagnostic-2026-10-26-verified/B-score.json'
    data = path.read_bytes()
    score = SongScore.model_validate_json(data)
    original_json = score.model_dump_json()
    candidate, report = build_chord_grid_candidate(score)
    assert score.model_dump_json() == original_json
    assert score.beats == candidate.beats and score.melody == candidate.melody
    for old, new in zip(score.chords, candidate.chords):
        assert old.model_dump(exclude={'start', 'end'}) == new.model_dump(exclude={'start', 'end'})
    _, a, _, a_skipped = build_entry_performance(score, 'continuous')
    _, b, _, b_skipped = build_entry_performance(candidate, 'continuous')
    prior_manifest = read(PRIOR / 'B-manifest.json')
    assert a.model_dump(mode='json')['events'] == prior_manifest['events']
    assert [e for e in a.events if e.track != 'guitar'] == [e for e in b.events if e.track != 'guitar']
    for label, s, manifest in [('A', score, a), ('B', candidate, b)]:
        write(label + '-score.json', s.model_dump(mode='json'))
        write(label + '-manifest.json', manifest.model_dump(mode='json'))
        (OUT / (label + '.mid')).write_bytes(export_manifest_midi(manifest))
    source = (PRIOR / 'source.wav').read_bytes()
    assert sha(source) == read(PRIOR / 'report.json')['source_sha256']
    reference = (ROOT / 'frontend/public/listening/entry-performance-regression-2026-10-26/B.wav').read_bytes()
    render = read(PRIOR / 'render-report.json')
    assert sha(reference) == render['outputs'][1]['sha256']
    (OUT / 'source.wav').write_bytes(source)
    (OUT / 'A-reference.wav').write_bytes(reference)
    write('report.json', dict(window=[10, 40], source_sha256=sha(source), score_sha256=sha(data),
        reference_A_sha256=sha(reference), frozen_guitar_gain=render['levels']['guitarGain'],
        grid=report, A_skipped=a_skipped, B_skipped=b_skipped,
        guitar_events=[sum(e.track == 'guitar' for e in m.events) for m in [a,b]],
        listening_hint='每段 30 秒，只需各聽一次。聽不出差異也可以直接回覆。'))
    print(OUT)

if __name__ == '__main__':
    main()
