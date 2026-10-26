"""One reviewable correction for the user's reported Bar 6→7 late entry.

Not a threshold sweep or a new automatic policy. Preserve the parent revision.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.revisions import RevisionStore
from app.exporters.midi import compile_playback_manifest,export_midi

ROOT=Path(__file__).resolve().parents[2]
PARENT='bc41b274-69d4-430f-8dda-52bd0759119d'
OUT=ROOT/'output/evaluation/reported-bar7-entry-2026-10-26'


def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    write('protocol.json',dict(parent_revision=PARENT,reported_transition='Bar 6 to Bar 7',
        feedback='No obvious overall ensemble displacement under a lenient judgment given existing fragmented melody; local chord change feels late',
        action='One explicit candidate: move only the shared Am/Em edge to existing Bar 7 downbeat; retain labels, grid and stroke times. No global snap or reanalysis.',
        scope='User located the transition, not an exact timestamp or confirmed correction. Human acceptance still required.'))
    store=RevisionStore(ROOT/'output/work/revisions');score=store.load(PARENT);before=score.model_dump_json()
    beat=next(b for b in score.beats if b.measure==7 and b.beat==1)
    next_beat=next(b for b in score.beats if b.time>beat.time)
    period=next_beat.time-beat.time
    matches=[(i,c) for i,c in enumerate(score.chords) if 0<c.start-beat.time<=min(.05,period/8)]
    assert len(matches)==1
    i,right=matches[0];left=score.chords[i-1]
    assert left.symbol=='Am' and right.symbol=='Em' and left.end==right.start
    assert not left.edited and not right.edited
    assert min(left.end-left.start,right.end-right.start)>=period
    a=compile_playback_manifest(score)
    old_first=min(e.start for e in a.events if e.track=='guitar' and e.source_id==right.id)
    assert old_first-right.start>=period/2
    assert any(e.track=='guitar' and e.source_id==left.id and e.start==beat.time for e in a.events)
    candidate=score.model_copy(deep=True)
    candidate.chords[i-1].end=beat.time;candidate.chords[i].start=beat.time
    # Protect this explicitly prepared edit from subsequent automatic candidates.
    candidate.chords[i-1].edited=True;candidate.chords[i].edited=True
    candidate.song.title='小手拉大手 · Bar 7 換和弦入口候選'
    candidate.provenance.parameters['local_entry_parent_revision']=PARENT
    candidate.provenance.parameters['local_entry_candidate']=json.dumps(dict(left=left.id,right=right.id,detected=right.start,candidate=beat.time))
    candidate.analysis.warnings.append('Local Bar 7 entry candidate: Am/Em boundary moved to the existing downbeat; pending listening acceptance. Other boundaries and saved G are unchanged.')
    b=compile_playback_manifest(candidate)
    ga=[e for e in a.events if e.track=='guitar'];gb=[e for e in b.events if e.track=='guitar']
    assert [(e.start,e.stroke) for e in ga]==[(e.start,e.stroke) for e in gb]
    changed=[(old,new) for old,new in zip(ga,gb) if old.pitches!=new.pitches]
    assert len(changed)==1 and changed[0][1].start==beat.time
    assert [e for e in a.events if e.track!='guitar']==[e for e in b.events if e.track!='guitar']
    assert candidate.melody==score.melody and candidate.beats==score.beats
    for index,(old,new) in enumerate(zip(score.chords,candidate.chords)):
        expected=old.model_copy(deep=True)
        if index==i-1:expected.end=beat.time;expected.edited=True
        if index==i:expected.start=beat.time;expected.edited=True
        assert expected==new
    revision=store.save(candidate)
    assert store.load(PARENT).model_dump_json()==before
    assert store.load(revision)==candidate
    for label,m in [('A',a),('B',b)]:
        write(label+'-manifest.json',m.model_dump(mode='json'))
    write('score.json',candidate.model_dump(mode='json'));(OUT/'candidate.mid').write_bytes(export_midi(candidate))
    write('report.json',dict(parent_revision=PARENT,candidate_revision=revision,bar=7,
        downbeat=beat.time,detected_boundary=right.start,detector_lateness_ms=(right.start-beat.time)*1000,
        previous_first_attack=old_first,candidate_first_attack=beat.time,
        eliminated_wait_seconds=old_first-beat.time,stroke_count=len(ga),changed_pitch_assignments=1,
        melody_and_beats_unchanged=True,other_chord_boundaries_unchanged=True,parent_unchanged=True,
        first_attack_original_file=score.song.source_start_seconds+old_first,
        first_attack_candidate_original_file=score.song.source_start_seconds+beat.time,
        url=f'http://localhost:5173/?revision={revision}'))
    print((OUT/'report.json').read_text())


if __name__=='__main__':main()
