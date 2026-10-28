"""Full source inventory: meter-qualified score or explicitly unmetered harmony.

Consumes the submitted full-song jobs. Never repairs failed beat observations.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request,urlopen

from app.analyzers.preprocessor import FFmpegPreprocessor
from app.analyzers.chords.chordino import ChordinoChordAnalyzer
from app.models.audio import AudioAsset,SourceType
from app.models.score import SongScore
from app.services.chord_grid_candidate import build_chord_grid_candidate
from app.services.chord_inspection import chord_inspection_events
from app.exporters.midi import compile_playback_manifest


def api(path,data=None):
    request=Request('http://127.0.0.1:8000'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=60) as r:return json.load(r)


async def run(directory):
    titles={r['video']:r['title'] for r in json.loads((directory/'titles.json').read_text())}
    report_path=directory/'overview.json'
    results=json.loads(report_path.read_text()) if report_path.exists() else []
    while len(results)<7:
        rows=json.loads((directory/'catalog.json').read_text())
        progress=False
        for row in rows:
            if any(r['video']==row['video'] for r in results) or row.get('status') not in ('completed','failed'):
                continue
            source=Path(row['input']);before=hashlib.sha256(source.read_bytes()).hexdigest()
            assert before==row['sha256']
            job=api('/api/v1/jobs/'+row['job'])
            folder=directory/row['video'];folder.mkdir(exist_ok=True)
            print('PREPARING',row['video'],job['status'],flush=True)
            if job['status']=='completed':
                score=SongScore.model_validate(job['score']);duration=score.song.duration_seconds
                score,grid=build_chord_grid_candidate(score)
                score.song.title=titles[row['video']];score.song.source_url=row['url'];score.song.source_type='youtube'
                score.provenance.parameters.update(analysis_source_job_id=row['job'],review_catalog='full-2026-10-28')
                manifest=compile_playback_manifest(score)
                events=[e for e in manifest.events if e.track=='guitar']
                chords=score.chords;unsupported=[];kind='rhythmic'
                revision=api('/revisions',{'score':score.model_dump(mode='json')})['revision_id']
                (folder/'score.json').write_text(score.model_dump_json(indent=2))
                (folder/'grid.json').write_text(json.dumps(grid,indent=2))
                key=score.analysis.key;mode=score.analysis.mode
            else:
                audio=await FFmpegPreprocessor().normalize(AudioAsset(path=source,source_type=SourceType.LOCAL))
                try:
                    duration=audio.duration_seconds
                    analysis=await ChordinoChordAnalyzer().analyze(audio,None)
                    (folder/'chord-analysis.json').write_text(analysis.model_dump_json(indent=2))
                    chords=analysis.chords;key=analysis.key;mode=analysis.mode
                    events,unsupported=chord_inspection_events(chords,duration)
                finally:
                    if audio.temporary_directory:shutil.rmtree(audio.temporary_directory)
                kind='unmetered';revision=None
                rejection=source.parents[1]/row['job']/'timing-rejection.json'
                assert rejection.exists()
                shutil.copyfile(rejection,folder/'timing-rejection.json')
            assert all(c.end<=duration for c in chords)
            assert api('/api/v1/jobs/'+row['job'])==job
            result=dict(**row,title=titles[row['video']],duration=duration,kind=kind,revision=revision,
                key_estimate=key,mode_estimate=mode,chords=[c.model_dump(mode='json') for c in chords],
                unsupported_chord_ids=unsupported,human_verdict='whole_song_unreviewed',
                events=[e.model_dump(mode='json') for e in events],engineer_note='No melody. Failed meter remains failed. Unmetered mode plays once per detected chord, without repeated strumming or a tempo assumption.')
            (folder/'inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            results.append(result);report_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
            print('READY',row['video'],kind,len(chords),'chords',len(events),'events',flush=True)
            progress=True
        if not progress:await asyncio.sleep(10)
    print('ALL FULL SOURCES PREPARED',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    asyncio.run(run(args.directory))
