"""Publish an independent local workspace excerpt, preserving full saved G.

Uses only frozen accepted audio/score and an existing saved melody revision.
Creates new IDs; never overwrites a job or revision and performs no inference.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.models.jobs import AnalysisJob,JobStatus
from app.services.accepted_excerpt import compose_excerpt
from app.services.jobs import JobStore
from app.services.revisions import RevisionStore
from app.exporters.midi import compile_playback_manifest,export_midi

ROOT=Path(__file__).resolve().parents[2]
PARENT_JOB='3ba648f12cb74dd59a45c1b2d4bc83ab'
PARENT_REVISION='db8c657e-62a5-4fad-a33e-cde25a9e1c0d'
OUT=ROOT/'output/evaluation/saved-accompaniment-workspace-2026-10-26'


def digest(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text())
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    write('protocol.json',dict(parent_job=PARENT_JOB,parent_revision=PARENT_REVISION,
        policy='Use preferred A accompaniment unchanged; crop saved G by absolute time, without quantization. Copy exact matching source audio into independent derived job. Save new revision only.',
        limitation='One 29-second excerpt, not whole-song processing or improved melody. No UI persistence/default change.'))
    store=RevisionStore(ROOT/'output/work/revisions');parent=store.load(PARENT_REVISION)
    before=parent.model_dump_json();accepted=read(ROOT/'docs/evaluation/accepted-accompaniment-2026-10-25.json')
    folder=ROOT/'output/evaluation/automatic-accompaniment-2026-10-24'
    score_bytes=(folder/'score.json').read_bytes();assert digest(score_bytes)==accepted['score_sha256']
    accompaniment=SongScore.model_validate_json(score_bytes)
    source=ROOT/'frontend/public/listening/automatic-accompaniment-2026-10-25/source.wav'
    source_bytes=source.read_bytes();assert digest(source_bytes)==accepted['source_sha256']
    start=accepted['analysis_offset'];audio,rate=sf.read(source,always_2d=True)
    parent_audio=ROOT/'output/work/jobs'/PARENT_JOB/'analysis-source.wav'
    with sf.SoundFile(parent_audio) as original:
        assert original.samplerate==rate
        original.seek(round(start*rate));expected=original.read(len(audio),always_2d=True)
    assert np.array_equal(audio,expected),'Frozen audio must be an exact sample crop of melody source'
    assert abs(len(audio)/rate-accompaniment.song.duration_seconds)<1/rate
    excerpt=compose_excerpt(parent,accompaniment,start)
    excerpt.song.title='小手拉大手 · 已確認伴奏＋原 G 旋律（29 秒片段）'
    job_id=uuid4().hex;metadata=read(folder/'report.json')
    p=excerpt.provenance
    p.beat_engine='beat_this_small';p.beat_engine_version=metadata['beat_this_version']
    p.chord_engine='chordino';p.chord_engine_version=''
    p.tempo_map_version='reviewed-small0-excerpt-v1'
    p.parameters.update(dict(analysis_source_job_id=job_id,candidate_source_job_id=job_id,
        melody_parent_job_id=PARENT_JOB,melody_parent_revision_id=PARENT_REVISION,
        source_audio_sha256=digest(source_bytes),accepted_accompaniment_score_sha256=digest(score_bytes),
        melody_parent_score_sha256=digest(before.encode()),derived_without_inference=True,
        chord_vamp_wrapper_version=metadata['vamp_version'],
        vocal_source_separated=False,melody_parent_vocal_source_separated=True))
    manifest=compile_playback_manifest(excerpt)
    approved=read(folder/'manifest.json')
    assert [e.model_dump(mode='json') for e in manifest.events if e.track=='guitar']==[e for e in approved['events'] if e['track']=='guitar']
    job_store=JobStore(ROOT/'output/work/jobs');directory=job_store.job_dir(job_id)
    directory.mkdir(exist_ok=False);(directory/'analysis-source.wav').write_bytes(source_bytes)
    now=datetime.now(timezone.utc).isoformat()
    job=AnalysisJob(id=job_id,status=JobStatus.COMPLETED,progress=100,
        message='Derived workspace excerpt from reviewed accompaniment and saved G; no new analysis.',
        skip_seconds=excerpt.song.source_start_seconds,analysis_seconds=excerpt.song.duration_seconds,
        created_at=now,updated_at=now,score=excerpt,artifacts=[])
    job_store.save(job)
    revision_id=store.save(excerpt)
    assert store.load(PARENT_REVISION).model_dump_json()==before
    assert store.load(revision_id)==excerpt
    write('score.json',excerpt.model_dump(mode='json'));write('manifest.json',manifest.model_dump(mode='json'))
    (OUT/'excerpt.mid').write_bytes(export_midi(excerpt))
    write('report.json',dict(job_id=job_id,revision_id=revision_id,parent_revision=PARENT_REVISION,
        parent_revision_unchanged=True,guitar_manifest_exact=True,source_samples_exact=True,
        source_sha256=digest(source_bytes),source_start_seconds=excerpt.song.source_start_seconds,
        duration=excerpt.song.duration_seconds,melody_notes=len(excerpt.melody),
        melody_pitch_changes=0,melody_timing='Subtract fixed crop offset; clip notes only at excerpt edges',
        original_G_notes=len(parent.melody),default_performance='original (preferred A)',
        url=f'http://localhost:5173/?revision={revision_id}'))
    print((OUT/'report.json').read_text())


if __name__=='__main__':main()
