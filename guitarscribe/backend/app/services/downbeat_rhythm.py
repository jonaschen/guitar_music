"""Schedule basic strums from observed bar starts, independently of chord changes.

No extrapolated beats, chord-entry attacks, quantization, or label filtering.
This pattern is opt-in and does not certify the musical accuracy of a grid.
"""
import math

from ..models.score import SongScore

PATTERN_ID = 'observed-downbeats-v1'
NO_CHORD = {'n', 'nc', 'n.c.', 'no_chord'}


def downbeat_events(score: SongScore):
    # Local import keeps the playback compiler as the single event schema.
    from ..exporters.midi import PlaybackEvent, _selected_voicing_pitches, _strum_profile
    from .playable_chords import with_default_voicings

    if score.analysis.timing_status == 'unmetered':
        raise ValueError('拍格尚未確認，無法按小節刷奏。')
    if score.analysis.time_signature not in {'3/4', '4/4'}:
        raise ValueError('每小節一下目前支援 3/4 或 4/4 拍。')
    duration = score.song.duration_seconds
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid audio duration')
    meter = int(score.analysis.time_signature[0])
    beats = score.beats
    if len(beats) < 2 or any(not math.isfinite(b.time) or b.time < 0 or not 1 <= b.beat <= meter for b in beats):
        raise ValueError('A finite, numbered beat grid is required')
    if any(b.time <= a.time or b.beat != a.beat % meter + 1
           or b.measure != a.measure + (b.beat == 1) for a, b in zip(beats, beats[1:])):
        raise ValueError('Beat grid must be ordered and consistently numbered')
    chords = score.chords
    if len({c.id for c in chords}) != len(chords):
        raise ValueError('Duplicate chord IDs')
    if any(not math.isfinite(c.start + c.end) or not 0 <= c.start < c.end <= duration for c in chords):
        raise ValueError('Invalid chord boundaries')
    if any(a.end > b.start for a, b in zip(chords, chords[1:])):
        raise ValueError('Overlapping or unordered chords')

    resolved = with_default_voicings(score)
    pitches = [() if c.symbol.strip().lower() in NO_CHORD else _selected_voicing_pitches(resolved, c)
               for c in resolved.chords]
    # A change of chord does not damp strings. A true rest or gap does.
    ring_limits = [c.end for c in chords]
    for i in range(len(chords) - 2, -1, -1):
        if pitches[i] and pitches[i + 1] and abs(chords[i].end - chords[i + 1].start) < 1e-9:
            ring_limits[i] = ring_limits[i + 1]
    starts = [b.time for b in beats if b.beat == 1 and b.time < duration]
    events, index = [], 0
    for position, start in enumerate(starts):
        while index < len(chords) and chords[index].end <= start:
            index += 1
        if index == len(chords):
            break
        chord = chords[index]
        if start < chord.start or not pitches[index]:
            continue
        end = min(ring_limits[index], starts[position + 1] if position + 1 < len(starts) else duration)
        offsets, velocities = _strum_profile('D', len(pitches[index]), min(.06, (end - start) / 2))
        events.append(PlaybackEvent(
            id=f'{PATTERN_ID}:{position}', track='guitar', start=start, end=end, sustain_end=end,
            pitches=pitches[index], pitch_offsets=offsets, pitch_velocities=velocities,
            velocity=velocities[0], stroke='D', source_id=chord.id,
        ))
    return events
