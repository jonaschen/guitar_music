import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location('mobile_tunnel', Path(__file__).resolve().parents[1] / 'scripts/start_mobile_demo_tunnel.py')
tunnel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tunnel)


def test_download_checks_pinned_digest_before_executing_and_reuses_verified_binary(tmp_path, monkeypatch):
    payload = b'official binary fixture'
    monkeypatch.setattr(tunnel, 'SHA256', hashlib.sha256(payload).hexdigest())
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return io.BytesIO(payload)
    binary = tunnel.ensure_binary(tmp_path, fetch)
    assert binary.read_bytes() == payload and binary.stat().st_mode & 0o111
    assert tunnel.ensure_binary(tmp_path, fetch) == binary and len(calls) == 1
    binary.write_bytes(b'tampered')
    with pytest.raises(RuntimeError, match='checksum'): tunnel.ensure_binary(tmp_path, fetch)
    assert len(calls) == 1


def test_bad_download_is_not_installed(tmp_path):
    with pytest.raises(RuntimeError, match='checksum'):
        tunnel.ensure_binary(tmp_path, lambda *a, **k: io.BytesIO(b'bad bytes'))
    assert not (tmp_path / tunnel.VERSION / 'cloudflared').exists()


def test_redirects_never_forward_invitation_credentials():
    with pytest.raises(HTTPError):
        tunnel.NoRedirect().redirect_request(None, None, 302, 'found', {}, 'https://elsewhere.example/')


def test_access_probe_checks_site_api_source_and_authenticated_audio_range_without_writes():
    calls = []
    credentials = dict(username='fixture', password='never-print-me')
    def request(url, authorization=None, byte_range=None):
        calls.append((url, authorization, byte_range))
        if authorization is None: return 401, {'www-authenticate': 'Basic realm="fixture"'}, b''
        if '/song-structure/audio?' in url:
            return 206, {'content-range': 'bytes 0-1023/9876'}, b'x' * 1024
        if url.endswith('/song-structure'):
            return 200, {}, json.dumps(dict(source_matches=True, document=dict(source=dict(
                fingerprint='a' * 64, audio_sha256='b' * 64)))).encode()
        return 200, {}, b'{}'
    result = tunnel.verify_access('https://fixture.trycloudflare.com', credentials, 'song', request)
    assert result == dict(unauthenticated=401, authenticated=200, audio_range=206)
    assert any(c[2] == 'bytes=0-1023' for c in calls)
    assert all('never-print-me' not in c[0] for c in calls)


@pytest.mark.parametrize('fault', ['open_gate', 'bad_login', 'redirect', 'source', 'range'])
def test_invalid_access_or_source_never_counts_as_verified(fault):
    def request(url, authorization=None, byte_range=None):
        if fault == 'redirect': return 302, {}, b''
        if authorization is None: return (200 if fault == 'open_gate' else 401), {'www-authenticate': 'Basic'}, b''
        if fault == 'bad_login': return 401, {}, b''
        if '/song-structure/audio?' in url: return 200, {}, b'audio'
        if url.endswith('/song-structure'):
            return 200, {}, json.dumps(dict(source_matches=fault != 'source', document=dict(source=dict(
                fingerprint='a' * 64, audio_sha256='b' * 64)))).encode()
        return 200, {}, b''
    with pytest.raises(RuntimeError): tunnel.verify_access('https://fixture.trycloudflare.com', dict(username='u', password='secret'), 'song', request)


def test_only_quick_tunnel_https_host_is_accepted():
    assert tunnel.quick_url('INF Visit https://a-b-c.trycloudflare.com to try') == 'https://a-b-c.trycloudflare.com'
    for text in ('http://bad.trycloudflare.com', 'https://bad.trycloudflare.com.evil.test', 'https://elsewhere.test'):
        assert tunnel.quick_url(text) is None


def test_atomic_publication_keeps_old_deployment_and_omits_credentials(tmp_path):
    old = tmp_path / 'deployment.json'; old.write_text('original')
    data = dict(url='https://demo.trycloudflare.com', checks=dict(audio_range=206))
    tunnel.publish(tmp_path, data)
    assert old.read_text() == 'original'
    assert json.loads((tmp_path / 'mobile-deployment.json').read_text()) == data


