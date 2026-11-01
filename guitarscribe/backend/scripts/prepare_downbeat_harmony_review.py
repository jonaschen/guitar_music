"""Audit frozen bar strums and prepare one scoped, timing-only harmony comparison.

Usage: python prepare_downbeat_harmony_review.py ACCEPTED_REVIEW_DIR OUTPUT_DIR
Uses existing nearest-eighth-v1 rules; no model inference or database writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest,export_midi
from app.services.chord_grid_candidate import build_chord_grid_candidate
from app.services.downbeat_harmony_audit import audit_downbeat_harmony


def prepare(prior,output):
    frozen=json.loads((prior/'packet.json').read_text())
    score=SongScore.model_validate_json((prior/'score.json').read_text())
    assert hashlib.sha256(score.model_dump_json().encode()).hexdigest()==frozen['score_sha256']
    original=compile_playback_manifest(score)
    assert hashlib.sha256(original.model_dump_json().encode()).hexdigest()==frozen['manifest_sha256']
    start,end=frozen['start'],frozen['end']
    candidate,timing=build_chord_grid_candidate(score,scope=(start,end))
    alternate=compile_playback_manifest(candidate)
    assert score.beats==candidate.beats and score.rhythm==candidate.rhythm and score.melody==candidate.melody
    assert len(score.chords)==len(candidate.chords)
    for a,b in zip(score.chords,candidate.chords):
        assert a.model_dump(exclude={'start','end'})==b.model_dump(exclude={'start','end'})
        for before,after in [(a.start,b.start),(a.end,b.end)]:
            if before!=after: assert start<before<end and start<=after<=end
    a_events=[e for e in original.events if e.track=='guitar']
    b_events=[e for e in alternate.events if e.track=='guitar']
    assert [(e.start,e.end,e.sustain_end,e.stroke) for e in a_events]==[(e.start,e.end,e.sustain_end,e.stroke) for e in b_events]
    assert [e for e in original.events if e.track!='guitar']==[e for e in alternate.events if e.track!='guitar']
    assert [e for e in original.events if not start<=e.start<end]==[e for e in alternate.events if not start<=e.start<end]
    before=audit_downbeat_harmony(score,start,end);after=audit_downbeat_harmony(candidate,start,end)
    changed=[dict(time=a['time'],player_seconds=a['time']-start,original=a['symbol'],candidate=b['symbol'],
                  boundary=a['nearby_late_boundary']) for a,b in zip(before['rows'],after['rows']) if a['pitches']!=b['pitches']]
    assert changed,'Do not ask for a comparison with no audible event differences'
    output.mkdir(parents=True,exist_ok=False)
    (output/'a-score.json').write_text(score.model_dump_json(indent=2))
    (output/'a-manifest.json').write_text(original.model_dump_json(indent=2))
    for name,value in [('score.json',candidate),('manifest.json',alternate)]:
        (output/name).write_text(value.model_dump_json(indent=2))
    (output/'candidate.mid').write_bytes(export_midi(candidate))
    shutil.copy2(prior/'source.wav',output/'source.wav')
    packet={**frozen,'title':'固定拍子，只比較換和弦時間',
            'score_sha256':hashlib.sha256(candidate.model_dump_json().encode()).hexdigest(),
            'manifest_sha256':hashlib.sha256(alternate.model_dump_json().encode()).hexdigest(),
            'control_manifest_sha256':frozen['manifest_sha256'],
            'timing_accepted_range':[start,end], 'musical_verdict':'harmony_unconfirmed',
            'harmony_unchanged':False,'harmony_labels_unchanged':True,'beat_grid_unchanged':True,
            'changes':changed}
    (output/'packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
    report=dict(policy='scoped-nearest-eighth-v1',scope=[start,end],timing=timing,before=before,after=after,
                changed_strums=changed,chord_count=len(score.chords),
                clip_strokes=len(before['rows']),outside_events_unchanged=True,
                protocol='One fixed A/B, timing boundaries only. Reuse prior A audio; freeze beats, rhythm, labels, voicings and gain. No parameter sweep or global adoption.',
                limitation='A different selected chord is not proof of improved harmony. Short unsounded segments remain in the score.')
    (output/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'changed_strums':changed,'unstruck_before':len(before['unstruck_segments']),
                      'unstruck_after':len(after['unstruck_segments']),'chords':len(score.chords)},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('prior',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();prepare(a.prior,a.output)
