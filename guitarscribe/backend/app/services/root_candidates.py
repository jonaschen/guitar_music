"""Root clues from observed Chordino emissions. Scores are not probabilities."""
import math
import re

from .transposition import NOTE_TO_PITCH

METHOD = 'root-mean-profile-duration-v1'
NAMES = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B')


def pitch_class(label):
    match = re.match(r'^([A-G][#b]?)', label.replace('♯', '#').replace('♭', 'b'))
    return NOTE_TO_PITCH.get(match[1]) if match else None


def compact_trace(trace, pooling='mean'):
    dictionary = trace['dictionary']
    roots = [pitch_class(entry['label']) for entry in dictionary]
    counts = [roots.count(p) for p in range(12)]
    if pooling not in ('mean', 'max') or any(n == 0 for n in counts):
        raise ValueError('Incomplete root dictionary or pooling method')
    unknown = [i for i, entry in enumerate(dictionary) if roots[i] is None and entry['label'] != 'N']
    if unknown:
        raise ValueError('Unknown root dictionary entries')
    frames = trace['frames']
    times = [f['sec'] + f['nsec'] * 1e-9 for f in frames]
    if any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Invalid frame times')
    rows = []
    for i, frame in enumerate(frames):
        emission = frame['emission']
        if len(emission) != len(roots) or any(not math.isfinite(v) or v < 0 for v in emission):
            raise ValueError('Invalid emission')
        if abs(sum(emission) - 1) > 1e-8:
            raise ValueError('Unnormalized emission')
        if i + 1 == len(frames):
            break  # Never invent the last frame's extent.
        scores, no_chord = [0.] * 12, 0.
        for root, value in zip(roots, emission):
            if root is None:
                no_chord = max(no_chord, value)
            else:
                if pooling == 'mean':
                    scores[root] += value / counts[root]
                else:
                    scores[root] = max(scores[root], value)
        rows.append([times[i], times[i + 1], *scores, no_chord])
    return {'method': f'root-{pooling}-profile-duration-v1', 'frames': rows}


def candidates_for_range(evidence, start, end):
    if not math.isfinite(start + end) or not 0 <= start < end:
        raise ValueError('Invalid candidate interval')
    totals, covered, no_chord = [0.] * 12, 0., 0.
    for row in evidence['frames']:
        a, b = row[:2]
        weight = max(0., min(end, b) - max(start, a))
        if weight:
            covered += weight
            for i in range(12):
                totals[i] += weight * row[2 + i]
            no_chord += weight * row[14]
    result = {'start': start, 'end': end, 'covered_seconds': covered,
              'coverage': min(1., covered / (end - start)), 'candidates': [], 'status': 'insufficient'}
    if covered <= 0:
        return result
    scores = [value / covered for value in totals]
    order = sorted(range(12), key=lambda p: (-scores[p], p))
    if scores[order[0]] <= 0 or no_chord / covered >= scores[order[0]]:
        return result
    # Three arbitrary indices must not disguise a larger exact tie.
    if abs(scores[order[2]] - scores[order[3]]) <= 1e-12:
        result['status'] = 'ambiguous'
        return result
    result.update(status='available', candidates=[{'pitch_class': p, 'name': NAMES[p],
                  'rank': rank + 1, 'score': scores[p]} for rank, p in enumerate(order[:3]) if scores[p] > 0])
    return result


def initial_segments(score):
    """Continuous source-time worksheet, including unanalyzed gaps."""
    duration = score['song']['duration_seconds']
    segments, cursor = [], 0.
    for chord in score['chords']:
        a, b = max(0., chord['start']), min(duration, chord['end'])
        if b <= a:
            continue
        if a < cursor - 1e-9:
            raise ValueError('Overlapping source chords')
        if a > cursor + 1e-9:
            segments.append({'start': cursor, 'end': a, 'original_root': None})
        root = pitch_class(chord['symbol'])
        if segments and root is not None and segments[-1]['original_root'] == root and abs(segments[-1]['end'] - a) < 1e-9:
            segments[-1]['end'] = b
        else:
            segments.append({'start': a, 'end': b, 'original_root': root})
        cursor = b
    if cursor < duration:
        segments.append({'start': cursor, 'end': duration, 'original_root': None})
    return [dict(s, id=f'root-{i}', root=None, status='pending') for i, s in enumerate(segments)]
