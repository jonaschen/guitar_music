"""Fixed third-source checkpoint: read job artifacts, never alter saved scores."""
import hashlib
import json
from pathlib import Path
import sys
import sqlite3
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.melody_contour import MelodyContour
from app.models.score import SongScore
from app.evaluation.conservative_notes import decode_bounded
from app.exporters.midi import compile_playback_manifest

ROOT=Path(__file__).resolve().parents[2]
JOB='f303ec8a86834633b060920fa85430af'
RANGES=[(20.,40.),(40.,60.)]  # Fixed before inspecting the resulting notes.
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')

def main():
    directory=ROOT/'output/work/jobs'/JOB
    out=ROOT/'output/evaluation/third-source-2026-10-25'
    out.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect(f'file:{ROOT}/output/work/jobs/jobs.sqlite3?mode=ro',uri=True) as db:
        job=json.loads(db.execute('select payload from jobs where id=?',(JOB,)).fetchone()[0])
    assert job['status']=='completed'
    score=SongScore.model_validate(job['score'])
    assert score.provenance.melody_engine=='pyin_vocal'
    assert score.provenance.parameters['vocal_source_separated']
    contour=MelodyContour.model_validate_json((directory/'melody-contour.json').read_bytes())
    assert contour.source_artifact_sha256==sha(directory/'vocal-stem.wav')
    assert contour.source_start==0 and contour.source_end>=60-.001
    notes=decode_bounded(contour)
    candidate=score.model_copy(update={'melody':notes},deep=True)
    manifest=compile_playback_manifest(candidate).model_dump(mode='json')
    events=[e for e in manifest['events'] if e['track']=='melody']
    assert len(events)==len(notes)
    for n,e in zip(notes,events):
        assert abs(n.start-e['start'])<1e-9 and abs(n.end-e['end'])<1e-9
        assert e['pitches']==[n.midi]
    report=dict(job_id=JOB,source_url=job['source_url'],status='awaiting_listening',
        selection='20-40 and 40-60 seconds fixed before note inspection; no output-quality selection',
        decoder_sha256=sha(ROOT/'backend/app/evaluation/conservative_notes.py'),
        source_hashes={n:sha(directory/n) for n in ['input.wav','analysis-source.wav','vocal-stem.wav','melody-contour.json']},
        source_start_seconds=score.song.source_start_seconds,parameters=score.provenance.parameters,
        job_created_at=job["created_at"],job_updated_at=job["updated_at"],
        full_G_notes=len(notes),compiler_parity=True,cases=[])
    for i,(start,end) in enumerate(RANGES,1):
        clipped=[dict(start=max(n.start,start)-start,end=min(n.end,end)-start,midi=n.midi) for n in notes if n.start<end and n.end>start]
        assert clipped
        write(out/f'g-{i}.json',clipped)
        audio_stats={}
        for label,source in [('source','analysis-source.wav'),('vocal','vocal-stem.wav')]:
            with sf.SoundFile(directory/source) as f:
                rate=f.samplerate;f.seek(round(start*rate));audio=f.read(round((end-start)*rate),always_2d=True)
            assert len(audio)==round((end-start)*rate)
            sf.write(out/f'{label}-{i}.wav',audio,rate,subtype='PCM_16')
            audio_stats[label]=dict(sha256=sha(out/f'{label}-{i}.wav'),peak=float(np.max(np.abs(audio))),rms=float(np.sqrt(np.mean(audio**2))))
        report['cases'].append(dict(id=i,start=start,end=end,duration=end-start,notes=len(clipped),under_100ms=sum(n['end']-n['start']<.1 for n in clipped),under_10ms=sum(n['end']-n['start']<.01 for n in clipped),audio=audio_stats))
    write(out/'report.json',report)
    write(out/'G-score.json',candidate.model_dump(mode='json'))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
