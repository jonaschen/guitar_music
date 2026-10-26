"""Local three-source structural regression and one frozen cross-source review."""
import hashlib
import io
import json
import sys
from pathlib import Path

import mido

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.chord_entry_performance import build_entry_performance
from app.exporters.midi import export_manifest_midi

ROOT=Path(__file__).resolve().parents[2]
EVAL=ROOT/'output/evaluation'
OUT=EVAL/'entry-performance-regression-2026-10-26'


def read(path):return json.loads(path.read_text())
def write(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    write('protocol.json',dict(policy='chord-entry-performance-v1',
        restriction='No new inference, threshold fitting, beat/score edits or default change',
        listening='Previously preferred live-source B vs explicit entry performance, fixed original 10–40 seconds; judge regression, not complete chord accuracy',
        limits='Structural checks on three existing sources are not human quality acceptance'))
    cases=[('third',EVAL/'confirmed-third-timing-2026-10-26/B-score.json'),
           ('live',EVAL/'chord-attack-diagnostic-2026-10-26-verified/B-score.json'),
           ('saved',EVAL/'accompaniment-regression-2026-10-26/saved-candidate.json')]
    results=[]
    for name,path in cases:
        score=SongScore.model_validate_json(path.read_bytes());before=score.model_dump_json()
        original,candidate,changes,skipped=build_entry_performance(score,'continuous')
        assert score.model_dump_json()==before
        assert [e for e in original.events if e.track!='guitar']==[e for e in candidate.events if e.track!='guitar']
        midi=export_manifest_midi(candidate);(OUT/(name+'.mid')).write_bytes(midi)
        actual=[];time=0
        for msg in mido.MidiFile(file=io.BytesIO(midi)):
            time+=msg.time
            if msg.type in {'note_on','note_off'}:actual.append((msg.channel,msg.note,msg.type,time))
        expected=[]
        for e in candidate.events:
            if e.track=='metronome':continue
            for i,p in enumerate(e.pitches):
                offset=e.pitch_offsets[i] if e.pitch_offsets else 0
                expected.extend([(int(e.track=='guitar'),p,'note_on',e.start+offset),(int(e.track=='guitar'),p,'note_off',e.end)])
        assert len(expected)==len(actual)
        errors=[]
        for a,b in zip(sorted(actual),sorted(expected)):
            assert a[:3]==b[:3]
            errors.append(abs(a[3]-b[3]))
        assert max(errors,default=0)<.002
        result=dict(source=name,changed=len(changes),skipped=skipped,midi_events=len(actual),max_midi_error_seconds=max(errors,default=0),original_revision=original.revision,candidate_revision=candidate.revision)
        if name=='third':
            previous=read(EVAL/'matched-entry-2026-10-26/B-manifest.json')
            def acoustic(e):return {k:v for k,v in e.items() if k not in {'id','end'}}
            key=lambda e:(e['start'],e['track'])
            assert sorted([acoustic(e.model_dump(mode='json')) for e in candidate.events],key=key)==sorted([acoustic(e) for e in previous['events']],key=key)
            result['preferred_acoustic_events_identical']=True
        if name=='live':
            write('A-manifest.json',original.model_dump(mode='json'));write('B-manifest.json',candidate.model_dump(mode='json'))
            prior=EVAL/'chord-attack-diagnostic-2026-10-26-verified'
            source=(prior/'source.wav').read_bytes();source_sha=hashlib.sha256(source).hexdigest()
            assert source_sha==read(prior/'report.json')['source_sha256']
            (OUT/'source.wav').write_bytes(source)
            reference=(ROOT/'frontend/public/listening/chord-attack-2026-10-26/B.wav').read_bytes()
            reference_sha=hashlib.sha256(reference).hexdigest();render=read(prior/'render-report.json')
            assert reference_sha==render['outputs'][1]['sha256'];(OUT/'A-reference.wav').write_bytes(reference)
            write('report.json',dict(window=[10,40],source_sha256=source_sha,reference_A_sha256=reference_sha,
                frozen_guitar_gain=render['levels']['guitarGain'],changes=changes,skipped=skipped))
        results.append(result)
    write('regression.json',results);print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
