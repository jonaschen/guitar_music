"""Read-only account of which harmony each scheduled bar strum actually uses.

Distinguishes a boundary missing an attack from a harmony segment not sampled
by this sparse rhythm. Neither is a verdict on the audio's true harmony.
"""
import math

from ..models.score import SongScore
from ..exporters.midi import compile_playback_manifest
from .downbeat_rhythm import PATTERN_ID


def audit_downbeat_harmony(score: SongScore, start: float, end: float) -> dict:
    if not all(math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= score.song.duration_seconds:
        raise ValueError('Invalid audit range')
    if score.rhythm.pattern_id != PATTERN_ID:
        raise ValueError('Requires the bar-downbeat rhythm')
    manifest = compile_playback_manifest(score)  # Also validates the grid and harmony spans.
    events = [e for e in manifest.events if e.track == 'guitar']
    lookup = {c.id: c for c in score.chords}
    rows = []
    for i, beat in enumerate(score.beats):
        if beat.beat != 1 or not start <= beat.time < end:
            continue
        event = next((e for e in events if e.start == beat.time), None)
        period = score.beats[i + 1].time - beat.time if i + 1 < len(score.beats) else None
        boundary = None
        # Same nearest-eighth window as the existing timing candidate. Only
        # contiguous boundaries, not entrances after a rest or an omitted beat.
        if event is not None and period is not None:
            chord = lookup[event.source_id]
            following = next((c for c in score.chords if c.start == chord.end), None)
            if following is not None and 0 < following.start - beat.time <= period / 4:
                first = next((e.start for e in events if e.source_id == following.id), None)
                boundary = dict(chord_id=following.id, symbol=following.symbol,
                                detected=following.start, lag_seconds=following.start - beat.time,
                                first_scheduled_attack=first,
                                wait_seconds=None if first is None else first - following.start,
                                contains_manual_edit=chord.edited or following.edited)
        rows.append(dict(time=beat.time, measure=beat.measure,
                         chord_id=event.source_id if event else None,
                         symbol=lookup[event.source_id].symbol if event else None,
                         pitches=list(event.pitches) if event else [], nearby_late_boundary=boundary))
    represented = {e.source_id for e in events}
    unstruck = [dict(chord_id=c.id, symbol=c.symbol, start=c.start, end=c.end)
               for c in score.chords if c.start < end and c.end > start and c.id not in represented]
    return dict(policy='downbeat-harmony-audit-v1', range=[start, end], rows=rows,
                unstruck_segments=unstruck, playback_revision=manifest.revision,
                source_start_seconds=score.song.source_start_seconds,
                time_basis='score_local', applied=False, saved=False,
                limitation='Scheduling evidence only; unstruck segments are not deleted or judged incorrect. Harmony accuracy remains unconfirmed.')
