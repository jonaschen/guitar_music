"""Prepare reproducible review inputs from completed jobs without changing them.

Usage: python prepare_performance_review.py WORK_DIR PLAN_JSON OUTPUT_DIR
The plan contains job, title, start, end and question for each fixed excerpt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.performance_draft import build_performance_draft
from app.exporters.midi import compile_playback_manifest


def prepare(work, plan, output):
    output.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(f'file:{work / "jobs/jobs.sqlite3"}?mode=ro', uri=True)
    rows = []
    for index, spec in enumerate(plan, 1):
        payload = db.execute('SELECT payload FROM jobs WHERE id=?', (spec['job'],)).fetchone()[0]
        job = json.loads(payload)
        assert job['status'] == 'completed' and job['score']
        score = SongScore.model_validate(job['score'])
        assert 0 <= spec['start'] < spec['end'] <= score.song.duration_seconds
        score.provenance.parameters['analysis_source_job_id'] = job['id']
        candidate, report = build_performance_draft(score)
        assert [(c.id, c.symbol) for c in score.chords] == [(c.id, c.symbol) for c in candidate.chords]
        assert score.beats == candidate.beats and score.melody == candidate.melody
        folder = output / str(index); folder.mkdir()
        variants = {}
        for name, value in [('a', score), ('b', candidate)]:
            (folder / f'{name}-score.json').write_text(value.model_dump_json(indent=2))
            manifest = compile_playback_manifest(value)
            (folder / f'{name}-manifest.json').write_text(manifest.model_dump_json(indent=2))
            events = [e for e in manifest.events if e.track == 'guitar']
            variants[name] = {'events': len(events), 'single_note_events': sum(len(e.pitches) == 1 for e in events),
                              'manifest_sha256': hashlib.sha256(manifest.model_dump_json().encode()).hexdigest()}
        source_dir = work / 'jobs' / job['id']
        source = source_dir / ('analysis-source.wav' if job.get('skip_seconds') or job.get('analysis_seconds') is not None else 'input.wav')
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-af',
                        f"atrim=start={spec['start']}:end={spec['end']},asetpts=PTS-STARTPTS",
                        '-ar','22050','-ac','1','-c:a','pcm_f32le',str(folder/'source.wav')],check=True)
        rows.append({**spec,'number':index,'report':report,'variants':variants,
                     'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                     'job_payload_sha256':hashlib.sha256(payload.encode()).hexdigest()})
    (output/'packet.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    return rows


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('work',type=Path);parser.add_argument('plan',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();rows=prepare(args.work,json.loads(args.plan.read_text()),args.output)
    print(json.dumps([{k:r[k] for k in ('number','job','variants')} for r in rows],ensure_ascii=False))
