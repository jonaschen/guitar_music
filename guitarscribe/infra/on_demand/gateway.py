"""Private on-demand gateway. No audio analysis or local application state lives here.

The ledger is external and uses generation CAS. A reservation is durable *before*
the one start RPC; ambiguous starts are never automatically replayed/refunded.
Only Compute's TERMINATED state and correlated start/stop timestamps settle a run.
Deploy with h2c (--use-http2), min instances 0, and a dedicated service account.
The VM must have automaticRestart=false, maxRunDuration<=7200 and STOP action.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from collections import OrderedDict, deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import html
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from typing import Callable
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from starlette.requests import ClientDisconnect, Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse

WINDOW_SECONDS = 31 * 86400
LIMIT_SECONDS = 40 * 3600
RESERVE_SECONDS = 9000
MAX_RUN_SECONDS = 7200
MAX_BODY_BYTES = 100 * 1024 * 1024
MAX_LEDGER_BYTES = 1024 * 1024


class ControlError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


class LedgerConflict(Exception):
    pass


class BodyTooLarge(Exception):
    pass


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Timestamp needs a timezone')
        value = parsed.timestamp()
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid timestamp')
    return float(value)


@dataclass(frozen=True)
class Instance:
    identity: str
    status: str
    started_at: float | None
    stopped_at: float | None
    max_run_seconds: int
    stop_action: str
    automatic_restart: bool
    internal_ip: str
    termination_at: float | None = None


class GCSLedger:
    """Read/write one small private object, never SQLite or a mounted filesystem."""
    def __init__(self, bucket, object_name):
        self.bucket = bucket
        self.object_name = object_name

    def read(self):
        from google.api_core.exceptions import NotFound, PreconditionFailed
        blob = self.bucket.blob(self.object_name)
        try:
            blob.reload(timeout=15)
        except NotFound:
            return None, 0
        if blob.size is None or blob.size > MAX_LEDGER_BYTES:
            raise ControlError('用量紀錄需要檢查，暫不啟動。')
        generation = int(blob.generation)
        try:
            raw = blob.download_as_bytes(if_generation_match=generation, timeout=15)
        except (NotFound, PreconditionFailed) as error:
            raise LedgerConflict() from error
        return json.loads(raw), generation

    def compare_and_swap(self, generation, document):
        from google.api_core.exceptions import PreconditionFailed
        raw = json.dumps(document, separators=(',', ':'), allow_nan=False)
        if len(raw.encode()) > MAX_LEDGER_BYTES:
            raise ControlError('用量紀錄需要整理，暫不啟動。')
        try:
            self.bucket.blob(self.object_name).upload_from_string(
                raw, content_type='application/json', if_generation_match=generation,
                timeout=15, retry=None)
        except PreconditionFailed as error:
            raise LedgerConflict() from error


class GoogleCompute:
    """One fixed instance. POST retries are deliberately disabled."""
    def __init__(self, project, zone, name, session_factory):
        if not all(re.fullmatch(r'[a-zA-Z0-9_-]+', v) for v in (project, zone, name)):
            raise ValueError('Invalid Compute resource')
        self.resource = f'projects/{project}/zones/{zone}/instances/{name}'
        self.url = 'https://compute.googleapis.com/compute/v1/' + self.resource
        self.session_factory = session_factory

    def describe(self):
        with self.session_factory() as session:
            response = session.get(self.url, timeout=20)
            response.raise_for_status()
            data = response.json()
        scheduling = data.get('scheduling', {})
        duration = scheduling.get('maxRunDuration', {})
        return Instance(
            identity=str(data['id']), status=data['status'],
            started_at=timestamp(data.get('lastStartTimestamp')),
            stopped_at=timestamp(data.get('lastStopTimestamp')),
            max_run_seconds=int(duration.get('seconds', 0)),
            stop_action=scheduling.get('instanceTerminationAction', ''),
            automatic_restart=scheduling.get('automaticRestart', True),
            internal_ip=data['networkInterfaces'][0]['networkIP'],
            termination_at=timestamp(data.get('resourceStatus', {}).get('scheduling', {}).get('terminationTimestamp')),
        )

    def start(self, request_id):
        with self.session_factory() as session:
            response = session.post(self.url + '/start', params={'requestId': request_id},
                                    json={}, timeout=20)
            response.raise_for_status()
        # The operation is asynchronous. Subsequent describe calls establish state.


class Controller:
    def __init__(self, ledger, compute, *, resource: str, internal_ip: str,
                 clock: Callable[[], float] = time.time):
        self.ledger = ledger
        self.compute = compute
        self.resource = resource
        self.internal_ip = internal_ip
        self.clock = clock

    def _safe_instance(self, instance):
        if (not instance.identity or instance.internal_ip != self.internal_ip
                or not 30 <= instance.max_run_seconds <= MAX_RUN_SECONDS
                or instance.stop_action != 'STOP' or instance.automatic_restart):
            raise ControlError('主機的自動停機設定需要檢查，暫不啟動。')

    def _validate(self, document, instance):
        if document is None:
            if instance.status != 'TERMINATED':
                raise ControlError('主機尚未納入用量管理，請先完成設定。')
            return dict(schema_version=1, resource=self.resource,
                        instance_id=instance.identity, accounted_start=instance.started_at, entries=[])
        try:
            if (document['schema_version'] != 1 or document['resource'] != self.resource
                    or document['instance_id'] != instance.identity):
                raise ValueError()
            timestamp(document['accounted_start'])
            entries = document['entries']
            if not isinstance(entries, list) or len(entries) > 5000:
                raise ValueError()
            ids = set()
            for row in entries:
                if row['id'] in ids or not re.fullmatch(r'[0-9a-f-]{36}', row['id']):
                    raise ValueError()
                ids.add(row['id'])
                timestamp(row['reserved_at'])
                if row['reserved_seconds'] != RESERVE_SECONDS:
                    raise ValueError()
                if row['state'] not in ('reserved', 'observed', 'settled'):
                    raise ValueError()
                if row['state'] == 'settled':
                    if timestamp(row['stopped_at']) < row['reserved_at']:
                        raise ValueError()
                    if type(row['charged_seconds']) is not int or row['charged_seconds'] < 60:
                        raise ValueError()
                if row.get('started_at') is not None:
                    timestamp(row['started_at'])
            if sum(row['state'] != 'settled' for row in entries) > 1:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ControlError('用量紀錄不完整，暫不啟動。') from None
        return deepcopy(document)

    def _reconcile(self, document, instance, now):
        active = next((r for r in document['entries'] if r['state'] != 'settled'), None)
        if active:
            start, stop = instance.started_at, instance.stopped_at
            # No old STOP timestamp can settle a newly reserved start. A changed
            # start after observing RUNNING means an out-of-band restart: fail closed.
            # Independent Google clocks can differ by a few seconds. A different
            # lastStartTimestamp is also required, so this tolerance can never
            # turn the previous run's STOP into a refund for the new reservation.
            correlated = (start is not None and active['reserved_at'] - 5 <= start <= now + 5
                          and start != document['accounted_start']
                          and (active.get('started_at') is None or active['started_at'] == start))
            if correlated and instance.status == 'RUNNING':
                active.update(state='observed', started_at=start)
            elif (correlated and instance.status == 'TERMINATED' and stop is not None
                  and max(start, active['reserved_at']) <= stop <= now + 5):
                # Charge boot/wait time too, with at least the VM's minimum billing
                # minute and a 60 s margin. Refund only after confirmed termination.
                charged = max(60, math.ceil(stop - active['reserved_at']) + 60)
                active.update(state='settled', started_at=start, stopped_at=stop,
                              charged_seconds=charged)
                document['accounted_start'] = start
                active = None
        # Retain the entire charge for any run touching the rolling window.
        # Unknown reservations never age out and never free the start lock.
        document['entries'] = [r for r in document['entries']
                               if r['state'] != 'settled' or r['stopped_at'] > now - WINDOW_SECONDS]
        return active

    def _view(self, document, instance, now):
        active = next((r for r in document['entries'] if r['state'] != 'settled'), None)
        used = sum(r['charged_seconds'] if r['state'] == 'settled' else r['reserved_seconds']
                   for r in document['entries'])
        state = 'stopped'
        if active:
            if (instance.status == 'RUNNING' and active.get('started_at') == instance.started_at
                    and active['state'] == 'observed'):
                state = 'running'
            elif instance.status in ('PROVISIONING', 'STAGING'):
                state = 'starting'
            elif instance.status in ('STOPPING', 'PENDING_STOP'):
                state = 'stopping'
            else:
                state = 'checking'
        elif instance.status != 'TERMINATED' or instance.started_at != document['accounted_start']:
            state = 'unmanaged'
        stop_at = None
        if state == 'running':
            stop_at = active['started_at'] + instance.max_run_seconds
            if instance.termination_at is not None:
                stop_at = min(stop_at, instance.termination_at)
        return dict(state=state, used_seconds=used, limit_seconds=LIMIT_SECONDS,
                    remaining_seconds=max(0, LIMIT_SECONDS - used), window_days=31,
                    can_wake=state == 'stopped' and used + RESERVE_SECONDS <= LIMIT_SECONDS,
                    stop_at=stop_at)

    def _update(self, wake):
        for _ in range(8):
            now = self.clock()
            instance = self.compute.describe()
            self._safe_instance(instance)
            try:
                old, generation = self.ledger.read()
                document = self._validate(old, instance)
                active = self._reconcile(document, instance, now)
                view = self._view(document, instance, now)
                start_id = None
                if wake and not active:
                    if instance.status != 'TERMINATED':
                        raise ControlError('主機正在切換狀態，請稍後查看。', 409)
                    if not view['can_wake']:
                        raise ControlError('近 31 天的可用時數不足，暫不啟動。', 429)
                    start_id = str(uuid4())
                    document['entries'].append(dict(id=start_id, reserved_at=now,
                        reserved_seconds=RESERVE_SECONDS, state='reserved', started_at=None))
                if document != old:
                    self.ledger.compare_and_swap(generation, document)
            except LedgerConflict:
                continue
            if start_id:
                # Only the CAS winner sends this request. A lost response leaves
                # the reservation intact; there is no transparent retry or refund.
                try:
                    self.compute.start(start_id)
                except Exception:
                    raise ControlError('啟動回應尚未確認，已保留用量；請稍後查看狀態。') from None
                view = self._view(document, instance, now)
                view['state'] = 'starting'
                view['can_wake'] = False
            return view
        raise ControlError('用量紀錄正忙碌，請稍後再試。')

    def status(self):
        return self._update(False)

    def wake(self):
        return self._update(True)


class RateLimiter:
    """Bounded, instance-local burst protection; the external ledger enforces cost."""
    def __init__(self, limit, seconds, clock=time.monotonic):
        self.limit, self.seconds, self.clock = limit, seconds, clock
        self.rows = OrderedDict()

    def allow(self, key):
        now = self.clock()
        row = self.rows.setdefault(key, deque())
        self.rows.move_to_end(key)
        while row and row[0] <= now - self.seconds:
            row.popleft()
        if len(self.rows) > 1024:
            self.rows.popitem(last=False)
        if len(row) >= self.limit:
            return False
        row.append(now)
        return True


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    public_origin: str
    backend_url: str
    max_body_bytes: int = MAX_BODY_BYTES
    max_streams: int = 8

    def __post_init__(self):
        origin, backend = urlsplit(self.public_origin), urlsplit(self.backend_url)
        if (not self.username or ':' in self.username or len(self.password) < 12
                or any(ord(c) < 32 for c in self.username + self.password)):
            raise ValueError('Invalid private gateway credentials')
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path not in ('', '/') or origin.query or origin.fragment
                or self.public_origin.endswith('/')):
            raise ValueError('PUBLIC_ORIGIN must be one HTTPS origin without trailing slash')
        if (backend.scheme != 'http' or not backend.hostname or backend.username or backend.password
                or backend.path not in ('', '/') or backend.query or backend.fragment):
            raise ValueError('BACKEND_URL must be a fixed HTTP origin')
        address = ipaddress.ip_address(backend.hostname)
        if address.version != 4 or not any(address in ipaddress.ip_network(n) for n in
                                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
            raise ValueError('BACKEND_URL must use an RFC1918 internal IPv4 address')
        if not 1 <= self.max_body_bytes <= MAX_BODY_BYTES or not 1 <= self.max_streams <= 16:
            raise ValueError('Invalid gateway resource bounds')


REQUEST_HEADERS = {b'accept', b'accept-encoding', b'accept-language', b'content-type',
                   b'content-length', b'range', b'if-range', b'if-none-match', b'if-modified-since'}
RESPONSE_HEADERS = {b'content-type', b'content-length', b'content-encoding', b'content-range',
                    b'accept-ranges', b'etag', b'last-modified', b'vary', b'location'}


class Gateway:
    def __init__(self, settings, controller, client=None, *, clock=time.time):
        self.settings, self.controller, self.clock = settings, controller, clock
        credential = f'{settings.username}:{settings.password}'.encode()
        self.expected_auth = hashlib.sha256(credential).digest()
        self.backend_auth = b'Basic ' + base64.b64encode(credential)
        self.csrf_key = hmac.digest(self.expected_auth, b'guitarscribe-cloud-csrf-v1', 'sha256')
        self.client = client
        self.owns_client = client is None
        self.failures = RateLimiter(10, 60)
        self.all_failures = RateLimiter(60, 60)
        self.wakes = RateLimiter(6, 60)
        self.controls = RateLimiter(90, 60)
        self.requests = RateLimiter(600, 60)
        self.streams = asyncio.Semaphore(settings.max_streams)
        self.status_lock = asyncio.Lock()
        self.status_cache = None
        self.status_cached_at = 0.

    def csrf_token(self):
        payload = f'{int(self.clock()) + 900}:{secrets.token_hex(16)}'.encode()
        signature = hmac.digest(self.csrf_key, payload + self.settings.public_origin.encode(), 'sha256').hex()
        return payload.decode() + ':' + signature

    def valid_csrf(self, value):
        try:
            expiry, nonce, signature = value.split(':')
            if len(value) > 200 or not re.fullmatch(r'[0-9a-f]{32}', nonce):
                return False
            if not self.clock() <= int(expiry) <= self.clock() + 900:
                return False
            expected = hmac.digest(self.csrf_key, f'{expiry}:{nonce}'.encode()
                                   + self.settings.public_origin.encode(), 'sha256').hex()
            return hmac.compare_digest(expected, signature)
        except (ValueError, TypeError):
            return False

    def _authenticated(self, headers):
        try:
            scheme, encoded = headers.get(b'authorization', b'').split(b' ', 1)
            if scheme.lower() != b'basic' or len(encoded) > 4096:
                return False
            credential = base64.b64decode(encoded, validate=True)
            return hmac.compare_digest(hashlib.sha256(credential).digest(), self.expected_auth)
        except (ValueError, binascii.Error):
            return False

    async def _status(self, fresh=False):
        async with self.status_lock:
            if not fresh and self.status_cache is not None and time.monotonic() - self.status_cached_at < 3:
                return self.status_cache
            view = await asyncio.to_thread(self.controller.status)
            self.status_cache, self.status_cached_at = view, time.monotonic()
            return view

    async def _ready_status(self):
        view = dict(await self._status())
        if view['state'] == 'running':
            ready = False
            try:
                if self.client is not None:
                    async with self.client.stream('GET', self.settings.backend_url.rstrip('/') + '/backend/health',
                            headers={'Authorization': self.backend_auth.decode()}, follow_redirects=False,
                            timeout=httpx.Timeout(5, connect=3)) as response:
                        ready = response.status_code == 200
            except httpx.HTTPError:
                pass
            if not ready:
                view['state'] = 'preparing'
        return view

    def _page(self, status=200, message=''):
        nonce = secrets.token_urlsafe(24)
        token = json.dumps(self.csrf_token())
        body = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GuitarScribe 私人工作室</title>
<style nonce="NONCE">body{margin:0;background:#f5f2eb;color:#252b29;font:18px/1.6 system-ui,sans-serif}
main{max-width:36rem;margin:12vh auto;padding:2rem}h1{font-size:1.7rem}button,a{font:inherit}
button{background:#244c43;color:white;border:0;border-radius:.5rem;padding:.7rem 1.2rem;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}a{color:#244c43}p{overflow-wrap:anywhere}</style>
<main><p>GuitarScribe · 私人工作室</p><h1>繼續聽歌與整理想法</h1>
<p id="state" role="status">MESSAGE</p><p id="quota"></p>
<button id="wake" disabled>啟動工作室</button> <a id="open" href="/" hidden>進入原本介面</a>
<p>每次最多使用兩小時，閒置時會提早休息。啟動後請稍候；離開前記得保存工作稿。</p>
<p><a href="/cloud">重新整理狀態</a></p></main><script nonce="NONCE">
const csrf=TOKEN, button=document.querySelector('#wake'), label=document.querySelector('#state');
let polling=false,remainingPolls=24;
async function refresh(){if(polling)return;polling=true;try{
 const r=await fetch('/cloud/status',{cache:'no-store'}),s=await r.json();
 if(!r.ok)throw Error(s.detail||'暫時無法確認狀態，請稍後再試。');
 const names={stopped:'工作室正在休息。',starting:'工作室啟動中，請稍候。',preparing:'正在準備原本介面，請稍候。',running:'工作室已就緒。',
 stopping:'工作室正在保存並停止。',checking:'啟動結果仍在確認中，請稍後查看；不會重複啟動。',
 unmanaged:'主機狀態需要確認，暫不啟動。'};
 label.textContent=names[s.state]||'正在確認狀態。';
 document.querySelector('#quota').textContent='近31天已使用或預留 '+(s.used_seconds/3600).toFixed(1)+' / 40 小時';
 button.disabled=!s.can_wake;document.querySelector('#open').hidden=s.state!=='running';
 if(['starting','preparing','checking','stopping'].includes(s.state)&&remainingPolls-->0)setTimeout(refresh,5000);
 }catch(e){label.textContent=e.message;button.disabled=true;}finally{polling=false;}}
button.addEventListener('click',async()=>{button.disabled=true;remainingPolls=24;label.textContent='正在啟動…';try{
 const r=await fetch('/cloud/wake',{method:'POST',headers:{'X-CSRF-Token':csrf}}),s=await r.json();
 if(!r.ok)throw Error(s.detail||'啟動未確認，請查看狀態。');await refresh();
 }catch(e){label.textContent=e.message;setTimeout(refresh,5000);}});refresh();
</script></html>'''.replace('NONCE', nonce).replace('TOKEN', token).replace('MESSAGE', html.escape(message or '正在確認工作室狀態…'))
        return HTMLResponse(body, status_code=status, headers={
            'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        })

    def _unavailable(self, scope, message):
        headers = dict(scope['headers'])
        if scope['method'] == 'GET' and scope['path'] in ('/', '/index.html') and b'text/html' in headers.get(b'accept', b''):
            return self._page(503, message)
        return JSONResponse({'detail': message, 'start_url': '/cloud'}, status_code=503,
                            headers={'Retry-After': '5'})

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    if self.client is None:
                        self.client = httpx.AsyncClient(follow_redirects=False,
                            transport=httpx.AsyncHTTPTransport(retries=0),
                            timeout=httpx.Timeout(120, connect=5, pool=5),
                            limits=httpx.Limits(max_connections=self.settings.max_streams))
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    if self.owns_client and self.client:
                        await self.client.aclose()
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        if scope['type'] != 'http':
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            return

        async def safe_send(message):
            if message['type'] == 'http.response.start':
                protected = {b'cache-control', b'x-content-type-options', b'x-frame-options', b'referrer-policy'}
                message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() not in protected]
                message['headers'] += [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                                       (b'x-frame-options', b'DENY'), (b'referrer-policy', b'no-referrer')]
            await send(message)

        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('latin1').lower()
        if host != urlsplit(self.settings.public_origin).netloc.lower():
            return await PlainTextResponse('Unknown host', 400)(scope, receive, safe_send)
        if not self._authenticated(headers):
            key = (scope.get('client') or ('unknown',))[0]
            allowed = self.failures.allow(key) and self.all_failures.allow('all')
            response = PlainTextResponse('請輸入私人工作室帳號與密碼。', 401 if allowed else 429,
                headers={'WWW-Authenticate': 'Basic realm="GuitarScribe private", charset="UTF-8"', 'Retry-After': '60'})
            return await response(scope, receive, safe_send)
        if not self.requests.allow('owner'):
            return await JSONResponse({'detail': '請稍候再試。'}, 429, headers={'Retry-After': '60'})(scope, receive, safe_send)
        method, path = scope['method'], scope['path']
        if method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            return await PlainTextResponse('Method not allowed', 405)(scope, receive, safe_send)
        # Basic credentials are ambient browser credentials, so protect *all*
        # writes against cross-origin forms, not just the wake endpoint.
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            if (headers.get(b'origin', b'').decode('latin1') != self.settings.public_origin
                    or headers.get(b'sec-fetch-site', b'same-origin') != b'same-origin'):
                return await PlainTextResponse('Origin rejected', 403)(scope, receive, safe_send)
        try:
            lengths = [v for k, v in scope['headers'] if k.lower() == b'content-length']
            if len(lengths) > 1 or lengths and not re.fullmatch(rb'[0-9]+', lengths[0]):
                raise ValueError()
            if lengths and int(lengths[0]) > self.settings.max_body_bytes:
                return await PlainTextResponse('錄音上傳上限為 100 MiB。', 413)(scope, receive, safe_send)
        except ValueError:
            return await PlainTextResponse('Invalid content length', 400)(scope, receive, safe_send)

        try:
            if path == '/cloud' and method == 'GET':
                return await self._page()(scope, receive, safe_send)
            if path == '/cloud/status' and method == 'GET':
                if not self.controls.allow('owner'):
                    raise ControlError('請稍候再查看。', 429)
                return await JSONResponse(await self._ready_status())(scope, receive, safe_send)
            if path == '/cloud/wake' and method == 'POST':
                if not self.valid_csrf(headers.get(b'x-csrf-token', b'').decode('latin1')):
                    raise ControlError('啟動頁已過期，請重新整理後再試。', 403)
                if not self.wakes.allow('owner'):
                    raise ControlError('請稍候再試。', 429)
                self.status_cache = None
                view = await asyncio.to_thread(self.controller.wake)
                self.status_cache = None
                return await JSONResponse(view, 202)(scope, receive, safe_send)
            if path == '/cloud' or path.startswith('/cloud/'):
                return await PlainTextResponse('Not found', 404)(scope, receive, safe_send)
            state = await self._status()
            if state['state'] != 'running':
                return await self._unavailable(scope, '工作室尚未就緒，請從啟動頁開啟。')(scope, receive, safe_send)
        except ControlError as error:
            return await JSONResponse({'detail': str(error)}, error.status)(scope, receive, safe_send)
        except Exception:
            return await JSONResponse({'detail': '暫時無法確認用量與主機狀態，請稍後再試。'}, 503)(scope, receive, safe_send)
        if self.streams.locked():
            return await JSONResponse({'detail': '連線忙碌，請稍後再試。'}, 429, headers={'Retry-After': '5'})(scope, receive, safe_send)
        async with self.streams:
            await self._proxy(scope, receive, safe_send, stop_at=state.get('stop_at'))

    async def _proxy(self, scope, receive, send, *, stop_at=None):
        request = Request(scope, receive)
        body_done = asyncio.Event()
        response_started = False
        upstream = None

        async def body():
            total = 0
            try:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > self.settings.max_body_bytes:
                        raise BodyTooLarge()
                    yield chunk
            finally:
                body_done.set()

        async def forward():
            nonlocal response_started, upstream
            try:
                raw_path = scope.get('raw_path', scope['path'].encode())
                if not raw_path.startswith(b'/') or raw_path.startswith(b'//') or b'?' in raw_path:
                    return await PlainTextResponse('Invalid path', 400)(scope, receive, send)
                query = scope.get('query_string', b'')
                url = httpx.URL(self.settings.backend_url).copy_with(raw_path=raw_path + (b'?' + query if query else b''))
                connection_tokens = set()
                for k, v in scope['headers']:
                    if k.lower() == b'connection':
                        connection_tokens.update(x.strip().lower() for x in v.split(b','))
                headers = [(k, v) for k, v in scope['headers'] if k.lower() in REQUEST_HEADERS and k.lower() not in connection_tokens]
                headers.append((b'authorization', self.backend_auth))
                if scope['method'] == 'POST' and scope['path'] == '/backend/cloud/activity':
                    activity = [v for k, v in scope['headers'] if k.lower() == b'x-guitarscribe-activity']
                    if activity == [b'visible']:
                        headers.append((b'x-guitarscribe-activity', b'visible'))
                # Never relay a caller's claimed deadline. A missing/invalid
                # controller deadline is omitted so the host can reject new
                # inference while allowing existing songs to be viewed.
                if type(stop_at) in (int, float) and math.isfinite(stop_at) and stop_at > 0:
                    headers.append((b'x-guitarscribe-stop-at', f'{stop_at:.6f}'.encode('ascii')))
                content = body()
                assert self.client is not None, 'Gateway lifespan has not started'
                outgoing = self.client.build_request(scope['method'], url, headers=headers, content=content)
                upstream = await self.client.send(outgoing, stream=True, follow_redirects=False)
                output_headers = []
                for key, value in upstream.headers.raw:
                    if key.lower() not in RESPONSE_HEADERS:
                        continue
                    if key.lower() == b'location':
                        location = value.decode('latin1')
                        if location.startswith(self.settings.backend_url.rstrip('/') + '/'):
                            value = (self.settings.public_origin + location[len(self.settings.backend_url.rstrip('/')):]).encode('latin1')
                        elif not location.startswith('/') or location.startswith('//'):
                            raise ControlError('後端回傳了不支援的重新導向。', 502)
                    output_headers.append((key, value))
                await send({'type': 'http.response.start', 'status': upstream.status_code, 'headers': output_headers})
                response_started = True
                if scope['method'] != 'HEAD':
                    async for chunk in upstream.aiter_raw():
                        await send({'type': 'http.response.body', 'body': chunk, 'more_body': True})
                await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
            except ClientDisconnect:
                return
            except BodyTooLarge:
                if not response_started:
                    await PlainTextResponse('錄音上傳上限為 100 MiB。', 413)(scope, receive, send)
            except (httpx.HTTPError, ControlError):
                if response_started:
                    # Do not turn a truncated upstream audio stream into a valid
                    # shorter response. The server closes the response/connection.
                    raise RuntimeError('Upstream stream interrupted') from None
                await self._unavailable(scope, '工作室連線尚未就緒，請稍後再試；操作未自動重送。')(scope, receive, send)
            finally:
                body_done.set()
                if upstream is not None:
                    await upstream.aclose()

        async def disconnected():
            await body_done.wait()
            while True:
                if (await receive())['type'] == 'http.disconnect':
                    return

        forward_task = asyncio.create_task(forward())
        disconnect_task = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait((forward_task, disconnect_task), return_when=asyncio.FIRST_COMPLETED)
            if forward_task in done:
                await forward_task
        finally:
            for task in (forward_task, disconnect_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(forward_task, disconnect_task, return_exceptions=True)


def create_app():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    from google.cloud import storage

    credentials = json.loads(Path(os.environ['GUITARSCRIBE_WEB_ACCESS_FILE']).read_text())
    settings = Settings(username=credentials['username'], password=credentials['password'],
        public_origin=os.environ['GUITARSCRIBE_CLOUD_PUBLIC_ORIGIN'],
        backend_url=os.environ['GUITARSCRIBE_CLOUD_BACKEND_URL'])
    auth, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    project = os.environ.get('GUITARSCRIBE_CLOUD_PROJECT', project)
    compute = GoogleCompute(project, os.environ['GUITARSCRIBE_CLOUD_ZONE'],
                            os.environ['GUITARSCRIBE_CLOUD_INSTANCE'], lambda: AuthorizedSession(auth))
    ledger = GCSLedger(storage.Client(project=project, credentials=auth).bucket(os.environ['GUITARSCRIBE_CLOUD_LEDGER_BUCKET']),
                       os.environ.get('GUITARSCRIBE_CLOUD_LEDGER_OBJECT', 'on-demand/ledger.json'))
    controller = Controller(ledger, compute, resource=compute.resource,
                            internal_ip=urlsplit(settings.backend_url).hostname)
    return Gateway(settings, controller)
