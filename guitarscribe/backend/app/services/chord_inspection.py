"""Unmetered harmony inspection; never manufacture beats or a rhythmic score."""
import math
from ..exporters.midi import PlaybackEvent, _strum_profile
from .voicings import ChordVoicingProvider


def chord_inspection_events(chords, duration, *, tuning=(40,45,50,55,59,64), capo=0, max_fret=15):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid audio duration')
    if any(not math.isfinite(c.start+c.end) or not 0 <= c.start < c.end <= duration for c in chords):
        raise ValueError('Invalid chord boundaries')
    if any(a.end > b.start for a, b in zip(chords, chords[1:])):
        raise ValueError('Overlapping or unordered chords')
    if len({c.id for c in chords}) != len(chords):
        raise ValueError('Duplicate chord IDs')
    provider = ChordVoicingProvider()
    events, unsupported = [], []
    for chord in chords:
        shapes = chord.available_voicings or provider.get(chord.shape_symbol or chord.symbol, capo=capo, max_fret=max_fret)
        if not shapes:
            unsupported.append(chord.id)
            continue
        selected = next((v for v in shapes if v.id == chord.voicing_id), shapes[0])
        pitches = tuple(t+f+capo for t, f in zip(tuning, selected.frets) if f is not None)
        if not pitches:
            unsupported.append(chord.id)
            continue
        offsets, velocities = _strum_profile('D', len(pitches), min(.06, (chord.end-chord.start)/2))
        events.append(PlaybackEvent(id='inspection:'+chord.id, track='guitar',
            start=chord.start, end=chord.end, sustain_end=chord.end,
            pitches=pitches, pitch_offsets=offsets, pitch_velocities=velocities,
            velocity=velocities[0], stroke='D', source_id=chord.id))
    return events, unsupported
