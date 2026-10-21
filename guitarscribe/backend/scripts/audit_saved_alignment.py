"""Read-only timing audit of a saved score and its compiled accompaniment.

This reports timing semantics and local beat irregularity; it does not infer
musical correctness or modify the saved score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from urllib.parse import quote
from urllib.request import Request, urlopen


def read_json(url, payload=None):
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def audit(score, manifest, first_bar, last_bar):
    starts = {b['measure']: b['time'] for b in score['beats'] if b['beat'] == 1}
    start, end = starts[first_bar], starts[last_bar + 1]
    beats = sorted(score['beats'], key=lambda b: b['time'])
    intervals = [(b, nxt['time'] - b['time']) for b, nxt in zip(beats, beats[1:])
                 if start <= b['time'] < end]
    if any(dt <= 0 for _, dt in intervals):
        raise ValueError('Duplicate or unordered beat times')
    median = statistics.median(dt for _, dt in intervals)
    spans = []
    for chord in sorted(score['chords'], key=lambda c: c['start']):
        if spans and spans[-1]['symbol'] == chord['symbol'] and abs(spans[-1]['end'] - chord['start']) < 1e-9:
            spans[-1]['end'] = chord['end']
        else:
            spans.append({key: chord[key] for key in ('symbol', 'start', 'end')})
    changes = []
    for chord in spans:
        if not start <= chord['start'] < end:
            continue
        attack = next((event['start'] for event in manifest['events']
                       if event['track'] == 'guitar' and chord['start'] - 1e-9 <= event['start'] < chord['end']), None)
        changes.append(dict(chord, first_guitar_attack=attack,
                            delay_ms=None if attack is None else (attack - chord['start']) * 1000))
    expected = [(n['start'], n['end'], n['midi']) for n in score['melody']]
    actual = [(e['start'], e['end'], e['pitches'][0]) for e in manifest['events'] if e['track'] == 'melody']
    return {
        'interpretation': 'Timing evidence only; musical alignment requires source verification.',
        'range': {'first_bar': first_bar, 'last_bar': last_bar, 'analysis_start': start,
                  'analysis_end': end, 'original_file_offset': score['song'].get('source_start_seconds', 0)},
        'median_beat_seconds': median,
        'bars': [{'bar': m, 'duration': starts[m + 1] - starts[m],
                  'beat_intervals': [dt for b, dt in intervals if b['measure'] == m]}
                 for m in range(first_bar, last_bar + 1)],
        'chord_changes': changes,
        'rhythm': score['rhythm'],
        'compiled_melody_matches_saved_notes': sorted(expected) == sorted(actual),
        'manifest_revision': manifest['revision'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--first-bar', type=int, default=28)
    parser.add_argument('--last-bar', type=int, default=35)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    url = args.api.rstrip('/') + '/revisions/' + quote(args.revision, safe='')
    score = read_json(url)
    report = audit(score, read_json(args.api.rstrip('/') + '/scores/playback/manifest', score),
                   args.first_bar, args.last_bar)
    if read_json(url) != score:
        raise RuntimeError('Saved revision changed during audit')
    report.update(revision=args.revision, saved_revision_unchanged=True,
                  score_sha256=hashlib.sha256(json.dumps(score, sort_keys=True).encode()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
