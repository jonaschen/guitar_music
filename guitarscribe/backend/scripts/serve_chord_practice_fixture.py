"""Disposable real chord/root/structure APIs for browser tests; no user DB access."""
import argparse
import hashlib
import math
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from app.models.jobs import JobStatus
from app.learning_practice_api import create_learning_router,get_learning_store
from app.services.learning_practice import LearningStore
from app.models.score import SongScore
from app.services.root_practice import RootPracticeStore, initial_document
from app.services.song_structure import SongStructureStore, source_for_job
from app.services.chord_practice import ChordPracticeStore
from app.root_practice_api import create_root_router, get_root_practice_store
from app.song_structure_api import create_song_structure_router, get_song_structure_store
from app.chord_practice_api import create_chord_practice_router, get_chord_practice_store, get_chord_structure_path


def create_fixture(directory):
    job = SimpleNamespace(id='fixture-song', status=JobStatus.COMPLETED,
                          skip_seconds=42., analysis_seconds=12., score=SongScore.model_validate(dict(
                              song=dict(title='Section chord fixture', duration_seconds=12., source_start_seconds=42.),
                              chords=[dict(id='c', start=0., end=6., symbol='C'),
                                      dict(id='g', start=6., end=12., symbol='G')])))
    with wave.open(str(directory / 'analysis-source.wav'), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b''.join(struct.pack('<h', int(1000 * math.sin(i / 8000 * 2 * math.pi * 220)))
                                  for i in range(12 * 8000)))
    roots = RootPracticeStore(directory / 'root-practice.sqlite3')
    roots.save(job.id, initial_document(job), 0)
    structures = SongStructureStore(directory / 'song-structure.sqlite3')
    source = source_for_job(job, directory).model_dump(mode='json')
    structures.save(job.id, dict(schema_version=1, source=source, candidate_sha256=None, sections=[
        dict(id=identifier, start=start, end=end, label=identifier, display_label=name,
             name_review_status='user_confirmed', boundary_review_status='user_confirmed')
        for identifier, start, end, name in [('intro',0.,4.,'前奏'), ('chorus',4.,10.,'副歌'), ('outro',10.,12.,'尾奏')]
    ]), 0)
    chords = ChordPracticeStore(directory / 'chord-practice.sqlite3')
    original_root = hashlib.sha256(roots.path.read_bytes()).hexdigest()
    original_structure = hashlib.sha256(structures.path.read_bytes()).hexdigest()
    original_score = job.score.model_dump_json()

    def get(identifier):
        if identifier != job.id: raise FileNotFoundError(identifier)
        return job
    service = SimpleNamespace(get=get, store=SimpleNamespace(job_dir=lambda _: directory))
    api = FastAPI()
    api.include_router(create_root_router(lambda: service))
    api.include_router(create_song_structure_router(lambda: service))
    api.include_router(create_chord_practice_router(lambda: service))
    api.include_router(create_learning_router(lambda: service))
    api.dependency_overrides[get_learning_store] = lambda: LearningStore(directory / "learning-practice.sqlite3")
    api.dependency_overrides[get_root_practice_store] = lambda: roots
    api.dependency_overrides[get_song_structure_store] = lambda: structures
    api.dependency_overrides[get_chord_practice_store] = lambda: chords
    api.dependency_overrides[get_chord_structure_path] = lambda: structures.path

    @api.get('/api/v1/jobs/{job_id}')
    def read_job(job_id: str):
        item = get(job_id)
        return dict(id=item.id, status='completed', score=item.score.model_dump(mode='json'),
                    skip_seconds=item.skip_seconds, analysis_seconds=item.analysis_seconds)

    @api.get('/fixture/invariants')
    def invariants():
        return dict(root_unchanged=hashlib.sha256(roots.path.read_bytes()).hexdigest() == original_root,
                    structure_unchanged=hashlib.sha256(structures.path.read_bytes()).hexdigest() == original_structure,
                    score_unchanged=job.score.model_dump_json() == original_score)
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5289)
    parser.add_argument('--frontend', type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='guitarscribe-section-chords-') as temporary:
        app = FastAPI()
        app.mount('/backend', create_fixture(Path(temporary)))
        app.mount('/', StaticFiles(directory=args.frontend, html=True))
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__': main()
