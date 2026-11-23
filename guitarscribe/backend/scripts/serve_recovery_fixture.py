"""Disposable real job APIs; inference is deterministic and never uses personal audio."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', type=Path, required=True)
    parser.add_argument('--port', type=int, default=5296)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='guitarscribe-recovery-') as temporary:
        work = Path(temporary)
        os.environ['GUITARSCRIBE_WORK_DIR'] = str(work)
        os.environ['GUITARSCRIBE_YOUTUBE_ENABLED'] = 'false'
        # Two browsers exercise three POSTs each against this disposable server;
        # the default five/hour production limit is tested separately at the API.
        os.environ['GUITARSCRIBE_SUBMISSION_RATE_LIMIT'] = '20'
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        import uvicorn
        from app.api import app as api, get_job_service
        from app.models.jobs import AnalysisJob, JobStatus
        from app.models.score import SongInfo, SongScore
        from app.services.jobs import AnalysisJobService, JobStore
        store = JobStore(work / 'jobs')
        for browser in ('chromium', 'webkit'):
            identifier = f'interrupted-{browser}'
            job = AnalysisJob(id=identifier, status=JobStatus.CHORD_ANALYSIS, melody_mode='off',
                created_at='2026-11-23T00:00:00+00:00', updated_at='2026-11-23T00:00:00+00:00')
            store.save(job)
            directory = store.job_dir(identifier); directory.mkdir()
            with wave.open(str(directory / 'input.wav'), 'wb') as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                audio.writeframes(b'\0\0' * 8 * 8000)
            (directory / 'source-title.txt').write_text('中斷後的練習歌', encoding='utf8')
            (directory / 'personal-note.txt').write_text('原稿不可覆蓋', encoding='utf8')
        class Pipeline:
            async def run(self, source, options, progress_callback=None):
                await progress_callback('chord_analysis')
                return SongScore(song=SongInfo(title='fixture', duration_seconds=8))
        service = AnalysisJobService(store, Pipeline, job_ttl_seconds=None)
        api.dependency_overrides[get_job_service] = lambda: service
        originals = {name:store.load(name).model_dump_json() for name in ('interrupted-chromium','interrupted-webkit')}
        hashes = {str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for name in originals for p in store.job_dir(name).iterdir()}
        @api.get('/fixture/invariants')
        def invariants():
            return dict(original_jobs_unchanged=all(store.load(name).model_dump_json()==data for name,data in originals.items()),
                        original_files_unchanged=all(hashlib.sha256((work/name).read_bytes()).hexdigest()==sha for name,sha in hashes.items()))
        site=work/'site';site.mkdir()
        shutil.copy2(args.frontend/'index.html',site/'index.html')
        shutil.copytree(args.frontend/'assets',site/'assets')
        server=FastAPI();server.mount('/backend',api);server.mount('/',StaticFiles(directory=site,html=True))
        uvicorn.run(server,host='127.0.0.1',port=args.port,log_level='warning')

if __name__ == '__main__':main()
