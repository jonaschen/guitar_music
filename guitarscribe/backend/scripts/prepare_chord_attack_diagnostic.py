"""Freeze a boundary-only diagnostic on accepted chords; no production edits."""
import hashlib
import json
from pathlib import Path
import sys

import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/evaluation/chord-attack-diagnostic-2026-10-26-verified'


def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source=ROOT/'output/evaluation/accompaniment-candidate-integration-2026-10-26/candidate-score.json'
    score=SongScore.model_validate_json(source.read_bytes())
    start,end=10.,40.
    write(OUT/'protocol.json',dict(window=[start,end],score_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        method='Within the accepted 10–40s window only, move shared internal chord boundaries to nearest existing beat (ties choose earlier). Preserve first start, final end, labels/order, voicings, rhythm, beats, melody. Reject collapsed or reordered spans. No production integration.',
        mapping={'A':'original detected boundaries','B':'nearest accepted beat boundaries'},
        warning='Timing ablation, not proof that every change should occur on a quarter-note beat.'))
    candidate=score.model_copy(deep=True)
    beat_times=sorted(b.time for b in score.beats)
    changes=[]
    for i in range(1,len(candidate.chords)):
        old=score.chords[i].start
        if not start<old<end:
            continue
        if abs(score.chords[i-1].end-old)>1e-8:
            continue  # Never fill a real no-chord gap.
        snapped=min(beat_times,key=lambda t:(abs(t-old),t))
        candidate.chords[i-1].end=snapped;candidate.chords[i].start=snapped
        changes.append(dict(original=old,aligned=snapped,shift=snapped-old,symbol=candidate.chords[i].symbol))
    assert all(c.start<c.end for c in candidate.chords)
    assert all(a.end<=b.start+1e-8 for a,b in zip(candidate.chords,candidate.chords[1:]))
    for a,b in zip(score.chords,candidate.chords):
        assert a.model_dump(exclude={'start','end'})==b.model_dump(exclude={'start','end'})
    assert score.model_dump(exclude={'chords'})==candidate.model_dump(exclude={'chords'})
    manifests=[compile_playback_manifest(s) for s in [score,candidate]]
    guitars=[[e for e in m.events if e.track=='guitar'] for m in manifests]
    assert [(e.start,e.stroke) for e in guitars[0]]==[(e.start,e.stroke) for e in guitars[1]]
    assert [e for e in manifests[0].events if e.track!='guitar']==[e for e in manifests[1].events if e.track!='guitar']
    expected=[]
    for beat,nxt in zip(score.beats,score.beats[1:]):
        for sub in (0,1):
            time=beat.time+(nxt.time-beat.time)*sub/2
            stroke=score.rhythm.display[2*(beat.beat-1)+sub]
            if start<=time<end and stroke:
                expected.append((round(time,8),stroke))
    for events in guitars:
        assert [(round(e.start,8),e.stroke) for e in events if start<=e.start<end]==expected
    delays=[]
    for a,b in zip(score.chords,candidate.chords):
        if not start<a.start<end:continue
        strokes=[[e for e in g if e.source_id==a.id] for g in guitars]
        if any(not events for events in strokes):raise ValueError('A chord receives no scheduled stroke')
        delays.append(dict(symbol=a.symbol,original_change=a.start-start,aligned_change=b.start-start,
            original_first_attack=strokes[0][0].start-start,aligned_first_attack=strokes[1][0].start-start,
            original_delay=strokes[0][0].start-a.start,aligned_delay=strokes[1][0].start-b.start))
    for label,s,m in zip(['A','B'],[score,candidate],manifests):
        (OUT/f'{label}-score.json').write_text(s.model_dump_json(indent=2))
        (OUT/f'{label}-manifest.json').write_text(m.model_dump_json(indent=2))
    audio=ROOT/'output/work/jobs/db79e1145ea046088b8aa5ef421d0e3f/analysis-source.wav'
    with sf.SoundFile(audio) as sound:
        sr=sound.samplerate;sound.seek(round(start*sr));samples=sound.read(round((end-start)*sr),always_2d=True)
    assert len(samples)==round((end-start)*sr)
    sf.write(OUT/'source.wav',samples,sr,subtype='PCM_16')
    report=dict(window=[start,end],changes=changes,attack_delays=delays,stroke_count=len(guitars[0]),
                stroke_times_identical=True,non_guitar_events_identical=True,labels_and_voicings_identical=True,
                source_sha256=hashlib.sha256((OUT/'source.wav').read_bytes()).hexdigest(),
                status='Engineering checks passed; audible improvement not established')
    write(OUT/'report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