def test_local_gate_failure_never_downloads_or_starts_tunnel(tmp_path, monkeypatch):
    (tmp_path / 'access.json').write_text(json.dumps(dict(username='fixture', password='private')))
    monkeypatch.setattr(tunnel, 'verify_access', lambda *args: (_ for _ in ()).throw(tunnel.UnsafeGate('open')))
    monkeypatch.setattr(tunnel, 'ensure_binary', lambda *args: pytest.fail('download before checking gate'))
    monkeypatch.setattr(tunnel, 'command', lambda *args: pytest.fail('unit changed before checking gate'))
    with pytest.raises(tunnel.UnsafeGate): tunnel.start(tmp_path, tmp_path, 'song')


def test_new_unit_failure_stops_only_new_tunnel_and_never_publishes(tmp_path, monkeypatch):
    (tmp_path / 'access.json').write_text(json.dumps(dict(username='fixture', password='private')))
    old = tmp_path / 'deployment.json'; old.write_text('old entrance')
    calls = []
    def verify(base, *args):
        if base != tunnel.ORIGIN: raise tunnel.UnsafeGate('open')
    states = iter([False, True])
    monkeypatch.setattr(tunnel, 'verify_access', verify)
    monkeypatch.setattr(tunnel, 'ensure_binary', lambda *args: tmp_path / 'binary')
    monkeypatch.setattr(tunnel, 'active', lambda: next(states))
    monkeypatch.setattr(tunnel, 'tunnel_url', lambda: 'https://fixture.trycloudflare.com')
    monkeypatch.setattr(tunnel, 'command', lambda *args, **kwargs: calls.append(args))
    with pytest.raises(tunnel.UnsafeGate): tunnel.start(tmp_path, tmp_path, 'song')
    assert calls[0][0] == 'systemd-run'
    assert calls[-1] == ('systemctl', '--user', 'stop', tunnel.UNIT)
    assert 'ngrok' not in str(calls) and 'friends-tunnel' not in str(calls)
    assert old.read_text() == 'old entrance' and not (tmp_path / 'mobile-deployment.json').exists()


def test_verified_existing_unit_is_reused_without_restart(tmp_path, monkeypatch):
    (tmp_path / 'access.json').write_text(json.dumps(dict(username='fixture', password='private')))
    binary = tmp_path / 'binary'; calls = []
    monkeypatch.setattr(tunnel, 'verify_access', lambda *args: dict(unauthenticated=401, authenticated=200, audio_range=206))
    monkeypatch.setattr(tunnel, 'ensure_binary', lambda *args: binary)
    monkeypatch.setattr(tunnel, 'active', lambda: True)
    monkeypatch.setattr(tunnel, 'tunnel_url', lambda: 'https://fixture.trycloudflare.com')
    def command(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=f'{binary} tunnel --url {tunnel.ORIGIN}')
    monkeypatch.setattr(tunnel, 'command', command)
    result = tunnel.start(tmp_path, tmp_path, 'song')
    assert len(calls) == 1 and calls[0][2] == 'show'
    assert result['checks']['audio_range'] == 206
    assert 'private' not in (tmp_path / 'mobile-deployment.json').read_text()


def test_unrecognized_existing_unit_is_left_untouched(tmp_path, monkeypatch):
    (tmp_path / 'access.json').write_text(json.dumps(dict(username='fixture', password='private')))
    calls = []
    monkeypatch.setattr(tunnel, 'verify_access', lambda *args: None)
    monkeypatch.setattr(tunnel, 'ensure_binary', lambda *args: tmp_path / 'binary')
    monkeypatch.setattr(tunnel, 'active', lambda: True)
    def command(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='different operator configuration')
    monkeypatch.setattr(tunnel, 'command', command)
    with pytest.raises(RuntimeError, match='left untouched'): tunnel.start(tmp_path, tmp_path, 'song')
    assert len(calls) == 1 and calls[0][2] == 'show'
    assert not (tmp_path / 'mobile-deployment.json').exists()
