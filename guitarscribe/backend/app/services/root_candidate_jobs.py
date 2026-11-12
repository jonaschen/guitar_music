"""Bounded local candidate preparation, with cancellation and independent caches."""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from .root_candidates import METHOD


def plugin_path():
    return Path(os.environ.get('GUITARSCRIBE_ROOT_PLUGIN_DIR', str(Path.home() / '.cache/guitarscribe-root-candidates/plugin')))


class RootCandidateJobs:
    def __init__(self):
        self.running = {}
        self.failures = {}

    @staticmethod
    def cache_path(directory):
        return directory / 'root-evidence-v1.json'

    def evidence(self, directory, source):
        path = self.cache_path(directory)
        if not path.is_file():
            return None
        try:
            evidence = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if evidence.get('source') != source or evidence.get('method') != METHOD:
            return None
        return evidence

    def status(self, directory, source):
        key = str(directory)
        if key in self.running:
            if self.running[key]['cancel'].is_set():
                return {'state': 'cancelling', 'message': '正在取消準備；練習進度保留。'}
            return {'state': 'running', 'message': '正在整理參考音，仍可先自行聽辨。'}
        evidence = self.evidence(directory, source)
        if evidence:
            return {'state': 'ready', 'message': '參考音已備妥；三個音都可能不合，請以聽辨為準。', 'method': METHOD}
        if key in self.failures:
            return {'state': 'failed', 'message': self.failures[key]}
        if not (plugin_path() / 'root-plugin.json').is_file():
            return {'state': 'unavailable', 'message': '這台主機尚未準備參考音工具，仍可選其他音練習。'}
        return {'state': 'idle', 'message': '可準備三個參考音，協助逐段比較。'}

    def start(self, directory, source, audio):
        state = self.status(directory, source)
        if state['state'] in ('ready', 'running', 'unavailable'):
            return state
        if self.running:
            return {'state': 'busy', 'message': '另一首正在準備參考音，請稍後再試。'}
        key = str(directory); cancel = threading.Event()
        self.failures.pop(key, None)
        self.running[key] = {'cancel': cancel, 'task': None}

        async def prepare():
            try:
                await asyncio.to_thread(self._run, directory, source, audio, cancel)
            except Exception as error:
                if cancel.is_set():
                    self.failures[key] = '已取消準備；你的練習進度保留。'
                elif isinstance(error, TimeoutError):
                    self.failures[key] = '準備超過時間上限，請先自行聽辨或稍後重試。'
                else:
                    self.failures[key] = '參考音目前無法準備；仍可自行聽辨，或稍後重試。'
            finally:
                self.running.pop(key, None)
        self.running[key]['task'] = asyncio.create_task(prepare())
        return self.status(directory, source)

    def cancel(self, directory):
        item = self.running.get(str(directory))
        if item:
            item['cancel'].set()
        return {'state': 'cancelling' if item else 'idle', 'message': '正在取消準備。' if item else '沒有進行中的準備。'}

    def _run(self, directory, source, audio, cancel):
        plugin = plugin_path().resolve()
        metadata = json.loads((plugin / 'root-plugin.json').read_text())
        library = plugin / 'nnls-chroma.so'
        digest = hashlib.sha256(library.read_bytes()).hexdigest()
        if digest != metadata['library_sha256']:
            raise ValueError('Plugin changed')
        with (directory.parent / '.root-candidate.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with tempfile.TemporaryDirectory(prefix='root-candidates-', dir=directory) as temp:
                temp = Path(temp)
                config = {'audio': str(audio.resolve()), 'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
                          'library': str(library), 'library_sha256': digest, 'duration': source['duration'],
                          'source': source, 'output': str(temp / 'evidence.json')}
                (temp / 'config.json').write_text(json.dumps(config))
                env = dict(os.environ, VAMP_PATH=str(plugin), GUITARSCRIBE_TRACE_PATH=str(temp / 'trace.json'))
                backend = str(Path(__file__).resolve().parents[2])
                env['PYTHONPATH'] = backend + os.pathsep + env.get('PYTHONPATH', '')
                for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
                    env[name] = '2'
                with (temp / 'worker.log').open('w') as log:
                    process = subprocess.Popen([sys.executable, '-m', 'app.services.root_candidate_worker', str(temp / 'config.json')],
                                               env=env, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        deadline = time.monotonic() + 180
                        while process.poll() is None:
                            if cancel.wait(.1):
                                raise RuntimeError('Cancelled')
                            if time.monotonic() > deadline:
                                raise TimeoutError()
                        if process.returncode:
                            raise RuntimeError('Observer failed')
                        if cancel.is_set():
                            raise RuntimeError('Cancelled')
                        # Atomic publication only after a fully parsed, matched result.
                        result = json.loads((temp / 'evidence.json').read_text())
                        if result['source'] != source or result['method'] != METHOD:
                            raise ValueError('Evidence identity mismatch')
                        (temp / 'evidence.json').replace(self.cache_path(directory))
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                process.kill(); process.wait()
