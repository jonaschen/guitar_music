"""Cloud VM wrapper; local installations continue using app.web directly."""
import json
import fcntl
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

def song_library(work):
    work = Path(work)
    revisions = {}
    path = work / 'revisions/guitarscribe.sqlite3'
    if path.is_file():
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            for revision, payload in db.execute('SELECT id,payload FROM revisions ORDER BY created_at DESC'):
                score = json.loads(payload)
                params = score.get('provenance', {}).get('parameters', {}) or {}
                job = params.get('candidate_source_job_id') or params.get('analysis_source_job_id')
                if not job:
                    job = next((e.get('source_job_id') for e in score.get('melody_edits', []) if e.get('source_job_id')), None)
                if job and job not in revisions:
                    revisions[job] = revision
    path = work / 'jobs/jobs.sqlite3'
    if not path.is_file():
        return []
    songs = []
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        for (payload,) in db.execute('SELECT payload FROM jobs ORDER BY updated_at DESC'):
            job = json.loads(payload)
            if job.get('status') == 'completed' and job.get('score'):
                songs.append(dict(job_id=job['id'], title=job['score']['song'].get('title') or '未命名歌曲',
                                  revision_id=revisions.get(job['id'])))
    return songs


def analysis_request(method, path):
    return method == 'POST' and (path in ('/backend/api/v1/jobs', '/backend/api/v1/youtube-jobs')
        or path.endswith('/song-structure/analysis') or path.endswith('/root-candidates'))


def user_activity(method, path):
    if path == '/backend/health':
        return False
    if method not in ('GET', 'HEAD', 'OPTIONS'):
        return True
    return path in ('/', '/index.html') or '/audio' in path


def active_analysis(work):
    """Uncertain state inhibits idle shutdown, not the platform's hard stop."""
    work = Path(work)
    database = work / 'jobs/jobs.sqlite3'
    try:
        if database.exists():
            with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                for (payload,) in db.execute('SELECT payload FROM jobs'):
                    if json.loads(payload)['status'] not in ('completed', 'failed', 'cancelled'):
                        return True
        for state in work.glob('structure-analysis/*/state.json'):
            if json.loads(state.read_text()).get('state') in ('running', 'cancelling'):
                return True
        candidate_lock = work / 'jobs/.root-candidate.lock'
        if candidate_lock.exists():
            with candidate_lock.open('r') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
    except (OSError, ValueError, sqlite3.Error, KeyError):
        return True
    return False


def recover_boot_state(work, boot_id):
    """A new kernel boot cannot retain any previous analysis process or scope."""
    work = Path(work)
    marker = work / '.cloud-boot-id'
    previous = marker.read_text().strip() if marker.exists() else None
    if previous == boot_id:
        return False
    for state in work.glob('structure-analysis/*/state.json'):
        with (state.parent / '.state.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                record = json.loads(state.read_text())
            except ValueError:
                continue  # Existing manager exposes corrupt records as failed.
            if not isinstance(record, dict):
                continue
            if record.get('state') in ('running', 'cancelling'):
                # Never signal a PID copied from another kernel boot: it may now
                # belong to an unrelated process. Saved practice is independent.
                record.update(state='interrupted', owner=None, process=None, unit=None)
                temporary = state.with_suffix('.cloud-recovery.tmp')
                temporary.write_text(json.dumps(record, ensure_ascii=False))
                temporary.replace(state)
    marker.write_text(boot_id + '\n')
    return True


def create_app():
    from fastapi import Request, HTTPException
    from starlette.responses import JSONResponse
    from app.api import app as api
    from app.web import create_app as web_app
    work = Path(os.environ['GUITARSCRIBE_WORK_DIR'])
    work.mkdir(parents=True, exist_ok=True)
    recover_boot_state(work, Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    # Reuse existing interrupted-job recovery, before idle checks/backup timers.
    from app.api import get_job_service
    from app.song_structure_api import get_structure_analysis_jobs
    get_job_service()
    manager = get_structure_analysis_jobs()
    for state in manager.root.glob('*/state.json'):
        manager._recover(state.parent)
    activity = Path(os.environ.get('GUITARSCRIBE_ACTIVITY_FILE', '/run/guitarscribe/activity'))

    @api.get('/cloud/library')
    def library():
        return {'songs': song_library(os.environ['GUITARSCRIBE_WORK_DIR'])}

    @api.post('/cloud/activity')
    def heartbeat(request: Request):
        if request.headers.get('x-guitarscribe-activity') != 'visible':
            raise HTTPException(403)
        activity.touch()
        return {'ok': True}

    # Both cloud routes remain behind the existing authentication gate.
    app = web_app()

    async def wrapped(scope, receive, send):
        if scope['type'] != 'http':
            return await app(scope, receive, send)
        path, method = scope['path'], scope['method']
        try:
            stop_at = float(dict(scope.get('headers', [])).get(b'x-guitarscribe-stop-at', b'0'))
        except ValueError:
            stop_at = 0
        if analysis_request(method, path) and (not math.isfinite(stop_at) or stop_at - time.time() < 30 * 60):
            response = JSONResponse({'detail': '本輪雲端使用剩不到 30 分鐘，暫停新增分析。已存進度會保留；主機停止後可重新啟動。'}, status_code=409)
            return await response(scope, receive, send)
        async def tracked(message):
            if (message['type'] == 'http.response.start' and message['status'] < 400
                    and user_activity(method, path)):
                activity.touch()
            await send(message)
        return await app(scope, receive, tracked)
    return wrapped


def idle_due(work, activity, *, now=None, uptime=None, idle_seconds=1800):
    now = time.time() if now is None else now
    uptime = float(Path('/proc/uptime').read_text().split()[0]) if uptime is None else uptime
    try:
        last = Path(activity).stat().st_mtime
    except FileNotFoundError:
        return False
    return uptime > idle_seconds and now - last > idle_seconds and not active_analysis(work)


if __name__ == '__main__':
    import subprocess
    if idle_due('/srv/guitarscribe/work', '/run/guitarscribe/activity'):
        subprocess.run(['systemctl', 'poweroff'], check=True)
