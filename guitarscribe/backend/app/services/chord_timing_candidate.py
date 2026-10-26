"""Bounded, reversible performance timing; original detection is retained."""
import hashlib
import json
import math

from ..models.score import SongScore
from ..exporters.midi import compile_playback_manifest

POLICY='late-downbeat-v1'
RECEIPT='chord_timing_receipt'
WARNING='Experimental chord entry timing: bounded late downbeats adjusted; original detected boundaries retained for restoration. Intentional microtiming is not distinguishable automatically.'


def chord_hash(score):
    return hashlib.sha256(json.dumps([c.model_dump(mode='json') for c in score.chords],sort_keys=True).encode()).hexdigest()


def build_timing_candidate(score: SongScore, start: float, end: float):
    if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=score.song.duration_seconds:
        raise ValueError('Invalid confirmed timing range')
    if score.provenance.parameters.get('chord_input_source')!='existing-accompaniment-stem-v1':
        raise ValueError('Requires the explicitly selected accompaniment chord candidate')
    if RECEIPT in score.provenance.parameters:
        raise ValueError('Restore the previous timing candidate before generating another')
    if len({c.id for c in score.chords})!=len(score.chords):
        raise ValueError('Chord IDs must be unique')
    if any(not math.isfinite(c.start+c.end) or c.start<0 or c.end<=c.start or c.end>score.song.duration_seconds for c in score.chords):
        raise ValueError('Invalid chord intervals')
    if any(a.end>b.start+1e-8 for a,b in zip(score.chords,score.chords[1:])):
        raise ValueError('Chord intervals overlap or are out of order')
    if any(not math.isfinite(b.time) for b in score.beats) or any(a.time>=b.time for a,b in zip(score.beats,score.beats[1:])):
        raise ValueError('Beat times must be finite and strictly increasing')
    before=compile_playback_manifest(score)
    attacks=[e for e in before.events if e.track=='guitar']
    downbeats=[(b.time,score.beats[i+1].time-b.time) for i,b in enumerate(score.beats[:-1])
               if b.beat==1 and start<=b.time<end]
    candidate=score.model_copy(deep=True)
    changes=[]; skipped=[]
    for i in range(1,len(score.chords)):
        left,right=score.chords[i-1:i+1];t=right.start
        if not start<t<end:continue
        reason=None
        if abs(left.end-t)>1e-8:reason='gap'
        elif left.edited or right.edited:reason='manual_chord'
        elif left.symbol==right.symbol:reason='same_label'
        nearby=[(beat,period) for beat,period in downbeats if 1e-8<t-beat<=min(.05,period/8)+1e-9]
        if reason is None and not nearby:reason='not_within_50ms_after_downbeat'
        if reason is None:
            beat,period=min(nearby,key=lambda pair:t-pair[0])
            if left.end-left.start<period or right.end-right.start<period:reason='short_neighbor'
            elif not any(abs(e.start-beat)<1e-8 and e.source_id==left.id for e in attacks):reason='no_existing_downbeat_stroke'
            else:
                first=next((e.start for e in attacks if e.source_id==right.id),None)
                if first is None or first-t<period/2:reason='no_half_beat_delay'
        if reason is not None:
            skipped.append(dict(right_id=right.id,detected=t,reason=reason));continue
        if beat<=candidate.chords[i-1].start or beat>=candidate.chords[i].end:
            skipped.append(dict(right_id=right.id,detected=t,reason='would_collapse'));continue
        candidate.chords[i-1].end=beat;candidate.chords[i].start=beat
        changes.append(dict(left_id=left.id,right_id=right.id,detected=t,performance=beat,
                            previous_first_attack=first,local_beat_seconds=period))
    if not changes:return candidate,changes,skipped
    after=compile_playback_manifest(candidate)
    before_attacks=[(e.start,e.stroke) for e in attacks]
    after_attacks=[(e.start,e.stroke) for e in after.events if e.track=='guitar']
    if before_attacks!=after_attacks:raise ValueError('Candidate would change rhythmic attacks')
    if [e for e in before.events if e.track!='guitar']!=[e for e in after.events if e.track!='guitar']:
        raise ValueError('Candidate would change melody or beats')
    receipt=dict(policy=POLICY,range=[start,end],changes=changes,applied_chord_hash=chord_hash(candidate),
                 original_chord_hash=chord_hash(score),
                 warning_added=WARNING not in score.analysis.warnings,
                 beat_grid_sha256=hashlib.sha256(json.dumps([b.model_dump() for b in score.beats],sort_keys=True).encode()).hexdigest(),
                 rhythm_sha256=hashlib.sha256(score.rhythm.model_dump_json().encode()).hexdigest())
    candidate.provenance.parameters[RECEIPT]=json.dumps(receipt,sort_keys=True)
    if receipt['warning_added']:candidate.analysis.warnings.append(WARNING)
    return candidate,changes,skipped


def restore_detected_timing(score: SongScore) -> SongScore:
    raw=score.provenance.parameters.get(RECEIPT)
    if not isinstance(raw,str):raise ValueError('No timing candidate to restore')
    try:
        receipt=json.loads(raw)
        if receipt['policy']!=POLICY or receipt['applied_chord_hash']!=chord_hash(score):
            raise ValueError('Chords changed after timing adjustment; preserve your edits')
        restored=score.model_copy(deep=True);lookup={c.id:c for c in restored.chords}
        for change in receipt['changes']:
            lookup[change['left_id']].end=change['detected']
            lookup[change['right_id']].start=change['detected']
        if chord_hash(restored)!=receipt['original_chord_hash']:raise ValueError('Invalid restoration receipt')
    except (KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Invalid restoration receipt') from exc
    del restored.provenance.parameters[RECEIPT]
    # Remove only the warning added by this service.
    if receipt.get('warning_added',True) and WARNING in restored.analysis.warnings:restored.analysis.warnings.remove(WARNING)
    return restored
