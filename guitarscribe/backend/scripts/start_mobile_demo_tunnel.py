#!/usr/bin/env python3
"""Pinned, temporary mobile entrance to the existing invitation-protected server.

No account, credential rotation, progress writes, or changes to the old tunnel.
Only publish a URL after anonymous, authenticated, and audio Range checks pass.

Operator usage from the repository root:
  python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py start
  python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py status
  python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py stop

Start reuses the active verified unit; it never restarts the existing web/ngrok
services. Stop affects only guitarscribe-mobile-tunnel. After a reboot or failed
connection, stop/start creates a new temporary hostname: read mobile-deployment.json
again. Restart=no prevents a silent hostname change. Repeated status probes count
toward the existing invitation gate's failed-login limit (10/minute per address).
The invitation remains shared, not a per-user account or isolated progress store.

Official temporary-tunnel behavior and limits:
https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
Pinned checksum source:
https://github.com/cloudflare/cloudflared/releases/tag/2026.11.0
"""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

VERSION = '2026.11.0'
SHA256 = '51f7c68b57ed7269164075d7e789efce5b59355982f06392deeb037d982a51fd'
DOWNLOAD = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-linux-amd64'
UNIT = 'guitarscribe-mobile-tunnel.service'
ORIGIN = 'http://127.0.0.1:5273'
PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_JOB = '83a3643ab3814172a046cebf709f3413'


