"""Import already-reviewed chord analysis as NEW editable seconds-based workspaces.

No models or audio rendering. Fails if source/event hashes differ; keeps old jobs intact.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from app.models.analysis import ChordAnalysis, RhythmSuggestion
from app.models.jobs import AnalysisJob, JobStatus
from app.models.score import SongScore, SongInfo, AnalysisSummary, KeyContext, KeySignature, Provenance
from app.services.jobs import JobStore
from app.services.revisions import RevisionStore
from app.services.playable_chords import with_default_voicings
from app.exporters.midi import compile_playback_manifest


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(catalog, work):
    jobs=JobStore(work/'jobs');revisions=RevisionStore(work/'revisions')
    rendered={r['video']:r for r in json.loads((catalog/'render-report.json').read_text())}
    report_path=catalog/'workspaces.json'
    report=json.loads(report_path.read_text()) if report_path.exists() else []
    for row in json.loads((catalog/'overview.json').read_text()):
        source=Path(row['input']);assert digest(source)==row['sha256']
        folder=catalog/row['video']
        analysis_path=folder/'chord-analysis.json'
        with sqlite3.connect(jobs.database_path) as connection:
            old=connection.execute('SELECT payload FROM jobs WHERE id=?',(row['job'],)).fetchone()[0]
        mix_hash=rendered[row['video']]['audio']['audio']['mix']['sha256']
        existing=next((r for r in report if r['video']==row['video']),None)
        if existing:
            assert existing['source_sha256']==row['sha256'] and existing['analysis_sha256']==digest(analysis_path)
            assert existing['mix_sha256']==mix_hash
            score=revisions.load(existing['revision'])
            assert [e.model_dump(mode='json') for e in compile_playback_manifest(score).events]==row['events']
            assert digest(jobs.job_dir(existing['job'])/'input.wav')==row['sha256']
            continue
        analysis=ChordAnalysis.model_validate_json(analysis_path.read_text())
        job_id=uuid4().hex;signature=KeySignature(key=analysis.key,mode=analysis.mode)
        score=with_default_voicings(SongScore(
            song=SongInfo(title=row['title'],source_type='youtube',source_url=row['url'],duration_seconds=row['duration']),
            analysis=AnalysisSummary(timing_status='unmetered',key=analysis.key,mode=analysis.mode,bpm=0,time_signature='',confidence=analysis.confidence,
                                     warnings=['拍格尚未確認；保留已試聽的和弦時間，每次換和弦彈一下。',*analysis.warnings]),
            key_context=KeyContext(source=signature,target=signature,shape=signature,sounding=signature),
            chords=analysis.chords,
            rhythm=RhythmSuggestion(pattern_id='unmetered-chord-inspection-v1',display=[],confidence=0,label='每次換和弦彈一下'),
            provenance=Provenance(beat_engine='beat-this',chord_engine=analysis.engine,chord_engine_version=analysis.engine_version,
                melody_engine='disabled',tempo_map_version='unmetered-seconds-v1',parameters={**analysis.parameters,
                'analysis_source_job_id':job_id,'original_source_job_id':row['source_job'],'rejected_timing_job_id':row['job'],
                'source_sha256':row['sha256'],'cached_analysis_sha256':digest(analysis_path),'melody_mode':'off',
                'import_policy':'reviewed-catalog-unmetered-v1','chord_complexity':'full'})))
        events=[e.model_dump(mode='json') for e in compile_playback_manifest(score).events]
        assert events==row['events'],f"Accepted playback changed: {row['video']}"
        destination=jobs.job_dir(job_id);destination.mkdir()
        shutil.copyfile(source,destination/'input.wav')
        for name in ('chord-analysis.json','timing-rejection.json'):shutil.copyfile(folder/name,destination/name)
        assert digest(destination/'input.wav')==row['sha256']
        now=datetime.now(timezone.utc).isoformat()
        jobs.save(AnalysisJob(id=job_id,status=JobStatus.COMPLETED,progress=100,message='已載入既有和弦分析；拍格尚未確認',
            melody_mode='off',chord_complexity='full',source_type='youtube',source_url=row['url'],created_at=now,updated_at=now,score=score,
            artifacts=['chord-analysis.json','timing-rejection.json']))
        revision=revisions.save(score)
        assert revisions.load(revision)==score
        with sqlite3.connect(jobs.database_path) as connection:
            assert connection.execute('SELECT payload FROM jobs WHERE id=?',(row['job'],)).fetchone()[0]==old
        report.append(dict(video=row['video'],title=row['title'],source_sha256=row['sha256'],analysis_sha256=digest(analysis_path),
            inspection_mode='unmetered',mix_sha256=mix_hash,job=job_id,revision=revision,event_count=len(events),accepted_event_parity=True,original_failed_job_unchanged=True))
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(row['video'],revision,len(events),'events unchanged',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('catalog',type=Path);parser.add_argument('work',type=Path)
    args=parser.parse_args();run(args.catalog,args.work)
