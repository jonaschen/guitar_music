"""Offline failure/concurrency tests. Never accesses Google or the owner's data."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import re
import sys
from threading import Lock
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

spec = importlib.util.spec_from_file_location('on_demand_gateway', Path(__file__).with_name('gateway.py'))
gateway = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gateway
spec.loader.exec_module(gateway)


class FakeLedger:
    def __init__(self):
        self.document = None
        self.generation = 0
        self.lock = Lock()
        self.writes = 0
        self.fail_write = False

    def read(self):
        with self.lock:
            return deepcopy(self.document), self.generation

    def compare_and_swap(self, generation, document):
        with self.lock:
            if self.fail_write:
                raise OSError('storage unavailable')
            if generation != self.generation:
                raise gateway.LedgerConflict()
            self.document = deepcopy(document)
            self.generation += 1
            self.writes += 1


class FakeCompute:
    def __init__(self):
        self.instance = gateway.Instance('123', 'TERMINATED', None, None, 7200, 'STOP', False, '10.2.0.4')
        self.calls = []
        self.lose_response = False

    def describe(self):
        return self.instance

    def start(self, request_id):
        self.calls.append(request_id)
        self.instance = replace(self.instance, status='PROVISIONING')
        if self.lose_response:
            raise TimeoutError('response lost after start')


@pytest.fixture
def control():
    ledger, compute, clock = FakeLedger(), FakeCompute(), [10_000_000.]
    controller = gateway.Controller(ledger, compute, resource='projects/p/zones/z/instances/i',
                                    internal_ip='10.2.0.4', clock=lambda: clock[0])
    return SimpleNamespace(ledger=ledger, compute=compute, clock=clock, controller=controller)


def running(s):
    s.clock[0] += 5
    s.compute.instance = replace(s.compute.instance, status='RUNNING', started_at=s.clock[0])
    return s.controller.status()


def stopped(s, seconds=3600):
    s.clock[0] += seconds
    s.compute.instance = replace(s.compute.instance, status='TERMINATED', stopped_at=s.clock[0])
    return s.controller.status()


def test_no_start_until_durable_reservation(control):
    s = control
    assert s.controller.status()['can_wake']
    assert not s.compute.calls
    s.ledger.fail_write = True
    with pytest.raises(OSError):
        s.controller.wake()
    assert not s.compute.calls and not s.ledger.document['entries']


def test_one_cas_winner_across_independent_controller_instances(control):
    s = control
    def attempt(_):
        other = gateway.Controller(s.ledger, s.compute, resource=s.controller.resource,
                                   internal_ip='10.2.0.4', clock=lambda:s.clock[0])
        return other.wake()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(20)))
    assert len(s.compute.calls) == 1
    assert len(s.ledger.document['entries']) == 1
    entry = s.ledger.document['entries'][0]
    assert s.compute.calls == [entry['id']]
    assert all(r['used_seconds'] == 9000 for r in results)


def test_lost_start_response_does_not_replay_or_refund(control):
    s = control; s.compute.lose_response = True
    with pytest.raises(gateway.ControlError): s.controller.wake()
    for _ in range(3):
        assert s.controller.wake()['used_seconds'] == 9000
    assert len(s.compute.calls) == 1
    assert running(s)['state'] == 'running'
    assert stopped(s)['used_seconds'] == 3665


def test_old_stop_and_stopping_state_cannot_refund_new_reservation(control):
    s = control
    s.compute.instance = replace(s.compute.instance, started_at=s.clock[0]-1000, stopped_at=s.clock[0]-500)
    s.controller.wake()
    s.compute.instance = replace(s.compute.instance, status='TERMINATED')
    assert s.controller.status()['used_seconds'] == 9000
    assert s.controller.wake()['state'] == 'checking'
    assert len(s.compute.calls) == 1
    running(s)
    s.clock[0] += 100
    s.compute.instance = replace(s.compute.instance, status='STOPPING', stopped_at=s.clock[0])
    assert s.controller.status()['used_seconds'] == 9000
    s.compute.instance = replace(s.compute.instance, status='TERMINATED')
    assert s.controller.status()['used_seconds'] == 165


def test_never_observed_running_can_settle_only_correlated_platform_timestamps(control):
    s = control; s.controller.wake()
    start = s.clock[0]+10; s.clock[0] += 800
    s.compute.instance = replace(s.compute.instance, status='TERMINATED', started_at=start, stopped_at=s.clock[0])
    assert s.controller.status()['used_seconds'] == 860


def test_out_of_band_restart_blocks_refund_and_new_start(control):
    s = control; s.controller.wake(); running(s)
    s.clock[0] += 100
    s.compute.instance = replace(s.compute.instance, started_at=s.clock[0])
    assert s.controller.status()['state'] == 'checking'
    assert stopped(s)['used_seconds'] == 9000
    s.controller.wake()
    assert len(s.compute.calls) == 1


def test_out_of_band_run_after_settlement_is_not_silently_adopted(control):
    s = control; s.controller.wake(); running(s); stopped(s)
    s.clock[0] += 100
    s.compute.instance = replace(s.compute.instance, started_at=s.clock[0]-50, stopped_at=s.clock[0])
    assert s.controller.status()['state'] == 'unmanaged'
    with pytest.raises(gateway.ControlError): s.controller.wake()
    assert len(s.compute.calls) == 1


def test_unknown_start_never_ages_out_even_after_31_days(control):
    s = control; s.controller.wake()
    s.clock[0] += 40 * 86400
    s.compute.instance = replace(s.compute.instance, status='TERMINATED')
    assert s.controller.status()['used_seconds'] == 9000
    s.controller.wake()
    assert len(s.compute.calls) == 1


def test_small_clock_skew_accepts_new_start_but_never_reuses_old_run(control):
    s = control; s.controller.wake()
    s.compute.instance = replace(s.compute.instance, status='RUNNING', started_at=s.clock[0]-2)
    assert s.controller.status()['state'] == 'running'
    assert stopped(s)['used_seconds'] == 3660
    s.clock[0] += 1
    previous_start = s.compute.instance.started_at
    s.controller.wake()
    s.compute.instance = replace(s.compute.instance, status='TERMINATED', started_at=previous_start)
    assert s.controller.status()['used_seconds'] == 3660+9000
    assert s.controller.status()['state'] == 'checking'


def test_old_start_within_clock_tolerance_is_still_not_a_new_execution(control):
    s = control
    s.compute.instance = replace(s.compute.instance, started_at=s.clock[0]-3, stopped_at=s.clock[0]-1)
    s.controller.wake()
    s.compute.instance = replace(s.compute.instance, status='TERMINATED', stopped_at=s.clock[0]+1)
    s.clock[0] += 2
    assert s.controller.status()['used_seconds'] == 9000
    assert s.controller.status()['state'] == 'checking'


def test_platform_termination_timestamp_is_used_as_earlier_deadline(control):
    s = control; s.controller.wake(); running(s)
    predicted = s.compute.instance.started_at+7200
    s.compute.instance = replace(s.compute.instance, termination_at=predicted-6.6)
    assert s.controller.status()['stop_at'] == predicted-6.6
    s.compute.instance = replace(s.compute.instance, termination_at=predicted+10)
    assert s.controller.status()['stop_at'] == predicted


def test_rolling_window_counts_full_run_crossing_boundary_and_blocks_over_cap(control):
    s = control; s.controller.status()
    cutoff = s.clock[0] - gateway.WINDOW_SECONDS
    entries = [dict(id=str(uuid4()), reserved_at=cutoff-100, reserved_seconds=9000,
                    state='settled', stopped_at=cutoff+1, started_at=cutoff-99,
                    charged_seconds=9000) for _ in range(16)]
    s.ledger.document['entries'] = entries
    assert s.controller.status()['used_seconds'] == 40 * 3600
    with pytest.raises(gateway.ControlError) as error: s.controller.wake()
    assert error.value.status == 429 and not s.compute.calls
    s.clock[0] += 2
    assert s.controller.status()['used_seconds'] == 0
    assert s.controller.wake()['used_seconds'] == 9000


@pytest.mark.parametrize('change', [dict(max_run_seconds=0), dict(max_run_seconds=7201),
    dict(stop_action='DELETE'), dict(automatic_restart=True), dict(internal_ip='10.2.0.5')])
def test_platform_stop_configuration_must_be_safe(control, change):
    s = control; s.compute.instance = replace(s.compute.instance, **change)
    with pytest.raises(gateway.ControlError): s.controller.wake()
    assert not s.compute.calls and s.ledger.document is None


def test_recreated_instance_and_corrupt_ledger_are_rejected(control):
    s = control; s.controller.status()
    s.compute.instance = replace(s.compute.instance, identity='456')
    with pytest.raises(gateway.ControlError): s.controller.wake()
    s.compute.instance = replace(s.compute.instance, identity='123')
    s.ledger.document['entries'] = [{'garbage': True}]
    with pytest.raises(gateway.ControlError): s.controller.wake()
    assert not s.compute.calls


def test_failed_settlement_write_keeps_reservation(control):
    s = control; s.controller.wake(); running(s)
    s.ledger.fail_write = True
    with pytest.raises(OSError): stopped(s)
    assert s.ledger.document['entries'][0]['state'] == 'observed'
    assert s.ledger.document['entries'][0]['reserved_seconds'] == 9000


class FakeController:
    def __init__(self, state='stopped'):
        self.state = state; self.starts = 0; self.reads = 0
        self.stop_at = 1_800_000_000.

    def status(self):
        self.reads += 1
        return dict(state=self.state, used_seconds=0, limit_seconds=144000,
                    remaining_seconds=144000, can_wake=self.state == 'stopped', stop_at=self.stop_at)

    def wake(self):
        self.starts += 1; self.state = 'starting'
        return self.status()


@pytest.fixture
def web():
    settings = gateway.Settings('owner', 'a-long-private-test-password', 'https://music.test', 'http://10.2.0.4:5273')
    controller = FakeController()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(206, headers={'content-range':'bytes 0-3/8', 'accept-ranges':'bytes',
            'content-type':'audio/wav'}, stream=httpx.ByteStream(b'wave'))
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = gateway.Gateway(settings, controller, upstream)
    return SimpleNamespace(settings=settings, controller=controller, calls=calls, upstream=upstream, app=app)


def client(web, auth=True):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url='https://music.test',
        auth=(web.settings.username, web.settings.password) if auth else None)


@pytest.mark.asyncio
async def test_auth_precedes_all_vm_or_ledger_operations_and_limits_guessing(web):
    async with client(web, False) as c:
        for _ in range(10): assert (await c.get('/cloud/status')).status_code == 401
        assert (await c.get('/cloud/status')).status_code == 429
        assert (await c.post('/cloud/wake')).status_code == 429
    assert web.controller.reads == 0 and web.controller.starts == 0 and not web.calls


@pytest.mark.asyncio
async def test_stopped_get_and_writes_never_wake_and_return_page_or_json(web):
    async with client(web) as c:
        page = await c.get('/', headers={'Accept':'text/html'})
        assert page.status_code == 503 and '啟動工作室' in page.text
        response = await c.get('/backend/api/v1/jobs/song')
        assert response.status_code == 503 and response.json()['start_url'] == '/cloud'
        response = await c.put('/backend/api/v1/jobs/song/root-practice', json={}, headers={'Origin':'https://music.test'})
        assert response.status_code == 503
    assert web.controller.starts == 0 and not web.calls


@pytest.mark.asyncio
async def test_wake_requires_origin_and_signed_expiring_csrf(web):
    async with client(web) as c:
        page = await c.get('/cloud')
        assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
        assert 'frame-ancestors' in page.headers['content-security-policy']
        token = json.loads(re.search(r'const csrf=("[^"]+")', page.text).group(1))
        assert (await c.post('/cloud/wake')).status_code == 403
        assert (await c.post('/cloud/wake', headers={'Origin':'https://evil.test','X-CSRF-Token':token})).status_code == 403
        assert (await c.post('/cloud/wake', headers={'Origin':'https://music.test','X-CSRF-Token':token+'x'})).status_code == 403
        assert (await c.post('/cloud/wake', headers={'Origin':'https://music.test','X-CSRF-Token':token})).status_code == 202
    assert web.controller.starts == 1
    web.app.clock = lambda: 10**12
    assert not web.app.valid_csrf(token)


@pytest.mark.asyncio
async def test_wrong_host_and_cross_site_backend_writes_are_rejected(web):
    web.controller.state = 'running'
    async with client(web) as c:
        assert (await c.get('/cloud',headers={'Host':'evil.test'})).status_code == 400
        for origin in ('https://evil.test', 'null', ''):
            response = await c.post('/backend/api/v1/jobs', headers={'Origin':origin}, content=b'x')
            assert response.status_code == 403
    assert not web.calls and web.controller.reads == 0


@pytest.mark.asyncio
async def test_proxy_preserves_range_and_forwards_only_fixed_backend_credentials(web):
    web.controller.state = 'running'
    async with client(web) as c:
        response = await c.get('/backend/audio?x=1', headers={'Range':'bytes=0-3', 'X-Forwarded-Host':'evil.test',
            'X-Goog-IAP-JWT-Assertion':'forged', 'Cookie':'other=private', 'Forwarded':'host=evil.test'})
        assert response.status_code == 206 and response.content == b'wave'
        assert response.headers['content-range'] == 'bytes 0-3/8'
        assert response.headers['cache-control'] == 'no-store'
    assert len(web.calls) == 1
    call = web.calls[0]
    assert str(call.url) == 'http://10.2.0.4:5273/backend/audio?x=1'
    assert call.headers['range'] == 'bytes=0-3'
    assert call.headers['authorization'] == 'Basic '+base64.b64encode(b'owner:a-long-private-test-password').decode()
    assert not {'x-forwarded-host','x-goog-iap-jwt-assertion','cookie','forwarded'} & set(call.headers)


@pytest.mark.asyncio
async def test_proxy_sets_deadline_from_controller_and_strips_forged_caller_header(web):
    web.controller.state = 'running'
    async with client(web) as c:
        response = await c.post('/backend/api/v1/jobs', content=b'x', headers={
            'Origin':'https://music.test', 'X-GuitarScribe-Stop-At':'999999999999',
            'Connection':'X-GuitarScribe-Stop-At'})
        assert response.status_code == 206
    assert len(web.calls) == 1
    assert web.calls[0].headers.get_list('x-guitarscribe-stop-at') == ['1800000000.000000']


@pytest.mark.asyncio
@pytest.mark.parametrize('deadline', [None, float('nan'), float('inf'), -1, '99999999999', True])
async def test_missing_or_invalid_deadline_is_not_filled_from_caller(web, deadline):
    web.controller.state = 'running'; web.controller.stop_at = deadline
    async with client(web) as c:
        response = await c.get('/backend/saved-song', headers={'X-GuitarScribe-Stop-At':'99999999999'})
        assert response.status_code == 206
    assert 'x-guitarscribe-stop-at' not in web.calls[0].headers


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method,value,forwarded', [
    ('/backend/cloud/activity','POST','visible',True),
    ('/backend/cloud/activity','POST','hidden',False),
    ('/backend/cloud/activity','GET','visible',False),
    ('/backend/api/v1/jobs','POST','visible',False),
])
async def test_authenticated_visible_heartbeat_header_only_reaches_its_endpoint(web, path, method, value, forwarded):
    web.controller.state = 'running'
    async with client(web) as c:
        response = await c.request(method, path, headers={
            'Origin':'https://music.test','X-GuitarScribe-Activity':value})
        assert response.status_code == 206
    assert ('x-guitarscribe-activity' in web.calls[0].headers) == forwarded


@pytest.mark.asyncio
async def test_failed_backend_write_is_sent_exactly_once_and_not_replayed(web):
    web.controller.state = 'running'; attempts = []
    def failure(request):
        attempts.append(request)
        raise httpx.ReadTimeout('lost response after backend commit', request=request)
    web.app.client = httpx.AsyncClient(transport=httpx.MockTransport(failure))
    async with client(web) as c:
        response = await c.put('/backend/save', content=b'draft', headers={'Origin':'https://music.test'})
        assert response.status_code == 503 and '未自動重送' in response.json()['detail']
    assert len(attempts) == 1 and attempts[0].content == b'draft'


@pytest.mark.asyncio
async def test_body_length_is_checked_before_control_or_proxy(web):
    web.controller.state = 'running'
    async with client(web) as c:
        response = await c.post('/backend/upload', content=b'x', headers={
            'Origin':'https://music.test','Content-Length':str(gateway.MAX_BODY_BYTES+1)})
        assert response.status_code == 413
    assert not web.calls and web.controller.reads == 0


@pytest.mark.asyncio
async def test_chunked_upload_enforces_streamed_size_bound(web):
    web.controller.state = 'running'
    web.app.settings = replace(web.settings, max_body_bytes=8)
    async def chunks():
        yield b'12345'; yield b'67890'
    async with client(web) as c:
        response = await c.post('/backend/upload', content=chunks(), headers={'Origin':'https://music.test'})
        assert response.status_code == 413
    assert not web.calls


@pytest.mark.asyncio
async def test_redirect_is_not_followed_and_internal_origin_is_rewritten(web):
    web.controller.state = 'running'; calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(307, headers={'Location':'http://10.2.0.4:5273/next'}, stream=httpx.ByteStream(b''))
    web.app.client = httpx.AsyncClient(transport=httpx.MockTransport(redirect))
    async with client(web) as c:
        response = await c.get('/redirect')
        assert response.status_code == 307 and response.headers['location'] == 'https://music.test/next'
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_external_redirect_is_rejected_without_credentials_leak(web):
    web.controller.state = 'running'
    web.app.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(302, headers={'Location':'https://evil.test'}, stream=httpx.ByteStream(b''))))
    async with client(web) as c:
        response = await c.get('/redirect')
        assert response.status_code == 503 and 'location' not in response.headers


@pytest.mark.asyncio
async def test_disconnect_closes_upstream_stream_and_returns_capacity(web):
    web.controller.state = 'running'
    emitted, closed = asyncio.Event(), asyncio.Event()
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'first'
            await asyncio.Event().wait()
        async def aclose(self): closed.set()
    web.app.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, stream=Stream())))
    auth = b'Basic '+base64.b64encode(b'owner:a-long-private-test-password')
    scope = dict(type='http', asgi={'version':'3.0'}, method='GET', path='/audio', raw_path=b'/audio',
        query_string=b'', headers=[(b'host',b'music.test'),(b'authorization',auth)], client=('127.0.0.1',1))
    first = True
    async def receive():
        nonlocal first
        if first:
            first = False
            return {'type':'http.request','body':b'', 'more_body':False}
        await emitted.wait()
        return {'type':'http.disconnect'}
    async def send(message):
        if message['type']=='http.response.body' and message.get('body')==b'first': emitted.set()
    await asyncio.wait_for(web.app(scope, receive, send), 2)
    assert closed.is_set() and not web.app.streams.locked()


@pytest.mark.asyncio
async def test_status_cache_avoids_compute_call_for_every_asset(web):
    web.controller.state = 'running'
    async with client(web) as c:
        for _ in range(10): assert (await c.get('/asset')).status_code == 206
    assert web.controller.reads == 1


@pytest.mark.asyncio
async def test_start_page_waits_for_backend_health_not_just_running_vm(web):
    web.controller.state = 'running'; healthy = [False]
    def health(request):
        assert str(request.url) == 'http://10.2.0.4:5273/backend/health'
        return httpx.Response(200 if healthy[0] else 503, stream=httpx.ByteStream(b''))
    web.app.client = httpx.AsyncClient(transport=httpx.MockTransport(health))
    async with client(web) as c:
        assert (await c.get('/cloud/status')).json()['state'] == 'preparing'
        healthy[0] = True
        assert (await c.get('/cloud/status')).json()['state'] == 'running'
    assert web.controller.starts == 0


def test_hypercorn_command_supports_application_factory(web, monkeypatch):
    pytest.importorskip('hypercorn')
    from hypercorn.utils import load_application
    monkeypatch.setattr(gateway, 'create_app', lambda:web.app)
    assert load_application('on_demand_gateway:create_app()', gateway.MAX_BODY_BYTES) is not None


@pytest.mark.parametrize('backend', ['http://127.0.0.1:5273', 'http://169.254.169.254',
    'http://evil.test', 'https://10.2.0.4', 'http://user:pass@10.2.0.4', 'http://10.2.0.4/path'])
def test_backend_must_be_fixed_private_ipv4_origin(backend):
    with pytest.raises(ValueError): gateway.Settings('owner', 'a-long-test-password', 'https://music.test', backend)


def test_compute_adapter_uses_exact_instance_stop_policy_and_idempotency_key():
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, url, **kwargs):
            calls.append(('GET', url, kwargs))
            return httpx.Response(200, request=httpx.Request('GET', url), json={
                'id':'123', 'status':'TERMINATED', 'lastStartTimestamp':'2026-11-20T00:00:00Z',
                'lastStopTimestamp':'2026-11-20T00:30:00Z',
                'scheduling':{'maxRunDuration':{'seconds':'7200'}, 'instanceTerminationAction':'STOP', 'automaticRestart':False},
                'resourceStatus':{'scheduling':{'terminationTimestamp':'2026-11-20T01:59:53.400Z'}},
                'networkInterfaces':[{'networkIP':'10.2.0.4'}]})
        def post(self, url, **kwargs):
            calls.append(('POST', url, kwargs))
            return httpx.Response(200, request=httpx.Request('POST', url), json={'status':'PENDING'})
    compute = gateway.GoogleCompute('project', 'asia-east1-a', 'music-vm', Session)
    instance = compute.describe()
    assert instance.status == 'TERMINATED' and instance.max_run_seconds == 7200
    assert instance.stopped_at - instance.started_at == 1800
    assert instance.termination_at-instance.started_at == pytest.approx(7193.4)
    request_id = str(uuid4()); compute.start(request_id)
    assert calls[1] == ('POST', 'https://compute.googleapis.com/compute/v1/projects/project/zones/asia-east1-a/instances/music-vm/start',
                        {'params':{'requestId':request_id}, 'json':{}, 'timeout':20})


def test_gcs_adapter_matches_read_generation_and_uses_conditional_nonretrying_write():
    exceptions = pytest.importorskip('google.api_core.exceptions')
    calls = []
    class Blob:
        size, generation = 10, 123
        def reload(self, **kwargs): calls.append(('reload', kwargs))
        def download_as_bytes(self, **kwargs):
            calls.append(('download', kwargs)); return b'{"v":1}'
        def upload_from_string(self, raw, **kwargs): calls.append(('upload', raw, kwargs))
    blob = Blob()
    store = gateway.GCSLedger(SimpleNamespace(blob=lambda name:blob), 'ledger.json')
    assert store.read() == ({'v':1}, 123)
    store.compare_and_swap(123, {'v':2})
    assert calls[1][1]['if_generation_match'] == 123
    assert calls[2][2]['if_generation_match'] == 123 and calls[2][2]['retry'] is None
    def failed(**kwargs): raise exceptions.PreconditionFailed('race')
    blob.download_as_bytes = failed
    with pytest.raises(gateway.LedgerConflict): store.read()
    def missing(**kwargs): raise exceptions.NotFound('missing')
    blob.reload = missing
    assert store.read() == (None, 0)


def test_gcs_write_conflict_and_ambiguous_failure_are_not_silently_retried():
    exceptions = pytest.importorskip('google.api_core.exceptions')
    calls = []
    def upload(raw, **kwargs):
        calls.append(kwargs); raise exceptions.PreconditionFailed('race')
    store = gateway.GCSLedger(SimpleNamespace(blob=lambda name:SimpleNamespace(upload_from_string=upload)), 'ledger.json')
    with pytest.raises(gateway.LedgerConflict): store.compare_and_swap(0, {'v':1})
    assert len(calls) == 1 and calls[0]['if_generation_match'] == 0


@pytest.mark.asyncio
async def test_live_hypercorn_h2c_accepts_body_larger_than_32_mib(web):
    """Actual TCP HTTP/2 framing, bounded chunks, then a fake fixed VM upstream."""
    pytest.importorskip('hypercorn')
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from h2.events import DataReceived, ResponseReceived, StreamEnded
    import socket

    web.controller.state = 'running'
    size = 33 * 1024 * 1024
    received = []
    class UploadTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            total = 0
            async for chunk in request.stream: total += len(chunk)
            received.append(total)
            return httpx.Response(200, stream=httpx.ByteStream(b'ok'))
    web.app.client = httpx.AsyncClient(transport=UploadTransport())
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
    config = Config(); config.bind = [f'127.0.0.1:{port}']; config.accesslog = None; config.errorlog = None
    shutdown = asyncio.Event()
    serving = asyncio.create_task(serve(web.app, config, shutdown_trigger=shutdown.wait))
    writer = None
    try:
        for _ in range(100):
            try:
                reader, writer = await asyncio.open_connection('127.0.0.1',port)
                break
            except ConnectionRefusedError:
                await asyncio.sleep(.01)
        assert writer is not None
        connection = H2Connection(config=H2Configuration(client_side=True, header_encoding='utf-8'))
        connection.initiate_connection()
        connection.send_headers(1, [(':method','POST'),(':scheme','https'),(':authority','music.test'),
            (':path','/backend/upload'),('origin','https://music.test'),
            ('authorization', web.app.backend_auth.decode()),('content-length',str(size))])
        writer.write(connection.data_to_send()); await writer.drain()
        sent = 0; ended = False; status = None; response = b''
        while not ended:
            while sent < size:
                count = min(size-sent, connection.local_flow_control_window(1), connection.max_outbound_frame_size)
                if count <= 0: break
                sent += count
                connection.send_data(1, b'x'*count, end_stream=sent==size)
            writer.write(connection.data_to_send()); await writer.drain()
            data = await asyncio.wait_for(reader.read(65536), 10)
            assert data, 'HTTP/2 connection closed unexpectedly'
            for event in connection.receive_data(data):
                if isinstance(event, ResponseReceived): status = dict(event.headers)[':status']
                elif isinstance(event, DataReceived):
                    response += event.data
                    connection.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
                elif isinstance(event, StreamEnded): ended = True
        assert status == '200' and response == b'ok' and received == [size]
    finally:
        if writer is not None:
            writer.close(); await writer.wait_closed()
        shutdown.set()
        await asyncio.wait_for(serving, 5)
