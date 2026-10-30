"""Bounded standard-tuning slash-chord shapes with explicit bass and full harmony.

Search only within a four-fret hand position, allowing open strings and a single
lowest-fret barre. Unknown qualities stay unsupported rather than losing tones.
"""
from functools import lru_cache
from itertools import product
import re

PITCH = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
         'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
         'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
INTERVALS = {'': (0, 4, 7), 'm': (0, 3, 7), '7': (0, 4, 7, 10),
             'maj7': (0, 4, 7, 11), 'm7': (0, 3, 7, 10),
             '6': (0, 4, 7, 9), 'm6': (0, 3, 7, 9), 'm7b5': (0, 3, 6, 10)}
TUNING = (40, 45, 50, 55, 59, 64)
SYMBOL = re.compile(r'^([A-G](?:#|b)?)(maj7|m7b5|m7|m6|7|6|m)?/([A-G](?:#|b)?)$')


def fingering(frets):
    pressed = [i for i, fret in enumerate(frets) if fret not in (None, 0)]
    fingers = [None] * 6
    if not pressed:
        return tuple(fingers)
    lowest = min(frets[i] for i in pressed)
    barre = [i for i in pressed if frets[i] == lowest]
    if len(barre) < 2 or any(frets[i] == 0 for i in range(barre[0], barre[-1] + 1)):
        barre = [min(pressed, key=lambda i: (frets[i], i))]
    remaining = [i for i in pressed if i not in barre]
    if len(remaining) > 3:
        return None
    for i in barre:
        fingers[i] = 1
    for finger, i in enumerate(sorted(remaining, key=lambda i: (frets[i], i)), 2):
        fingers[i] = finger
    return tuple(fingers)


@lru_cache(maxsize=512)
def slash_shapes(symbol: str, max_fret: int):
    match = SYMBOL.fullmatch(symbol)
    if not match or not 0 <= max_fret <= 24:
        return ()
    root, quality, bass = match.groups()
    if root not in PITCH or bass not in PITCH:
        return ()
    expected = {(PITCH[root] + step) % 12 for step in INTERVALS[quality or '']}
    expected.add(PITCH[bass])
    candidates = {}
    for position in range(max_fret + 1):
        frets_in_window = sorted({0, *range(max(1, position), min(max_fret, position + 3) + 1)})
        options = [[None, *(f for f in frets_in_window if (pitch + f) % 12 in expected)] for pitch in TUNING]
        for frets in product(*options):
            if frets in candidates:
                continue
            pitches = [pitch + fret for pitch, fret in zip(TUNING, frets) if fret is not None]
            if len(pitches) < max(4, len(expected)) or min(pitches) % 12 != PITCH[bass]:
                continue
            # Physical low-to-high string order must also start on the named bass.
            if pitches[0] != min(pitches) or {p % 12 for p in pitches} != expected:
                continue
            fingers = fingering(frets)
            if fingers is None:
                continue
            pressed = [f for f in frets if f not in (None, 0)]
            sounded = [i for i, f in enumerate(frets) if f is not None]
            interior_mutes = sum(frets[i] is None for i in range(sounded[0], sounded[-1] + 1))
            rank = (max(pressed, default=0) + interior_mutes * 2, len(pressed), -len(pitches), frets_in_window[0])
            candidates[frets] = (rank, fingers)
    ordered = sorted(candidates, key=lambda frets: (candidates[frets][0], tuple(-1 if f is None else f for f in frets)))[:4]
    return tuple((frets, candidates[frets][1]) for frets in ordered)
