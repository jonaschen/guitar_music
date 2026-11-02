"""Run the real local pipeline in an isolated directory, preserving the source job.

Usage: python smoke_guarded_timing_recovery.py WORK_DIR OUTPUT_DIR JOB_ID
Needs the optional fixed DBN dependency and the existing VAMP_PATH.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run(work, output, job_id):
    import torch
    from app.core.config import Settings, BeatEngine, ChordEngine
    from app.core.pipeline import create_pipeline
    from app.models.audio import SourceRequest, SourceType
    from app.exporters.midi import compile_playback_manifest, export_midi
    from app.exporters.musicxml import export_musicxml
    output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    db = sqlite3.connect(f'file:{work}/jobs/jobs.sqlite3?mode=ro', uri=True)
    payload = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()[0]
    job = json.loads(payload)
    source = work/'jobs'/job_id/('analysis-source.wav' if job.get('skip_seconds') or job.get('analysis_seconds') is not None else 'input.wav')
    settings = Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL, beat_recovery_enabled=True,
                        chord_engine=ChordEngine.CHORDINO,
                        rhythm_patterns_dir=Path(__file__).resolve().parents[2]/'rhythm-patterns')
    score = await create_pipeline(settings).run(
        SourceRequest(source_type=SourceType.LOCAL, path=source.resolve(), rights_confirmed=True),
        {'melody_mode':'off', 'chord_complexity':'full', '_artifact_directory':str(output.resolve())})
    (output/'score.json').write_text(score.model_dump_json(indent=2))
    manifest = compile_playback_manifest(score)
    (output/'manifest.json').write_text(manifest.model_dump_json(indent=2))
    (output/'score.mid').write_bytes(export_midi(score))
    (output/'score.musicxml').write_text(export_musicxml(score))
    before = [(c['symbol'],c['start'],c['end']) for c in job['score']['chords']]
    after = [(c.symbol,c.start,c.end) for c in score.chords]
    report = dict(timing_status=score.analysis.timing_status,
                  beat_recovery=score.provenance.parameters.get('beat_recovery_status'),
                  chords_unchanged=before==after, chords=len(after), beats=len(score.beats),
                  guitar_events=sum(e.track=='guitar' for e in manifest.events), melody_notes=len(score.melody),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  job_payload_sha256=hashlib.sha256(payload.encode()).hexdigest())
    assert report['timing_status']=='metered' and report['beat_recovery']=='recovered'
    assert before==after, 'Timing recovery unexpectedly changes harmonic content'
    assert db.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()[0]==payload
    db.close()
    (output/'check.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(run(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]))