def ensure_binary(cache, fetch=urlopen):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('This pinned binary supports Linux amd64 only.')
    directory = Path(cache) / VERSION
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = directory / 'cloudflared'
    if binary.exists():
        if hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('Cached cloudflared checksum mismatch; not executed or replaced.')
        return binary
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
            temp = Path(stream.name)
            digest, size = hashlib.sha256(), 0
            with fetch(DOWNLOAD, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 100_000_000: raise RuntimeError('Unexpected cloudflared download size.')
                    digest.update(chunk); stream.write(chunk)
            stream.flush(); os.fsync(stream.fileno())
        if digest.hexdigest() != SHA256:
            raise RuntimeError('Downloaded cloudflared checksum mismatch; not installed.')
        temp.chmod(0o700); os.replace(temp, binary)
    finally:
        if temp is not None: temp.unlink(missing_ok=True)
    return binary


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Invitation credentials must never follow an origin redirect.
        raise HTTPError(newurl, code, 'Redirect refused', headers, fp)


class UnsafeGate(RuntimeError):
    pass


def request(url, authorization=None, byte_range=None):
    headers = {'Cache-Control': 'no-cache'}
    if authorization: headers['Authorization'] = authorization
    if byte_range: headers['Range'] = byte_range
    try:
        response = build_opener(NoRedirect()).open(Request(url, headers=headers), timeout=12)
    except HTTPError as error:
        response = error
    with response:
        return response.code, {k.lower(): v for k, v in response.headers.items()}, response.read(2_000_000)


def verify_access(base, credentials, job, fetch=request):
    authorization = 'Basic ' + base64.b64encode(
        f"{credentials['username']}:{credentials['password']}".encode()).decode()
    for path in ('/', '/backend/health'):
        code, headers, _ = fetch(base + path)
        if code == 200:
            raise UnsafeGate('Unauthenticated entrance is open; the new tunnel must stop.')
        if code != 401 or not headers.get('www-authenticate', '').lower().startswith('basic'):
            raise RuntimeError('Anonymous site/API request did not receive the existing Basic challenge.')
        if fetch(base + path, authorization)[0] != 200:
            raise RuntimeError('Existing invitation did not authenticate to site/API.')
    endpoint = base + '/backend/api/v1/jobs/' + quote(job, safe='') + '/song-structure'
    code, _, body = fetch(endpoint, authorization)
    try:
        data = json.loads(body)
        source = data['document']['source']
        valid = code == 200 and data['source_matches'] and all(
            re.fullmatch('[a-f0-9]{64}', source[key]) for key in ('fingerprint', 'audio_sha256'))
    except (ValueError, TypeError, KeyError): valid = False
    if not valid: raise RuntimeError('Demonstration source is unavailable or changed; no URL published.')
    audio_url = endpoint + '/audio?' + urlencode({k: source[k] for k in ('fingerprint', 'audio_sha256')})
    audio_code = fetch(audio_url, byte_range='bytes=0-1023')[0]
    if audio_code in (200, 206):
        raise UnsafeGate('Unauthenticated audio is open; the new tunnel must stop.')
    if audio_code != 401:
        raise RuntimeError('Audio was not protected by the invitation gate.')
    code, headers, body = fetch(audio_url, authorization, 'bytes=0-1023')
    if code != 206 or not re.fullmatch(r'bytes 0-1023/[0-9]+', headers.get('content-range', '')) or len(body) != 1024:
        raise RuntimeError('Authenticated audio Range check failed.')
    return dict(unauthenticated=401, authenticated=200, audio_range=206)


def quick_url(log):
    matches = re.findall(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?![a-zA-Z0-9.:-])', log)
    return matches[-1] if matches else None


def command(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if check and result.returncode:
        raise RuntimeError('Local tunnel service command failed; inspect its user journal.')
    return result


def active():
    return command('systemctl', '--user', 'is-active', '--quiet', UNIT, check=False).returncode == 0


def tunnel_url():
    invocation = command('systemctl', '--user', 'show', UNIT, '-p', 'InvocationID', '--value').stdout.strip()
    if not re.fullmatch('[a-f0-9]{32}', invocation): return None
    log = command('journalctl', '--user', f'_SYSTEMD_INVOCATION_ID={invocation}', '-n', '100', '--no-pager', '-o', 'cat').stdout
    return quick_url(log)


def publish(folder, data):
    folder = Path(folder)
    with tempfile.NamedTemporaryFile(mode='w', dir=folder, delete=False) as stream:
        temp = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, folder / 'mobile-deployment.json')
        finally: temp.unlink(missing_ok=True)


def start(folder, cache, job):
    # Validate existing protection before exposing the origin through a new URL.
    credentials = json.loads((folder / 'access.json').read_text())
    verify_access(ORIGIN, credentials, job)
    binary = ensure_binary(cache)
    started = False
    try:
        if active():
            running = command('systemctl', '--user', 'show', UNIT, '-p', 'ExecStart', '--value').stdout
            if str(binary) not in running or ORIGIN not in running:
                raise RuntimeError('Existing unit differs from this pinned origin; left untouched.')
        else:
            command('systemd-run', '--user', '--collect', '--unit=' + UNIT,
                    '--property=Restart=no', '--property=UMask=0077', '--property=NoNewPrivileges=yes',
                    str(binary), '--no-autoupdate', 'tunnel', '--config', '/dev/null',
                    '--url', ORIGIN, '--protocol', 'http2', '--metrics', '127.0.0.1:0')
            started = True
        deadline = time.monotonic() + 90
        url = None
        while time.monotonic() < deadline:
            if not active(): raise RuntimeError('Temporary tunnel stopped before becoming ready.')
            url = tunnel_url()
            if url:
                try:
                    checks = verify_access(url, credentials, job)
                    break
                except UnsafeGate: raise
                except (OSError, RuntimeError): pass
            time.sleep(2)
        else: raise RuntimeError('Temporary entrance did not pass access and audio checks in time.')
        data = dict(url=url, mode='owner-mobile-demo-existing-invitation', unit=UNIT, origin=ORIGIN,
                    version=VERSION, sha256=SHA256, job_id=job, checks=checks,
                    demo_url=url + '/?' + urlencode(dict(practice='demo', job=job)),
                    verified_at=datetime.now(timezone.utc).isoformat(),
                    data='existing-web-preview-work', hostname_lifetime='current-unit-invocation')
        publish(folder, data)
        return data
    except Exception:
        if started: command('systemctl', '--user', 'stop', UNIT, check=False)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('start', 'status', 'stop'), default='start')
    parser.add_argument('--output-dir', type=Path, default=PROJECT / 'output/web-preview')
    parser.add_argument('--cache-dir', type=Path, default=Path.home() / '.cache/guitarscribe-cloudflared')
    parser.add_argument('--job', default=DEFAULT_JOB)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / '.mobile-tunnel.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'stop':
            command('systemctl', '--user', 'stop', UNIT, check=False)
            if active(): raise RuntimeError('Mobile tunnel did not stop; deployment metadata retained.')
            publish(args.output_dir, dict(state='stopped', unit=UNIT))
            print('Mobile tunnel stopped; existing web and old tunnel unchanged.')
        elif args.action == 'status':
            if not active(): raise RuntimeError('Mobile tunnel is not running.')
            data = json.loads((args.output_dir / 'mobile-deployment.json').read_text())
            if data.get('url') != tunnel_url(): raise RuntimeError('Published URL differs from the current tunnel invocation.')
            credentials = json.loads((args.output_dir / 'access.json').read_text())
            verify_access(data['url'], credentials, args.job)
            print(json.dumps(data, ensure_ascii=False))
        else:
            print(json.dumps(start(args.output_dir, args.cache_dir, args.job), ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # HTTP errors and subprocess output never echo request headers or secrets.
        print(str(error) if isinstance(error, RuntimeError) else f'Mobile tunnel failed ({type(error).__name__}); credentials were not printed.')
        raise SystemExit(1)
