"""Opt-in performance preview; never changes score boundaries or defaults."""
import hashlib
import math

from ..exporters.midi import PlaybackManifest, compile_playback_manifest
from ..models.score import SongScore

POLICY = 'chord-entry-performance-v1'


def build_entry_performance(score: SongScore, mode: str):
    if mode not in {'sparse', 'continuous'}:
        raise ValueError('Choose sparse or continuous performance')
    chords = score.chords
    if len({c.id for c in chords}) != len(chords):
        raise ValueError('Chord IDs must be unique')
    if any(not math.isfinite(c.start+c.end) or not 0 <= c.start < c.end <= score.song.duration_seconds for c in chords):
        raise ValueError('Invalid chord intervals')
    if any(a.end > b.start for a, b in zip(chords, chords[1:])):
        raise ValueError('Chords must be ordered and non-overlapping')
    if any(not math.isfinite(b.time) for b in score.beats) or any(a.time >= b.time for a,b in zip(score.beats,score.beats[1:])):
        raise ValueError('Beat times must be finite and increasing')
    original = compile_playback_manifest(score)
    replacements, changes, skipped = {}, [], []
    for chord in chords:
        attacks = [e for e in original.events if e.track == 'guitar' and e.source_id == chord.id]
        reason = None
        periods = [(a.time, b.time-a.time) for a,b in zip(score.beats,score.beats[1:])]
        period = min(periods,key=lambda p:abs(p[0]-chord.start))[1] if periods else None
        if chord.edited:
            reason = 'manual_chord'
        elif period is None:
            reason = 'no_local_beat_period'
        elif chord.end-chord.start < period:
            reason = 'short_chord'
        elif not attacks:
            reason = 'no_existing_attack'
        elif any(e.start >= chord.end for e in attacks):
            reason = 'merged_harmony_span'
        if reason:
            skipped.append(dict(chord_id=chord.id, reason=reason))
            continue
        first = attacks[0].model_copy(update={'start': chord.start})
        selected = [first] + (attacks[1:] if mode == 'continuous' else [])
        updated = []
        for i, event in enumerate(selected):
            end = selected[i+1].start if i+1<len(selected) else chord.end
            # Protect offsets from crossing a following stroke or short interval.
            if event.start+max(event.pitch_offsets, default=0) >= end:
                reason = 'insufficient_room_for_strings'
                break
            updated.append(event.model_copy(update={
                'id': f'{POLICY}:{mode}:{chord.id}:{i}',
                'end': end, 'sustain_end': chord.end,
            }))
        if reason:
            skipped.append(dict(chord_id=chord.id, reason=reason))
            continue
        replacements[chord.id] = updated
        changes.append(dict(chord_id=chord.id, original_first_attack=attacks[0].start,
                            first_attack=chord.start, original_attacks=len(attacks), candidate_attacks=len(updated)))
    events = [e for e in original.events if e.track != 'guitar' or e.source_id not in replacements]
    events.extend(e for group in replacements.values() for e in group)
    events.sort(key=lambda e:(e.start,e.track,e.id))
    payload = original.model_dump(mode='json')
    payload['events'] = [e.model_dump(mode='json') for e in events]
    candidate = PlaybackManifest.model_validate(payload)
    revision = hashlib.sha256((POLICY+mode+candidate.model_dump_json()).encode()).hexdigest()[:16]
    candidate = candidate.model_copy(update={'revision': revision})
    assert [e for e in original.events if e.track!='guitar'] == [e for e in candidate.events if e.track!='guitar']
    return original, candidate, changes, skipped
