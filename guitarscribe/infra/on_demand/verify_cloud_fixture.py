"""Operator-only persistence fixture. Never changes existing songs or their drafts.

Run on the private VM as guitarscribe; seed once, exercise its ID through the
public authenticated API, reboot, verify, then clean. Cleanup uses a private
ownership marker and refuses to remove any other job. Not installed as an API.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
from uuid import uuid4
import wave

ROOT = Path('/srv/guitarscribe')
WORK = ROOT / 'work'
MARKER = ROOT / 'cloud-verification-fixture.json'
sys.path.insert(0, str(ROOT / 'app/backend'))


def db_hashes():
    result = {}
    for path in sorted(WORK.rglob('*.sqlite3')):
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            result[str(path.relative_to(WORK))] = hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()
    return result


def seed():
    from app.models.jobs import AnalysisJob, JobStatus
    from app.models.score import SongScore
    from app.services.jobs import JobStore
    from app.services.root_practice import RootPracticeStore, initial_document
    from app.services.song_structure import SongStructureStore, source_for_job
    assert not MARKER.exists(), 'Existing owned fixture must be cleaned first'
    identifier = uuid4().hex
    # Persist the ownership marker BEFORE inserting anything, so an interrupted
    # verification can still clean only its own data.
    state = dict(job_id=identifier, baseline=db_hashes())
    with MARKER.open('x') as stream: json.dump(state, stream)
    MARKER.chmod(0o600)
    store = JobStore(WORK / 'jobs')
    directory = store.job_dir(identifier); directory.mkdir()
    job = AnalysisJob(id=identifier, status=JobStatus.COMPLETED, progress=100,
                      created_at='2000-01-01T00:00:00+00:00', updated_at='2000-01-01T00:00:00+00:00',
                      skip_seconds=42., analysis_seconds=12., score=SongScore.model_validate(dict(
                          song=dict(title='Cloud persistence verification (temporary)', duration_seconds=12., source_start_seconds=42.),
                          chords=[dict(id='c', start=0., end=6., symbol='C'), dict(id='g', start=6., end=12., symbol='G')])) )
    with wave.open(str(directory / 'analysis-source.wav'), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b''.join(struct.pack('<h', int(1000 * math.sin(i / 8000 * 2 * math.pi * 220)))
                                  for i in range(12 * 8000)))
    store.save(job)
    RootPracticeStore(WORK / 'root-practice.sqlite3').save(identifier, initial_document(job), 0)
    source = source_for_job(job, directory).model_dump(mode='json')
    SongStructureStore(WORK / 'song-structure.sqlite3').save(identifier, dict(schema_version=1, source=source,
        candidate_sha256=None, sections=[dict(id=label, start=start, end=end, label=label, display_label=name,
        name_review_status='user_confirmed', boundary_review_status='user_confirmed')
        for label,start,end,name in [('intro',0.,4.,'前奏'), ('chorus',4.,10.,'副歌'), ('outro',10.,12.,'尾奏')]]), 0)
    print(json.dumps(dict(job_id=identifier, seeded=True)))


def clean():
    state = json.loads(MARKER.read_text()); identifier = state['job_id']
    assert len(identifier) == 32 and all(c in '0123456789abcdef' for c in identifier)
    from host_activity import active_analysis
    assert not active_analysis(WORK), 'Wait for analysis before cleaning verification data'
    from app.services.jobs import JobStore
    job = JobStore(WORK / 'jobs').load(identifier)
    assert job.score.song.title == 'Cloud persistence verification (temporary)'
    for name, tables, key in [
        ('chord-practice.sqlite3', ['chord_practice', 'chord_practice_history'], 'job_id'),
        ('root-practice.sqlite3', ['root_practice', 'root_practice_history'], 'job_id'),
        ('song-structure.sqlite3', ['song_structure', 'song_structure_history'], 'job_id'),
        ('jobs/jobs.sqlite3', ['jobs'], 'id'),
    ]:
        path = WORK / name
        if not path.exists(): continue
        empty = True
        with closing(sqlite3.connect(path)) as db, db:
            for table in tables:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    db.execute(f'DELETE FROM {table} WHERE {key}=?', (identifier,))
                    empty = empty and db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        if name not in state['baseline'] and name == 'chord-practice.sqlite3' and empty:
            for suffix in ('', '-wal', '-shm'): Path(str(path) + suffix).unlink(missing_ok=True)
    shutil.rmtree(WORK / 'jobs' / identifier)
    candidate = WORK / 'structure-analysis' / hashlib.sha256(identifier.encode()).hexdigest()
    if candidate.exists(): shutil.rmtree(candidate)
    assert db_hashes() == state['baseline'], 'Existing user databases changed during verification; inspect without overwriting'
    MARKER.unlink()
    print(json.dumps(dict(cleaned=True, user_databases_unchanged=True, database_count=len(state['baseline']))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['seed', 'clean'])
    args = parser.parse_args()
    {'seed': seed, 'clean': clean}[args.action]()
