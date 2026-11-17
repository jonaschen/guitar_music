"""Bounded, source-bound structure candidates; never saves an editable document."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid

from ..evaluation.song_structure import load_ready_candidate
from ..evaluation.song_structure_feedback import candidate_digest
from .song_structure import StructureDocument, StructureSource

ACTIVE = {'running', 'cancelling'}
MESSAGES = {
    'idle': '尚未分析歌曲結構，可建立前奏、主歌與副歌的待確認初稿。',
    'running': '正在分析歌曲結構，可能需要約 15–20 分鐘；仍可練習根音。',
    'cancelling': '正在停止分析；已保存的結構與根音會保留。',
    'ready': '結構初稿已備妥，請先預覽；套用後才會改變歌曲結構。',
    'cancelled': '已取消分析，原有進度保留，可重新分析。',
    'failed': '結構分析未完成，原有進度保留，可重試。',
    'interrupted': '上次分析因服務中斷而停止，可重新分析。',
    'unavailable': '這台主機尚未備妥受資源限制的結構分析工具，仍可手動整理。',
    'busy': '另一首歌曲正在分析結構，請稍後再試。',
    'stale': '原曲來源已變動，這份分析初稿不能套用，請重新分析。',
}


def _identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
        return {'pid': pid, 'start': fields[19]} if fields[0] != 'Z' else None
    except (OSError, IndexError):
        return None


def _atomic(path, data):
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


class StructureAnalysisJobs:
    def __init__(self, work_dir, *, python=None, runner=None, protocol=None,
                 timeout=1200., poll_interval=.1, supervised=True):
        self.root = Path(work_dir) / 'structure-analysis'
        self.root.mkdir(parents=True, exist_ok=True)
        self.python = str(python) if python else None
        self.runner = Path(runner) if runner else Path(__file__).resolve().parents[2] / 'scripts/analyze_song_structure.py'
        self.protocol = Path(protocol) if protocol else None
        self.timeout = min(float(timeout), 1200.)
        if not math.isfinite(self.timeout) or self.timeout <= 0: raise ValueError('Analysis timeout must be finite and positive')
        self.poll_interval = poll_interval
        # False is injected only by tests with tiny fake subprocesses.
        self.supervised = supervised
        self._threads = []
        self._guard = threading.RLock()

    @classmethod
    def from_env(cls, work_dir):
        return cls(work_dir, python=os.environ.get('GUITARSCRIBE_STRUCTURE_PYTHON'),
                   runner=os.environ.get('GUITARSCRIBE_STRUCTURE_RUNNER'),
                   protocol=os.environ.get('GUITARSCRIBE_STRUCTURE_PROTOCOL'),
                   timeout=float(os.environ.get('GUITARSCRIBE_STRUCTURE_TIMEOUT_SECONDS', '1200')))

    def _directory(self, job):
        path = self.root / hashlib.sha256(job.encode()).hexdigest()
        path.mkdir(exist_ok=True)
        return path

    @contextmanager
    def _state(self, directory):
        with (directory / '.state.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = directory / 'state.json'
            try:
                record = json.loads(path.read_text()) if path.exists() else None
            except (ValueError, OSError):
                record = {'state': 'failed', 'run_id': None}
            yield record, path

    def _available(self):
        if (not self.python or not os.access(self.python, os.X_OK) or not self.runner.is_file()
                or self.protocol is None or not self.protocol.is_file()): return False
        try:
            template = json.loads(self.protocol.read_text())
            if not os.access(template['preprocessing']['python'], os.X_OK): return False
            if self.supervised:
                if not shutil.which('systemd-run') or not shutil.which('systemctl'): return False
                result = subprocess.run(['systemctl', '--user', 'show-environment'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                if result.returncode: return False
            return True
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired): return False

    def _reply(self, job, state, record=None, candidate=None):
        record = record or {}
        elapsed = (max(0., time.time() - record['started_epoch'])
                   if state in ACTIVE and 'started_epoch' in record else record.get('elapsed_seconds', 0.))
        message = MESSAGES[state]
        if state == 'failed' and record.get('reason') == 'timeout':
            message = '分析超過時間上限，已停止；原有進度保留，可重試。'
        return dict(job_id=job, state=state, message=message, candidate=candidate,
                    run_id=record.get('run_id'), elapsed_seconds=round(elapsed, 3))

    def _stop(self, record, process=None):
        unit = record.get('unit')
        if unit and unit == f"guitarscribe-structure-{record.get('run_id')}.scope":
            try:
                subprocess.run(['systemctl', '--user', 'stop', unit], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
            except (OSError, subprocess.TimeoutExpired): pass
        identity = record.get('process')
        pid = process.pid if process is not None else (identity or {}).get('pid')
        owned = process is not None or identity is not None and _identity(pid) == identity
        if owned and pid:
            # Keep the group ID even if its leader exited: Demucs may remain.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try: os.killpg(pid, sig)
                except ProcessLookupError: break
                if sig == signal.SIGTERM:
                    if process is not None:
                        try: process.wait(timeout=1)
                        except subprocess.TimeoutExpired: pass
                    else: time.sleep(.1)
            if process is not None: process.wait(timeout=3)

    def _recover(self, directory):
        with self._state(directory) as (record, path):
            if record and record.get('state') in ACTIVE and (not record.get('owner') or _identity(record['owner'].get('pid')) != record['owner']):
                self._stop(record)
                record.update(state='interrupted', elapsed_seconds=max(0., time.time() - record.get('started_epoch', time.time())))
                _atomic(path, record)
            return record

    def _document_from_run(self, run, source, *, allow_rebind=False):
        original = load_ready_candidate(run)
        manifest = json.loads((run / 'manifest.json').read_text())
        recorded = manifest['source']
        root_source = {k: v for k, v in source.items() if k != 'audio_sha256'}
        original_source = StructureSource.model_validate(dict(recorded['root_source'], audio_sha256=recorded['audio_sha256'])).model_dump(mode='json')
        same_audio_range = all(original_source[key] == source[key] for key in ('audio_sha256', 'duration', 'source_start'))
        same_identity = recorded['job'] == source['job_id'] and recorded['root_source'] == root_source
        if (original_source['job_id'] != recorded['job'] or not same_audio_range
                or not same_identity and not allow_rebind):
            raise ValueError('Completed run source does not match current recording')
        if self.protocol and self.protocol.is_file():
            template = json.loads(self.protocol.read_text())
            for key in ('model', 'candidate_commit'):
                if key in template and manifest.get(key) != template[key]:
                    raise ValueError('Completed run model differs from the configured protocol')
        sections = [dict(id=s['id'], start=s['start'], end=s['end'], label=s['label'],
                         display_label=s['display_label'], name_review_status='unreviewed',
                         boundary_review_status='unreviewed', note='',
                         model_sections=[dict(id=s['id'], start=s['start'], end=s['end'], label=s['label'],
                                              model_end=s.get('model_end'), original_number=i+1)])
                    for i, s in enumerate(original['sections'])]
        sections[-1]['end'] = source['duration']
        return StructureDocument.model_validate(dict(schema_version=1, source=source,
                                                      candidate_sha256=candidate_digest(original), sections=sections)).model_dump(mode='json')

    def import_completed_run(self, job, run, source, revalidate, *, allow_rebind=False):
        """Internal cache adoption, not an HTTP upload or an editable save."""
        source = StructureSource.model_validate(source).model_dump(mode='json')
        if source['job_id'] != job: raise ValueError('Source job mismatch')
        run = Path(run).resolve()
        with self._guard, (self.root / '.analysis.lock').open('a') as lock:
            for path in self.root.glob('*/state.json'): self._recover(path.parent)
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return self._reply(job, 'busy')
            document = self._document_from_run(run, source, allow_rebind=allow_rebind)
            if StructureSource.model_validate(revalidate()).model_dump(mode='json') != source:
                raise ValueError('Live source changed before importing completed analysis')
            current = self.status(job, source)
            if current['state'] == 'ready' and current['candidate'] == document: return current
            directory = self._directory(job)
            run_id = uuid.uuid4().hex
            target = directory / run_id; target.mkdir()
            _atomic(target / 'document.json', document)
            original_source = json.loads((run / 'manifest.json').read_text())['source']
            _atomic(target / 'import.json', dict(original_run=str(run), original_job=original_source['job'],
                    original_source=dict(original_source['root_source'], audio_sha256=original_source['audio_sha256']),
                    manifest_sha256=hashlib.sha256((run / 'manifest.json').read_bytes()).hexdigest(),
                    candidate_sha256=document['candidate_sha256']))
            record = dict(job_id=job, run_id=run_id, state='ready', source=source, kind='imported',
                          started_epoch=time.time(), elapsed_seconds=0., owner=None, process=None, unit=None)
            with self._state(directory) as (_, path): _atomic(path, record)
            return self._reply(job, 'ready', record, document)

    def status(self, job, source):
        source = StructureSource.model_validate(source).model_dump(mode='json')
        directory = self._directory(job)
        record = self._recover(directory)
        if not record: return self._reply(job, 'idle' if self._available() else 'unavailable')
        state = record.get('state', 'failed')
        if record.get('source') != source:
            if state in ACTIVE: return self.cancel(job, reason='stale')
            return self._reply(job, 'stale', record)
        if state == 'ready':
            try:
                run = record['run_id']
                if not re.fullmatch(r'[0-9a-f]{32}', run): raise ValueError('Invalid run')
                candidate = StructureDocument.model_validate_json((directory / run / 'document.json').read_text())
                if candidate.source.model_dump(mode='json') != source: raise ValueError('Source mismatch')
                return self._reply(job, state, record, candidate.model_dump(mode='json'))
            except (OSError, ValueError, KeyError): return self._reply(job, 'failed', record)
        return self._reply(job, state if state in MESSAGES else 'failed', record)

    def start(self, job, source, audio, title, revalidate, *, force=False):
        source = StructureSource.model_validate(source).model_dump(mode='json')
        if source['job_id'] != job: raise ValueError('Source job mismatch')
        with self._guard:
            status = self.status(job, source)
            if status['state'] in ACTIVE or status['state'] == 'ready' and not force: return status
            if not self._available(): return self._reply(job, 'unavailable')
            for path in self.root.glob('*/state.json'): self._recover(path.parent)
            lock = (self.root / '.analysis.lock').open('a')
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                status = self.status(job, source)
                return status if status['state'] in ACTIVE else self._reply(job, 'busy')
            directory = self._directory(job)
            run = uuid.uuid4().hex
            record = dict(job_id=job, run_id=run, state='running', source=source,
                          owner=_identity(os.getpid()), process=None, started_epoch=time.time(),
                          started_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=0.,
                          unit=f'guitarscribe-structure-{run}.scope' if self.supervised else None)
            try:
                run_dir = directory / run; run_dir.mkdir()
                template = json.loads(self.protocol.read_text())
                template['sources'] = [dict(job=job, title=title, audio=str(Path(audio).resolve()),
                                            audio_sha256=source['audio_sha256'],
                                            root_source={k: v for k, v in source.items() if k != 'audio_sha256'},
                                            reference_status='not_annotated')]
                limits = template.setdefault('resource_limits', {})
                limits['seconds_per_song'] = min(float(limits.get('seconds_per_song', 1200)), self.timeout)
                _atomic(run_dir / 'protocol.json', template)
                with self._state(directory) as (_, path): _atomic(path, record)
                thread = threading.Thread(target=self._run, args=(directory, record, template, revalidate, lock), daemon=True)
                self._threads = [t for t in self._threads if t.is_alive()] + [thread]
                thread.start()
            except Exception:
                lock.close(); raise
            return self._reply(job, 'running', record)

    def cancel(self, job, *, reason='cancelled'):
        directory = self._directory(job)
        self._recover(directory)
        with self._state(directory) as (record, path):
            if record and record.get('state') in ACTIVE:
                record.update(state='cancelling', cancel_reason=reason)
                _atomic(path, record)
                return self._reply(job, 'cancelling', record)
        return self._reply(job, 'idle')

    def _finish(self, directory, record, state, reason=None):
        with self._state(directory) as (latest, path):
            if not latest or latest.get('run_id') != record['run_id']: return
            if latest['state'] == 'cancelling': state = latest.get('cancel_reason', 'cancelled')
            latest.update(state=state, elapsed_seconds=max(0., time.time() - record['started_epoch']), reason=reason)
            _atomic(path, latest)

    def _run(self, directory, record, template, revalidate, lock):
        run_dir = directory / record['run_id']
        process = None
        state, reason = 'failed', None
        try:
            command = [self.python, str(self.runner), '--protocol', str(run_dir / 'protocol.json'),
                       '--job', record['job_id'], '--out', str(run_dir / 'result')]
            if self.supervised:
                limits = template['resource_limits']
                command = ['systemd-run', '--user', '--scope', '--quiet', '--unit', record['unit'],
                           '-p', f"MemoryMax={min(int(limits.get('memory_max_bytes', 2684354560)), 2684354560)}",
                           '-p', f"MemorySwapMax={min(int(limits.get('swap_max_bytes', 536870912)), 536870912)}",
                           '-p', f"CPUQuota={min(int(limits.get('cpu_quota_percent', 200)), 200)}%",
                           '-p', f"RuntimeMaxSec={limits['seconds_per_song']}", '-p', 'TimeoutStopSec=3', '--', *command]
            env = dict(os.environ)
            for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'): env[key] = '2'
            with (run_dir / 'worker.log').open('w') as log:
                process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True, pass_fds=(lock.fileno(),))
                record['process'] = _identity(process.pid)
                with self._state(directory) as (latest, path):
                    latest['process'] = record['process']; _atomic(path, latest)
                deadline = time.monotonic() + template['resource_limits']['seconds_per_song']
                while process.poll() is None:
                    with self._state(directory) as (latest, _):
                        if latest['state'] == 'cancelling':
                            state = latest.get('cancel_reason', 'cancelled'); return
                    if time.monotonic() > deadline:
                        reason = 'timeout'; return
                    time.sleep(self.poll_interval)
                if process.returncode:
                    if time.monotonic() >= deadline: reason = 'timeout'
                    return
            source = record['source']
            document = self._document_from_run(run_dir / 'result', source)
            try:
                if StructureSource.model_validate(revalidate()).model_dump(mode='json') != source:
                    state = 'stale'; return
            except Exception:
                state = 'stale'; return
            _atomic(run_dir / 'document.json', document)
            state = 'ready'
        except Exception:
            state = 'failed'
        finally:
            try:
                self._stop(record, process)
                self._finish(directory, record, state, reason)
            finally:
                lock.close()

    def wait(self, timeout=5):
        deadline = time.monotonic() + timeout
        for thread in self._threads: thread.join(max(0., deadline - time.monotonic()))
