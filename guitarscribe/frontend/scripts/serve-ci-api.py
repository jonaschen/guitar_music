"""Disposable API for browser CI: never uses a developer's or cloud workspace."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import uvicorn

backend = Path(__file__).resolve().parents[2] / 'backend'
sys.path.insert(0, str(backend))
if __name__ == '__main__':
    with TemporaryDirectory(prefix='guitarscribe-browser-ci-') as work:
        os.environ['GUITARSCRIBE_WORK_DIR'] = work
        os.environ['GUITARSCRIBE_RHYTHM_PATTERNS_DIR'] = str(backend.parent / 'rhythm-patterns')
        os.environ['GUITARSCRIBE_YOUTUBE_ENABLED'] = 'false'
        from app.api import get_job_service
        get_job_service()  # Match the cloud host's eager startup, before parallel browser requests.
        uvicorn.run('app.api:app', host='127.0.0.1', port=5290, log_level='warning')
