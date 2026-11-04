"""Frozen three-item review; source hashes required, no analysis/job writes.

Usage: python prepare_timing_batch_review.py GUITARSCRIBE_ROOT OUTPUT_DIR
Follow with render-performance-review.mjs on OUTPUT_DIR/strumming-input.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.models.analysis import RhythmSuggestion
from app.services.timing_checkpoint_candidate import build_checkpoint_candidate
from app.exporters.midi import compile_playback_manifest, export_midi
from app.services.downbeat_rhythm import BEAT_PATTERN_ID

CASES=[('後來','10de4472b18247d99326c42f41d04b0d',220,260),
       ('你的樣子','cd754fa6b231407290c076c2351e917c',15,55)]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def prepare(root,output):
    root=root.resolve();output.mkdir(parents=True,exist_ok=False)
    main=root/'output/evaluation/timing-main-model-2026-11-04'
    continuity=root/'output/evaluation/timing-continuity-2026-11-04'
    rows=[]
    for number,(title,job,start,end) in enumerate(CASES,1):
        report=json.loads((continuity/job/'report.json').read_text());case=report['case']
        original=json.loads((main/job/'report.json').read_text())['baseline']['dbn']
        selected=report['decoders'][report['selected_decoder']]
        source=Path(case['source']);assert sha(source)==case['source_sha256']
        connection=sqlite3.connect(f"file:{case['work']}/jobs/jobs.sqlite3?mode=ro",uri=True)
        payload=connection.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0];connection.close()
        assert hashlib.sha256(payload.encode()).hexdigest()==case['payload_sha256']
        score=SongScore.model_validate(json.loads(payload)['score'])
        candidate=build_checkpoint_candidate(score,report) # Recomputes full-song gates.
        folder=output/str(number);folder.mkdir()
        (folder/'candidate-score.json').write_text(candidate.model_dump_json(indent=2))
        (folder/'candidate.mid').write_bytes(export_midi(candidate))
        subprocess.run(['ffmpeg','-v','error','-i',str(source),'-af',f'atrim=start={start}:end={end},asetpts=PTS-STARTPTS',
            '-ar','22050','-ac','1','-c:a','pcm_f32le',str(folder/'raw.wav')],check=True)
        audio,rate=sf.read(folder/'raw.wav');assert rate==22050 and len(audio)==(end-start)*rate
        waves={'source':audio*.45};schedules={}
        for variant,timing in [('a',original),('b',selected)]:
            clicks=np.zeros(len(audio));schedule=[]
            for time in timing['beats']:
                if not start<=time<end:continue
                down=any(abs(time-d)<1e-6 for d in timing['downbeats'])
                t=np.arange(round(.065*rate))/rate
                pulse=(.30 if down else .18)*np.sin(2*np.pi*(1500 if down else 1000)*t)*np.exp(-t/.015)
                at=round((time-start)*rate);n=min(len(pulse),len(audio)-at)
                clicks[at:at+n]+=pulse[:n];schedule.append(dict(time=time-start,downbeat=down))
            waves[variant+'-mix']=waves['source']+clicks;schedules[variant]=schedule
        gain=min(1,.95/max(float(np.max(np.abs(w))) for w in waves.values()))
        hashes={}
        for name,wave in waves.items():
            assert np.isfinite(wave).all()
            file=output/f'{number}-{name}.wav';sf.write(file,wave*gain,rate,subtype='PCM_16');hashes[file.name]=sha(file)
        (folder/'raw.wav').unlink()
        row=dict(number=number,title=title,kind='click',start=start,end=end,job=job,
            source_url=case['source_url'],source_sha256=case['source_sha256'],gain=gain,
            files=hashes,schedules=schedules,decoder=report['selected_decoder'],
            score_sha256=sha(folder/'candidate-score.json'),musical_verdict='unconfirmed')
        rows.append(row)
    # Same frozen accepted grid and same harmony B; only change the rhythm schedule.
    frozen=root/'output/evaluation/downbeat-harmony-2026-11-01'
    prior=json.loads((frozen/'packet.json').read_text())
    base=SongScore.model_validate_json((frozen/'score.json').read_text())
    assert hashlib.sha256(base.model_dump_json().encode()).hexdigest()==prior['score_sha256']
    assert sha(frozen/'source.wav')=='9fdc385a7226c51d3e8a681b2c3980a4425a4c38589d7bd331ad172cfcbff86b'
    assert sha(frozen/'source.wav')==sha(root/'output/evaluation/downbeat-review-2026-11-01/source.wav')
    source_case=next(c for c in json.loads((main/'plan.json').read_text())['cases'] if c['job']==prior['job'])
    assert sha(Path(source_case['source']))==prior['source_sha256']
    original_manifest=compile_playback_manifest(base)
    saved=json.loads((frozen/'manifest.json').read_text())
    assert original_manifest.model_dump(mode='json')==saved
    candidate=base.model_copy(deep=True)
    meter=int(base.analysis.time_signature[0])
    candidate.rhythm=RhythmSuggestion(pattern_id=BEAT_PATTERN_ID,label='每拍一下',subdivision=4,
        display=['D']*meter,accents=[1]+[.7]*(meter-1))
    assert candidate.chords==base.chords and candidate.beats==base.beats and candidate.guitar==base.guitar
    inputs=output/'strumming-input';folder=inputs/'3';folder.mkdir(parents=True)
    shutil.copyfile(frozen/'source.wav',folder/'source.wav')
    manifests={}
    for variant,score in [('a',base),('b',candidate)]:
        manifest=compile_playback_manifest(score);manifests[variant]=manifest
        (folder/f'{variant}-score.json').write_text(score.model_dump_json(indent=2))
        (folder/f'{variant}-manifest.json').write_text(manifest.model_dump_json(indent=2))
        (folder/f'{variant}.mid').write_bytes(export_midi(score))
    row=dict(number=3,title='下一個天亮',kind='strum',start=24,end=64,
        job=prior['job'],source_sha256=prior['source_sha256'],excerpt_sha256=sha(frozen/'source.wav'),musical_verdict='unconfirmed',
        events={v:[dict(start=e.start-24,end=e.end-24,chord=e.source_id) for e in m.events if e.track=='guitar' and 24<=e.start<64] for v,m in manifests.items()})
    # All new attacks must come from the same accepted observed grid.
    assert all(any(abs(e['start']+24-b.time)<1e-9 for b in base.beats) for e in row['events']['b'])
    for key in ('a','b'):
        row[key+'_manifest_sha256']=sha(folder/f'{key}-manifest.json')
    dump(inputs/'packet.json',[row]);rows.append(row)
    dump(output/'packet.json',rows)
    shutil.copyfile(root/'frontend/scripts/timing-batch-review.html',output/'index.html')
    print(json.dumps([dict(number=r['number'],title=r['title'],start=r['start'],end=r['end']) for r in rows],ensure_ascii=False))


if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]))
