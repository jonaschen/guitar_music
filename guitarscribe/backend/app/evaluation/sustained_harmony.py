"""Compare held guitar pitches with the existing score, never with musical truth."""
import math
from collections import defaultdict

from ..exporters.midi import compile_playback_manifest, _selected_voicing_pitches
from ..services.playable_chords import with_default_voicings
from ..services.downbeat_rhythm import NO_CHORD


def audit_sustained_harmony(score, start, end):
    if not all(math.isfinite(t) for t in (start,end)) or not 0<=start<end<=score.song.duration_seconds:
        raise ValueError('Invalid audit range')
    manifest=compile_playback_manifest(score)
    resolved=with_default_voicings(score)
    lookup={c.id:c for c in resolved.chords}
    classes={c.id:tuple(sorted({p%12 for p in _selected_voicing_pitches(resolved,c)}))
        if c.symbol.strip().lower() not in NO_CHORD else () for c in resolved.chords}
    rows=[]
    for event in manifest.events:
        stop=event.sustain_end if event.sustain_end is not None else event.end
        a,b=max(start,event.start),min(end,stop)
        if event.track!='guitar' or b<=a:continue
        pcs=tuple(sorted({p%12 for p in event.pitches}));spans=[];support=0;by_pitch=defaultdict(float)
        for chord in resolved.chords:
            lo,hi=max(a,chord.start),min(b,chord.end)
            if hi<=lo:continue
            same=classes[chord.id]==pcs
            if same:support+=hi-lo
            by_pitch[classes[chord.id]]+=hi-lo
            spans.append(dict(start=lo,end=hi,symbol=chord.symbol,chord_id=chord.id,
                pitch_classes=list(classes[chord.id]),same_pitches=same))
        selected=lookup.get(event.source_id)
        rows.append(dict(start=event.start,end=stop,clip_start=a,clip_end=b,
            player_seconds=a-start,selected_symbol=selected.symbol if selected else None,
            selected_chord_id=event.source_id,pitch_classes=list(pcs),spans=spans,
            support_seconds=support,support_fraction=support/(b-a),
            other_score_harmony_seconds=sum(s['end']-s['start'] for s in spans if not s['same_pitches']),
            uncovered_seconds=max(0,b-a-sum(s['end']-s['start'] for s in spans)),
            majority_other_score_harmony=any(k!=pcs and v>(b-a)/2 for k,v in by_pitch.items())))
    return dict(policy='sustained-score-harmony-v1',range=[start,end],rows=rows,
        manifest_revision=manifest.revision,events=len(rows),
        majority_other_events=sum(r['majority_other_score_harmony'] for r in rows),
        other_score_harmony_seconds=sum(r['other_score_harmony_seconds'] for r in rows),
        musical_accuracy_evaluated=False,
        limitation='Pitch-class equality ignores bass/register. Score labels are not ground truth; disagreement is not an instruction to replace a chord or add an attack.')
