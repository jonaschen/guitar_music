"""Bounded existing-source engineering regression; no new source or quality claim."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.accompaniment_candidate import analyze_existing_stem
from app.exporters.midi import compile_playback_manifest, export_midi

root=Path(__file__).resolve().parents[2]
out=root/'output/evaluation/accompaniment-regression-2026-10-26'
out.mkdir(parents=True,exist_ok=False)
cases=[('third','f303ec8a86834633b060920fa85430af',20.,40.),
       ('saved','3ba648f12cb74dd59a45c1b2d4bc83ab',49.957732426303856,64.4237641723356)]
(out/'protocol.json').write_text(json.dumps(dict(cases=cases,rule='Fixed prior listening windows. Same stem analyzer defaults. No tuning, no database writes, no separation. Structural checks only.'),indent=2))
reports=[]
for name,job,start,end in cases:
    began=time.monotonic()
    with sqlite3.connect(f'file:{root}/output/work/jobs/jobs.sqlite3?mode=ro',uri=True) as db:
        score=SongScore.model_validate(json.loads(db.execute('select payload from jobs where id=?',(job,)).fetchone()[0])['score'])
    cropped=score.model_copy(deep=True)
    cropped.song.duration_seconds=end-start
    cropped.song.source_start_seconds+=start
    cropped.beats=[b.model_copy(update={'time':b.time-start}) for b in score.beats if start<=b.time<end]
    for field in ['melody','chords']:
        setattr(cropped,field,[n.model_copy(update={'start':max(start,n.start)-start,'end':min(end,n.end)-start}) for n in getattr(score,field) if n.start<end and n.end>start])
    before=cropped.model_dump_json()
    with tempfile.TemporaryDirectory(prefix='guitarscribe-stem-regression-') as temp:
        directory=Path(temp)
        for file in ['analysis-source.wav','accompaniment-stem.wav']:
            with sf.SoundFile(root/'output/work/jobs'/job/file) as source:
                sr=source.samplerate; source.seek(round(start*sr)); samples=source.read(round((end-start)*sr),always_2d=True)
            assert len(samples)==round((end-start)*sr)
            sf.write(directory/file,samples,sr,subtype='FLOAT')
        candidate=analyze_existing_stem(cropped,directory,job)
    assert cropped.model_dump_json()==before
    assert candidate.melody==cropped.melody and candidate.beats==cropped.beats
    assert all(0<=c.start<c.end<=end-start for c in candidate.chords)
    assert all(a.end<=b.start for a,b in zip(candidate.chords,candidate.chords[1:]))
    (out/f'{name}-candidate.json').write_text(candidate.model_dump_json(indent=2))
    (out/f'{name}.mid').write_bytes(export_midi(candidate))
    (out/f'{name}-manifest.json').write_text(compile_playback_manifest(candidate).model_dump_json(indent=2))
    reports.append(dict(id=name,job=job,window=[start,end],chords=len(candidate.chords),
                        melody_and_beats_unchanged=True,source_unchanged=True,
                        seconds=time.monotonic()-began,quality='Not evaluated by ear',
                        provenance=candidate.provenance.parameters))
(out/'report.json').write_text(json.dumps(reports,indent=2))
print(json.dumps([{k:v for k,v in r.items() if k!='provenance'} for r in reports],indent=2))
