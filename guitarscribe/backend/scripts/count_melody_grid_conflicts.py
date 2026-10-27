"""Read-only onset feasibility audit on frozen G/SOME artifacts; never emits a score."""
import argparse
from bisect import bisect_left
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = Path('docs/diagnostics/2026-10-27/melody-grid-feasibility')


def read(path):
    return json.loads(path.read_text())


def grid_points(beats, divisions):
    assert divisions in (4, 8) and len(beats) >= 2
    assert all(math.isfinite(x) for x in beats)
    assert all(a < b for a, b in zip(beats, beats[1:]))
    return [a + (b-a)*i/divisions for a, b in zip(beats, beats[1:])
            for i in range(divisions)] + [beats[-1]]


def raw_some(chunks):
    notes = []
    for chunk_index, chunk in enumerate(chunks):
        position = chunk['offset']
        assert len(chunk['note_dur']) == len(chunk['note_rest']) == len(chunk['note_midi'])
        for event_index, (duration, rest, pitch) in enumerate(zip(chunk['note_dur'], chunk['note_rest'], chunk['note_midi'])):
            assert math.isfinite(duration) and duration > 0
            if not rest:
                notes.append(dict(start=position, end=position+duration, midi=round(pitch),
                                  raw_pitch=pitch, chunk=chunk_index, raw_event=event_index))
            position += duration
    return notes


def count(notes, points, duration):
    assert notes and points
    assert all(math.isfinite(n[k]) for n in notes for k in ('start', 'end', 'midi'))
    assert all(n['start'] < n['end'] for n in notes)
    assert all(a['start'] <= b['start'] for a, b in zip(notes, notes[1:]))
    bins = defaultdict(list)
    mapped, uncovered, outside = [], [], []
    for index, note in enumerate(notes):
        record = dict(note, index=index+1, original_duration=note['end']-note['start'])
        if not points[0] <= note['start'] <= points[-1]:
            uncovered.append(record)
            continue
        right = bisect_left(points, note['start'])
        if right == 0:
            chosen = 0
        else:
            left = right-1
            chosen = left if note['start']-points[left] <= points[right]-note['start']+1e-12 else right
        record.update(grid_index=chosen, mapped_start=points[chosen], shift=points[chosen]-note['start'])
        bins[chosen].append(record)
        mapped.append(record)
        if not 0 <= points[chosen] < duration:
            outside.append(record)
    groups = [dict(grid_index=index, grid_time=points[index], notes=items)
              for index, items in sorted(bins.items()) if len(items) > 1]
    affected = sum(len(g['notes']) for g in groups)
    excess = sum(len(g['notes'])-1 for g in groups)
    adjacent = [(a,b) for a,b in zip(mapped,mapped[1:])
                if b['index']==a['index']+1 and a['grid_index']==b['grid_index']]
    return dict(note_count=len(notes), collision_groups=len(groups), involved_notes=affected,
                involved_fraction=affected/len(notes), excess_occupants=excess,
                excess_fraction=excess/len(notes), adjacent_collision_pairs=len(adjacent),
                same_pitch_adjacent_collision_pairs=sum(a['midi']==b['midi'] for a,b in adjacent),
                uncovered_onsets=uncovered, outside_clip_mappings=outside,
                onset_collision_gate_passed=not groups and not uncovered,
                deletions=0, merges=0, groups=groups, mapping=mapped)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing diagnostic report')
    protocol_path = ROOT/REL/'protocol.json'
    protocol = read(protocol_path)
    for file, expected in protocol['inputs'].items():
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest() == expected, file
    def load(relative):
        return read(ROOT/'output/evaluation'/relative)
    third = load('third-source-2026-10-25/G-score.json')
    frozen = load('third-source-click-2026-10-26/frozen-inputs.json')
    assert third['analysis']['time_signature'] == '4/4'
    existing = [dict(b, time=b['time']-20) for b in third['beats'] if 20 <= b['time'] < 40]
    assert existing == frozen['beats'], 'Third source grid differs from human-confirmed click'
    saved = load('saved-accompaniment-workspace-2026-10-26/score.json')
    accepted = load('saved-song-entry-2026-10-26/score.json')
    assert saved['analysis']['time_signature'] == '4/4' and saved['beats'] == accepted['beats']
    external = load('external-comparison-2026-10-25/manifest.json')['files'][1]
    shift = saved['song']['source_start_seconds'] - external['original_seconds'][0]
    assert abs(shift) < 1/44100, 'Unexpected saved excerpt origin discrepancy'
    meta = load('final-some-2026-10-27/listening-inputs.json')
    transport = read(ROOT/'docs/diagnostics/2026-10-27/final-some/transport-check.json')
    cases = []
    for clip, beats, origin_shift in [('third-1',[b['time']-20 for b in third['beats']],-20),
                                     ('saved-G',[b['time']+shift for b in saved['beats']],shift)]:
        info = next(m for m in meta if m['id']==clip)
        baseline = Path(info['baseline'])
        proof = next(m for m in transport if m['id']==clip)
        assert hashlib.sha256(baseline.read_bytes()).hexdigest()==proof['baseline_sha256']
        g = read(baseline)
        some = raw_some(load(f'final-some-2026-10-27/{clip}-raw.json'))
        exported = load(f'final-some-2026-10-27/{clip}-notes.json')
        assert len(some)==len(exported)
        assert [n['midi'] for n in some]==[n['midi'] for n in exported]
        raw_error = max(abs(a[k]-b[k]) for a,b in zip(some,exported) for k in ('start','end'))
        assert raw_error < .001, 'Raw SOME event identity/time differs from evaluated MIDI'
        for label, notes in [('G',g),('SOME_raw',some)]:
            for divisions in (4,8):
                points = grid_points(beats,divisions)
                result = count(notes,points,info['duration'])
                result.update(clip=clip,model=label,denominator=divisions*4,
                              reference_only=divisions==8,duration=info['duration'],
                              beat_origin_shift_seconds=origin_shift,
                              raw_some_vs_midi_max_error=raw_error if label=='SOME_raw' else None)
                cases.append(result)
    for file, expected in protocol['inputs'].items():
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==expected, 'Input mutated: '+file
    report = dict(protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  inputs_unchanged=True, source_origin_shift_saved_seconds=shift,
                  no_model_execution=True, no_audio_generated=True, cases=cases)
    with args.output.open('x') as f:
        json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    for c in cases:
        print(c['clip'],c['model'],c['denominator'],
              {k:c[k] for k in ('note_count','collision_groups','involved_notes','excess_occupants','same_pitch_adjacent_collision_pairs')},
              'uncovered',len(c['uncovered_onsets']),'outside',len(c['outside_clip_mappings']))


if __name__ == '__main__':
    main()
