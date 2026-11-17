"""Disposable real-API/browser fixture. Never opens the user's work directory."""
import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
import uvicorn
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.root_practice import RootPracticeStore, initial_document
from app.services.song_structure import SongStructureStore
from app.song_structure_api import create_song_structure_router, get_song_structure_store, get_structure_analysis_jobs
from app.services.structure_analysis_jobs import StructureAnalysisJobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5287)
    parser.add_argument('--frontend', type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='guitarscribe-structure-fullstack-') as temporary:
        directory = Path(temporary)
        job = SimpleNamespace(id='fixture-song', status=JobStatus.COMPLETED, skip_seconds=42., analysis_seconds=8.,
                              score=SongScore.model_validate({'song': {'duration_seconds': 8., 'source_start_seconds': 42.}}))
        with wave.open(str(directory/'analysis-source.wav'), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
            audio.writeframes(b'\0\0' * 64000)
        roots = RootPracticeStore(directory/'root-practice.sqlite3')
        jobs={job.id:job};other=deepcopy(job);other.id='fixture-analysis';jobs[other.id]=other
        for item in jobs.values(): roots.save(item.id, initial_document(item), 0)
        root_hash = hashlib.sha256(roots.path.read_bytes()).hexdigest()
        score = {key:value.score.model_dump_json() for key,value in jobs.items()}
        def get(identifier):
            if identifier not in jobs: raise FileNotFoundError(identifier)
            return jobs[identifier]
        service = SimpleNamespace(get=get, store=SimpleNamespace(job_dir=lambda _: directory))
        api = FastAPI()
        api.include_router(create_song_structure_router(lambda: service))
        store = SongStructureStore(directory/'song-structure.sqlite3')
        api.dependency_overrides[get_song_structure_store] = lambda: store
        protocol=directory/'protocol.json'
        protocol.write_text(json.dumps({'id':'browser-fixture','preprocessing':{'python':sys.executable},'resource_limits':{'seconds_per_song':15}}))
        analysis=StructureAnalysisJobs(directory,python=sys.executable,runner=Path(__file__).resolve().parents[1]/'tests/fixtures/structure_candidate_worker.py',protocol=protocol,timeout=15,supervised=False)
        api.dependency_overrides[get_structure_analysis_jobs] = lambda: analysis
        @api.get('/fixture/invariants')
        def invariants():
            return {'roots_unchanged': hashlib.sha256(roots.path.read_bytes()).hexdigest() == root_hash,
                    'score_unchanged': {key:value.score.model_dump_json() for key,value in jobs.items()} == score}
        app = FastAPI()
        app.mount('/backend', api)
        app.mount('/', StaticFiles(directory=args.frontend, html=True))
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')

if __name__ == '__main__': main()
