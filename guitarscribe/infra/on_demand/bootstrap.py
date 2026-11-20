#!/usr/bin/python3
"""First-boot installer for a dedicated Ubuntu 24.04 VM. Run as root.

Metadata supplies only names of this application's private bucket/release/secret.
Credentials come from the attached, least-privileged service account.
Existing practice data is never replaced on reboot.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request

ROOT = Path('/srv/guitarscribe')


def metadata(key):
    request = urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/' + key,
                                     headers={'Metadata-Flavor': 'Google'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def google_get(url, destination=None):
    token = json.loads(metadata('instance/service-accounts/default/token'))['access_token']
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=120) as response:
        if destination:
            with Path(destination).open('wb') as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
        else:
            return response.read()


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def write(path, content, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def configure_maintenance():
    if not (ROOT / 'app/backend/backup_work.py').is_file():
        return
    temporary = ROOT / 'backup-tmp'; temporary.mkdir(exist_ok=True)
    run('chown', 'guitarscribe:guitarscribe', str(temporary))
    status = ROOT / 'maintenance'; status.mkdir(exist_ok=True, mode=0o700)
    run('chown', 'guitarscribe:guitarscribe', str(status))
    bucket = metadata('instance/attributes/guitarscribe-bucket')
    if not all(c.isalnum() or c in '.-_' for c in bucket):
        raise ValueError('Invalid backup bucket')
    write('/etc/systemd/system/guitarscribe-backup.service', f'''[Unit]
Description=Immutable private GuitarScribe backup
After=network-online.target
[Service]
Type=oneshot
User=guitarscribe
Group=guitarscribe
WorkingDirectory=/srv/guitarscribe/app/backend
ExecStart=/srv/guitarscribe/runtime/main/bin/python backup_work.py backup --work /srv/guitarscribe/work --bucket {bucket} --temp-root /srv/guitarscribe/backup-tmp --status-file /srv/guitarscribe/maintenance/backup-status.json
TimeoutStartSec=15min
MemoryMax=2G
CPUQuota=50%
Nice=10
NoNewPrivileges=true
''')
    write('/etc/systemd/system/guitarscribe-backup.timer', '''[Unit]
Description=Back up saved GuitarScribe progress while running
[Timer]
OnBootSec=15min
OnUnitActiveSec=30min
[Install]
WantedBy=timers.target
''')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'guitarscribe-backup.timer')


def main():
    if os.geteuid() != 0 or platform.machine() != 'x86_64' or 'VERSION_ID="24.04"' not in Path('/etc/os-release').read_text():
        raise RuntimeError('Requires root on Ubuntu 24.04 x86_64')
    ROOT.mkdir(parents=True, exist_ok=True)
    if (ROOT / '.installed').is_file():
        configure_maintenance()
        print('Existing installation retained; systemd starts the saved workspace.')
        return
    bucket = metadata('instance/attributes/guitarscribe-bucket')
    release = metadata('instance/attributes/guitarscribe-release')
    secret = metadata('instance/attributes/guitarscribe-secret')
    def fetch(name, destination=None):
        obj = urllib.parse.quote(f'{release}/{name}', safe='')
        return google_get(f'https://storage.googleapis.com/storage/v1/b/{bucket}/o/{obj}?alt=media', destination)
    manifest = json.loads(fetch('manifest.json'))
    installing = ROOT / '.installing-manifest.json'
    if installing.exists() and json.loads(installing.read_text()) != manifest:
        raise RuntimeError('A different installation is unfinished; review before changing releases')
    if (ROOT / 'work').exists() and not installing.exists():
        raise RuntimeError('Existing unmarked workspace requires operator review; never overwrite progress')
    write(installing, json.dumps(manifest))
    downloads = ROOT / 'install'; downloads.mkdir(exist_ok=True)
    for name, info in manifest['artifacts'].items():
        if Path(name).name != name:
            raise ValueError('Invalid artifact name')
        path = downloads / name
        fetch(name, path)
        h = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024): h.update(block)
        if h.hexdigest() != info['sha256'] or path.stat().st_size != info['bytes']:
            raise RuntimeError('Artifact checksum mismatch: ' + name)
    run('apt-get', 'update', '-qq')
    run('apt-get', 'install', '-y', '--no-install-recommends', 'python3.12-venv', 'ffmpeg',
        'libsndfile1', 'libvamp-sdk2v5', 'dbus-user-session', 'ca-certificates')
    run('useradd', '--system', '--uid', '1501', '--home-dir', str(ROOT / 'home'), '--create-home',
        '--shell', '/usr/sbin/nologin', 'guitarscribe') if subprocess.run(['id', 'guitarscribe'], stdout=subprocess.DEVNULL).returncode else None
    for name in ('main', 'structure'):
        run('python3.12', '-m', 'venv', str(ROOT / 'runtime' / name))
    for filename in ('runtime.tar.gz', 'app.tar.gz'):
        with tarfile.open(downloads / filename) as archive:
            archive.extractall(ROOT, filter='data')
    if not (ROOT / 'work').exists():
        import shutil
        staging = downloads / 'personal-staging'
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        with tarfile.open(downloads / 'personal-work.tar.gz') as archive:
            archive.extractall(staging, filter='data')
        (staging / 'work').rename(ROOT / 'work')
    structure_site = ROOT / 'runtime/structure/lib/python3.12/site-packages'
    # The source environment shares the accepted main runtime through one .pth.
    for path in structure_site.glob('*.pth'):
        text = path.read_text()
        if '/home/jonas/.cache/guitarscribe-runtime/' in text:
            path.write_text(text.replace('/home/jonas/.cache/guitarscribe-runtime/', '/srv/guitarscribe/runtime/main/'))
    write(ROOT / 'protocol.json', (downloads / 'protocol.json').read_text())
    response = json.loads(google_get(f'https://secretmanager.googleapis.com/v1/{secret}:access'))
    credentials = base64.b64decode(response['payload']['data']).decode()
    parsed = json.loads(credentials)
    if not parsed.get('username') or len(parsed.get('password', '')) < 24:
        raise ValueError('Expected a dedicated strong cloud credential')
    write(ROOT / 'access.json', credentials, 0o600)
    write('/usr/local/bin/guitarscribe-ytdlp', '#!/bin/sh\nexec /srv/guitarscribe/runtime/main/bin/python -m yt_dlp --js-runtimes node:/srv/guitarscribe/runtime/bin/node "$@"\n', 0o755)
    environment = {
        'GUITARSCRIBE_WEB_ACCESS_FILE': str(ROOT / 'access.json'),
        'GUITARSCRIBE_WEB_STATIC_DIR': str(ROOT / 'site'),
        'GUITARSCRIBE_WORK_DIR': str(ROOT / 'work'),
        'GUITARSCRIBE_ACTIVITY_FILE': '/run/guitarscribe/activity',
        'GUITARSCRIBE_KEEP_SONGS': 'true',
        'GUITARSCRIBE_BEAT_ENGINE': 'beat_this_small', 'GUITARSCRIBE_BEAT_RECOVERY_ENABLED': 'true',
        'GUITARSCRIBE_CHORD_ENGINE': 'chordino', 'GUITARSCRIBE_MELODY_SEPARATOR': 'off',
        'GUITARSCRIBE_YOUTUBE_ENABLED': 'true', 'GUITARSCRIBE_YTDLP_BINARY': '/usr/local/bin/guitarscribe-ytdlp',
        'GUITARSCRIBE_YOUTUBE_JS_RUNTIME': 'node:/srv/guitarscribe/runtime/bin/node',
        'GUITARSCRIBE_SUBMISSION_RATE_LIMIT': '5',
        'GUITARSCRIBE_RHYTHM_PATTERNS_DIR': str(ROOT / 'app/rhythm-patterns'),
        'GUITARSCRIBE_ROOT_PLUGIN_DIR': str(ROOT / 'runtime/root-plugin'),
        'GUITARSCRIBE_STRUCTURE_PYTHON': str(ROOT / 'runtime/structure/bin/python'),
        'GUITARSCRIBE_STRUCTURE_PROTOCOL': str(ROOT / 'protocol.json'),
        'VAMP_PATH': str(ROOT / 'runtime/chordino'),
        'PYTHONPATH': str(ROOT / 'runtime/dbn') + ':' + str(ROOT / 'runtime/vamp-python'),
        'TORCH_HOME': str(ROOT / 'runtime/torch'), 'OMP_NUM_THREADS': '2',
        'PYTHONUNBUFFERED': '1',
    }
    write(ROOT / 'environment', ''.join(f'{key}={value}\n' for key, value in environment.items()), 0o600)
    unit = '''[Unit]
Description=GuitarScribe private practice
After=network-online.target
[Service]
WorkingDirectory=/srv/guitarscribe/app/backend
EnvironmentFile=/srv/guitarscribe/environment
ExecStart=/srv/guitarscribe/runtime/main/bin/python -m uvicorn host_activity:create_app --factory --host 0.0.0.0 --port 5273
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
MemoryMax=6G
CPUQuota=200%
[Install]
WantedBy=default.target
'''
    write(ROOT / 'home/.config/systemd/user/guitarscribe.service', unit)
    write('/etc/tmpfiles.d/guitarscribe.conf', 'd /run/guitarscribe 0750 guitarscribe guitarscribe -\nf /run/guitarscribe/activity 0640 guitarscribe guitarscribe -\n')
    write('/etc/systemd/system/guitarscribe-idle.service', '''[Unit]
Description=Stop an idle private GuitarScribe VM
[Service]
Type=oneshot
ExecStart=/srv/guitarscribe/runtime/main/bin/python /srv/guitarscribe/app/backend/host_activity.py
''')
    write('/etc/systemd/system/guitarscribe-idle.timer', '''[Unit]
Description=Check private GuitarScribe activity
[Timer]
OnBootSec=35min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
''')
    run('chown', '-R', 'guitarscribe:guitarscribe', str(ROOT))
    run('systemd-tmpfiles', '--create', '/etc/tmpfiles.d/guitarscribe.conf')
    run('loginctl', 'enable-linger', 'guitarscribe')
    run('systemctl', 'start', 'user@1501.service')
    env = dict(os.environ, XDG_RUNTIME_DIR='/run/user/1501', DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1501/bus')
    run('runuser', '-u', 'guitarscribe', '--', 'systemctl', '--user', 'enable', '--now', 'guitarscribe.service', env=env)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'guitarscribe-idle.timer')
    smoke = '''import json,hashlib,os
from pathlib import Path
import vamp
assert 'nnls-chroma:chordino' in vamp.list_plugins()
from beat_this.model.postprocessor import Postprocessor
Postprocessor('dbn')
from app.services.structure_analysis_jobs import StructureAnalysisJobs
assert StructureAnalysisJobs.from_env(Path(os.environ['GUITARSCRIBE_WORK_DIR']))._available()
protocol=json.loads(Path(os.environ['GUITARSCRIBE_STRUCTURE_PROTOCOL']).read_text())
for item in protocol['runtime_weights']:
 assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
from host_activity import song_library
assert song_library(os.environ['GUITARSCRIBE_WORK_DIR'])
'''
    smoke_env = dict(env, **environment)
    run('runuser', '-u', 'guitarscribe', '--', str(ROOT / 'runtime/main/bin/python'), '-c', smoke,
        cwd=ROOT / 'app/backend', env=smoke_env)
    run('runuser', '-u', 'guitarscribe', '--', str(ROOT / 'runtime/structure/bin/python'),
        '-c', 'import allin1_infer, demucs_infer, torch; assert not torch.cuda.is_available()',
        cwd=ROOT / 'app/backend', env=smoke_env)
    auth = base64.b64encode(f"{parsed['username']}:{parsed['password']}".encode()).decode()
    for attempt in range(30):
        try:
            request = urllib.request.Request('http://127.0.0.1:5273/backend/health', headers={'Authorization': 'Basic ' + auth})
            with urllib.request.urlopen(request, timeout=3) as response:
                if json.load(response).get('status') == 'ok': break
        except (OSError, ValueError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError('Application health check failed; installation remains resumable')
    write(ROOT / 'release-manifest.json', json.dumps(manifest, indent=2))
    write(ROOT / '.installed', manifest['commit'] + '\n')
    configure_maintenance()
    print('Private installation complete. Run functional and persistence checks before publishing.')


if __name__ == '__main__':
    main()
