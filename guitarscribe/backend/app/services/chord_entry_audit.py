"""Read-only detection of a late boundary missing an existing downbeat stroke.

Reports scheduling evidence, not chord correctness or automatic edit approval.
"""
import math

from ..exporters.midi import compile_playback_manifest
from ..models.score import SongScore
from .chord_entry_performance import build_entry_performance


def audit_chord_entries(score: SongScore, mode: str = 'original') -> dict:
    if mode not in {'original','continuous','sparse'}:
        raise ValueError('Unknown performance mode')
    if not math.isfinite(score.song.duration_seconds) or score.song.duration_seconds<=0:
        raise ValueError('Invalid duration')
    if len({c.id for c in score.chords})!=len(score.chords):
        raise ValueError('Chord IDs must be unique')
    if any(not math.isfinite(c.start+c.end) or not 0<=c.start<c.end<=score.song.duration_seconds for c in score.chords):
        raise ValueError('Invalid chord intervals')
    if any(a.end>b.start+1e-8 for a,b in zip(score.chords,score.chords[1:])):
        raise ValueError('Chord intervals overlap or are out of order')
    if any(not math.isfinite(b.time) for b in score.beats) or any(a.time>=b.time for a,b in zip(score.beats,score.beats[1:])):
        raise ValueError('Beat times must be finite and increasing')
    manifest=compile_playback_manifest(score) if mode=='original' else build_entry_performance(score,mode)[1]
    attacks=[e for e in manifest.events if e.track=='guitar']
    downbeats=[(b,n.time-b.time) for b,n in zip(score.beats,score.beats[1:]) if b.beat==1]
    issues=[]
    for left,right in zip(score.chords,score.chords[1:]):
        if left.symbol==right.symbol or abs(left.end-right.start)>1e-8:continue
        nearby=[(b,period) for b,period in downbeats if 1e-8<right.start-b.time<=min(.05,period/8)+1e-9]
        if not nearby:continue
        beat,period=min(nearby,key=lambda pair:right.start-pair[0].time)
        if min(left.end-left.start,right.end-right.start)<period:continue
        old_stroke=next((e for e in attacks if e.source_id==left.id and abs(e.start-beat.time)<1e-8),None)
        first=min((e.start for e in attacks if e.source_id==right.id),default=None)
        if old_stroke is None or first is None or first-right.start<period/2:continue
        beat_index=score.beats.index(beat)
        previous_beat=score.beats[beat_index-1].time if beat_index else 0.0
        issues.append(dict(kind='late_boundary_missed_downbeat',left_id=left.id,right_id=right.id,
            old_chord=left.symbol,new_chord=right.symbol,measure=beat.measure,
            downbeat_seconds=beat.time,detected_boundary_seconds=right.start,first_attack_seconds=first,
            boundary_lag_seconds=right.start-beat.time,wait_after_boundary_seconds=first-right.start,
            wait_after_downbeat_seconds=first-beat.time,local_beat_seconds=period,
            previous_beat_seconds=max(0,previous_beat),
            original_source_downbeat_seconds=score.song.source_start_seconds+beat.time,
            original_source_first_attack_seconds=score.song.source_start_seconds+first,
            contains_manual_edit=left.edited or right.edited))
    return dict(policy='late-boundary-audit-v1',mode=mode,playback_revision=manifest.revision,
        time_basis='score_local',source_start_seconds=score.song.source_start_seconds,
        issues=issues,applied=False,saved=False,
        limitation='Scheduling evidence only. No findings does not establish musical correctness; beat phase and intended microtiming require listening. Nothing is edited.')
