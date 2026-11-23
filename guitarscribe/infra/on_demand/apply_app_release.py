"""Apply a reviewed app-only package on the existing personal VM.

No downloads, credential changes, runtime changes or workspace restoration.
Requires explicit old/new commits and package hash. Use the deployment runbook
for normal gateway wake, backup, upload, public verification and shutdown.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

from host_activity import active_analysis
from release_workspace import file_sha, snapshot, verify_preserved


def stage_release(archive_path, manifest_path, release, commit, sha):
    archive_path, manifest_path, release = Path(archive_path), Path(manifest_path), Path(release)
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('release_kind') != 'app_only' or manifest.get('commit') != commit
            or set(manifest.get('artifacts', {})) != {'app.tar.gz'}):
        raise ValueError('Release identity or kind differs from reviewed values')
    artifact = manifest['artifacts']['app.tar.gz']
    if file_sha(archive_path) != sha or artifact.get('sha256') != sha or artifact.get('bytes') != archive_path.stat().st_size:
        raise ValueError('Release package hash or size differs')
    release.mkdir(parents=True, exist_ok=False)
    stage = release/'stage'; stage.mkdir()
    with tarfile.open(archive_path) as archive:
        names = set()
        for member in archive.getmembers():
            path = Path(member.name)
            if (not path.parts or path.is_absolute() or '..' in path.parts
                    or path.parts[0] not in ('app', 'site') or not (member.isfile() or member.isdir())
                    or path.as_posix() in names):
                raise ValueError('Unsafe or duplicate archive member')
            names.add(path.as_posix())
        archive.extractall(stage, filter='data')
    if not (stage/'app/backend/app/api.py').is_file() or not (stage/'site/index.html').is_file():
        raise ValueError('Release lacks application entry points')
    shutil.copyfile(manifest_path, release/'manifest.json')
    shutil.copyfile(archive_path, release/'app.tar.gz')
    return manifest


def apply_staged(root, release, service, check_health, *, allow_retry_schema=False):
    root, release = Path(root), Path(release)
    stage, previous = release/'stage', release/'previous'
    previous.mkdir(exist_ok=False)
    moved = []
    manifest = json.loads((release/'manifest.json').read_text())
    if (root/'app-release-manifest.json').exists():
        shutil.copyfile(root/'app-release-manifest.json', previous/'app-release-manifest.json')
    try:
        service('stop')
        before = snapshot(root/'work')
        (release/'workspace-before.json').write_text(json.dumps(before, indent=2))
        for name in ('app', 'site'):
            (root/name).rename(previous/name); moved.append(name)
            (stage/name).rename(root/name)
        service('start'); check_health()
        after = snapshot(root/'work')
        (release/'workspace-after.json').write_text(json.dumps(after, indent=2))
        additions = verify_preserved(before, after, allow_retry_schema=allow_retry_schema)
        temporary = root/'.app-release-manifest.next'
        temporary.write_text(json.dumps(manifest, indent=2)+'\n')
        temporary.replace(root/'app-release-manifest.json')
        return dict(commit=manifest['commit'], databases=len(before['databases']), files=len(before['files']),
                    allowed_additions=additions, saved_progress_unchanged=True, previous_code=str(previous))
    except BaseException:
        service('stop')
        for name in reversed(moved):
            if (root/name).exists(): (root/name).rename(release/('failed-'+name))
            (previous/name).rename(root/name)
        service('start')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--release', required=True, help='New directory name, e.g. 2026-11-23-v7')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--expected-current-commit', required=True)
    parser.add_argument('--allow-retry-schema', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.release): parser.error('Invalid release name')
    if not all(re.fullmatch(r'[0-9a-f]{40}', c) for c in (args.commit, args.expected_current_commit)):
        parser.error('Full Git commits required')
    if not re.fullmatch(r'[0-9a-f]{64}', args.sha256): parser.error('SHA256 required')
    root = Path('/srv/guitarscribe')
    if os.geteuid() != 0 or not (root/'.installed').is_file(): raise RuntimeError('Run as root on the installed personal VM')
    current = json.loads((root/'app-release-manifest.json').read_text())
    if current['commit'] != args.expected_current_commit: raise RuntimeError('Live release changed; inspect before applying')
    if any((root/name).is_symlink() for name in ('app', 'site', 'work', 'releases')): raise RuntimeError('Unexpected installation symlink')
    activity = Path('/run/guitarscribe/activity'); stamp = activity.stat().st_mtime_ns
    def run(*command, **kwargs): return subprocess.run(command, check=True, **kwargs)
    def state(unit): return subprocess.check_output(['systemctl', 'show', unit, '-p', 'ActiveState', '--value'], text=True).strip()
    def safe_window():
        if activity.stat().st_mtime_ns != stamp or time.time()-activity.stat().st_mtime < 60 or active_analysis(root/'work'):
            raise RuntimeError('Recent activity or active analysis; no safe update window')
        if state('guitarscribe-backup.service') in ('active', 'activating', 'deactivating'):
            raise RuntimeError('Backup is active')
        backup = json.loads((root/'maintenance/backup-status.json').read_text())
        success = backup.get('last_success') or {}
        when = success.get('snapshot_at', 0)
        if (backup.get('state') != 'complete' or not success.get('manifest_sha256')
                or not 0 <= time.time()-when <= 1200 or when < stamp/1e9):
            raise RuntimeError('A fresh completed backup after the last activity is required')
    safe_window()
    release = root/'releases'/args.release
    stage_release(args.archive, args.manifest, release, args.commit, args.sha256)
    run('chown', '-R', 'guitarscribe:guitarscribe', str(release/'stage'))
    account = pwd.getpwnam('guitarscribe')
    env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{account.pw_uid}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{account.pw_uid}/bus')
    def service(action): run('runuser', '-u', 'guitarscribe', '--', 'systemctl', '--user', action, 'guitarscribe.service', env=env)
    access = json.loads((root/'access.json').read_text())
    auth = 'Basic ' + base64.b64encode((access['username']+':'+access['password']).encode()).decode()
    def check_health():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                request = urllib.request.Request('http://127.0.0.1:5273/backend/health', headers={'Authorization': auth})
                with urllib.request.urlopen(request, timeout=min(3, max(.01, deadline-time.monotonic()))) as response:
                    if json.load(response).get('status') == 'ok': return
            except (OSError, ValueError): pass
            time.sleep(min(1, max(0, deadline-time.monotonic())))
        raise RuntimeError('Updated application failed health checks')
    timer_was_active = state('guitarscribe-backup.timer') == 'active'
    try:
        if timer_was_active: run('systemctl', 'stop', 'guitarscribe-backup.timer')
        safe_window()
        result = apply_staged(root, release, service, check_health, allow_retry_schema=args.allow_retry_schema)
        (release/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result))
    finally:
        if timer_was_active: run('systemctl', 'start', 'guitarscribe-backup.timer')


if __name__ == '__main__': main()
