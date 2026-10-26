"""Different-song regression using an already accepted 29s frozen packet.

No audio analysis, chord selection, beat inference or score edits.
"""
import hashlib
import io
import json
from pathlib import Path
import sys

import mido

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.chord_entry_performance import build_entry_performance
from app.exporters.midi import export_manifest_midi

ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/'output/evaluation/automatic-accompaniment-2026-10-24'
AUDIO=ROOT/'frontend/public/listening/automatic-accompaniment-2026-10-25'
OUT=ROOT/'output/evaluation/saved-song-entry-2026-10-26'


def read(path):return json.loads(path.read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    accepted=read(ROOT/'docs/evaluation/accepted-accompaniment-2026-10-25.json')
    write('protocol.json',dict(song='小手拉大手',duration=accepted['duration_seconds'],
        analysis_start=accepted['analysis_offset'],original_source_start=18+accepted['analysis_offset'],
        basis='Previously preferred automatic accompaniment packet; not the older Librosa/chromagram job',
        A='Frozen previously accepted candidate.wav, unchanged',
        B='Same score/beat grid/voicings/rhythm and product voice; opt-in continuous entry performance',
        fixed='No reanalysis, offsets, parameters, score edits or per-variant gain normalization',
        decision='If B is worse, retain A and investigate arrangement; do not tune this song. If comparable/better, retain bounded evidence for this second song, not whole-song accuracy.'))
    score_bytes=(INPUT/'score.json').read_bytes();manifest_bytes=(INPUT/'manifest.json').read_bytes()
    source=(AUDIO/'source.wav').read_bytes();reference=(AUDIO/'candidate.wav').read_bytes()
    for data,key in [(score_bytes,'score_sha256'),(manifest_bytes,'manifest_sha256'),(source,'source_sha256'),(reference,'candidate_audio_sha256')]:
        assert sha(data)==accepted[key],key
    score=SongScore.model_validate_json(score_bytes);before=score.model_dump_json()
    original,candidate,changes,skipped=build_entry_performance(score,'continuous')
    assert score.model_dump_json()==before
    assert original.model_dump(mode='json')['events']==json.loads(manifest_bytes)['events']
    assert [e for e in original.events if e.track!='guitar']==[e for e in candidate.events if e.track!='guitar']
    for label,manifest in [('A',original),('B',candidate)]:
        write(label+'-manifest.json',manifest.model_dump(mode='json'))
        midi=export_manifest_midi(manifest);(OUT/(label+'.mid')).write_bytes(midi)
        actual=[];time=0
        for msg in mido.MidiFile(file=io.BytesIO(midi)):
            time+=msg.time
            if msg.type in {'note_on','note_off'}:actual.append((msg.channel,msg.note,msg.type,time))
        expected=[]
        for event in manifest.events:
            if event.track=='metronome':continue
            channel=int(event.track=='guitar')
            for i,pitch in enumerate(event.pitches):
                offset=event.pitch_offsets[i] if event.pitch_offsets else 0
                expected.extend([(channel,pitch,'note_on',event.start+offset),(channel,pitch,'note_off',event.end)])
        assert len(actual)==len(expected)
        errors=[]
        for a,b in zip(sorted(actual),sorted(expected)):
            assert a[:3]==b[:3]
            errors.append(abs(a[3]-b[3]))
        assert max(errors,default=0)<.002
        write(label+'-midi-check.json',dict(note_events=len(actual),max_error_seconds=max(errors,default=0)))
    (OUT/'source.wav').write_bytes(source);(OUT/'A-reference.wav').write_bytes(reference)
    (OUT/'score.json').write_bytes(score_bytes)
    write('report.json',dict(window=[0,score.song.duration_seconds],source_sha256=sha(source),reference_A_sha256=sha(reference),
        frozen_guitar_gain=1.0,score_sha256=sha(score_bytes),changes=changes,skipped=skipped,
        original_event_parity=True,score_unchanged=True,non_guitar_events_unchanged=True,
        prior_reference='automatic-accompaniment-2026-10-25/candidate.wav'))
    print(json.dumps(dict(duration=score.song.duration_seconds,changed=len(changes),skipped=skipped,source_sha256=sha(source)),ensure_ascii=False))


if __name__=='__main__':main()
