"""Bounded HTTP/1 JSON transport. Execution belongs exclusively to the worker."""
import hmac
import ipaddress
import json
import math
import os
import re
import signal
import socketserver
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus

from .repository import Repository

MAX_BODY = 16384
MAX_HEADERS = 8192
MAX_CONNECTIONS = 16
ID = re.compile(r'[A-Za-z0-9_-]{1,200}\Z')
JOB_ROUTE = re.compile(r'/jobs/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:/(reply|cancel))?\Z')
PUBLIC_FIELDS = ('id', 'voice_session_id', 'state', 'created_at', 'updated_at',
                 'spoken_response', 'question')


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    host: str = '127.0.0.1'
    port: int = 8765
    request_timeout: float = 3
    rate_limit: int = 60
    rate_window: float = 60

    def __post_init__(self):
        if not isinstance(self.token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', self.token):
            raise ValueError('Configure a private gateway token of 32–256 URL-safe characters')
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError:
            raise ValueError('gateway.host must be an IPv4 loopback address') from None
        if address.version != 4 or not address.is_loopback:
            raise ValueError('gateway.host must be an IPv4 loopback address; use Tailscale Serve for HTTPS')
        if type(self.port) is not int or not 0 <= self.port <= 65535:
            raise ValueError('Invalid gateway.port')
        if type(self.rate_limit) is not int or not 1 <= self.rate_limit <= 10000:
            raise ValueError('Invalid gateway.rate_limit')
        for value in (self.request_timeout, self.rate_window):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 3600:
                raise ValueError('Invalid gateway timeout or rate window')

    @classmethod
    def load(cls, data):
        if not isinstance(data, dict) or data.keys() - {
                'token_env', 'host', 'port', 'request_timeout', 'rate_limit', 'rate_window'}:
            raise ValueError('Invalid gateway configuration fields')
        token_env = data.get('token_env', 'FMVOICE_API_TOKEN')
        if not isinstance(token_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token_env):
            raise ValueError('Invalid gateway.token_env')
        return cls(token=os.environ.get(token_env, ''),
                   **{k: v for k, v in data.items() if k != 'token_env'})


class RateLimiter:
    """Global fixed window: bounded memory, also covers failed authentication.

    There is one shared credential. Never trust proxy/client IP headers as keys.
    Restarting the gateway resets the window; this is basic admission control.
    """
    def __init__(self, limit, window, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.start, self.count = clock(), 0
        self.lock = threading.Lock()

    def allow(self):
        with self.lock:
            now = self.clock()
            if now - self.start >= self.window:
                self.start, self.count = now, 0
            if self.count >= self.limit:
                return False
            self.count += 1
            return True


class APIError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def public_job(job):
    value = {key: job[key] for key in PUBLIC_FIELDS}
    value['cancel_requested'] = bool(job['cancel_requested'])
    if job['state'] == 'waiting_for_input':
        value['input_revision'] = job['input_revision']
    return value


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('Non-finite JSON value')


class Gateway(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = False
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, config, settings, *, clock=time.monotonic):
        self.config, self.settings = config, settings
        self.limiter = RateLimiter(settings.rate_limit, settings.rate_window, clock)
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        # Fail before accepting traffic if persistence is unavailable/misconfigured.
        Repository(config.database, config.home, timeout=0.5).close()
        super().__init__((settings.host, settings.port), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            # Do not let a full pool create additional threads or blocked writers.
            request.settimeout(0.05)
            try:
                respond(request, 503, {'error': 'busy'})
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never print request data, exception strings, paths or tracebacks.
        pass


def respond(sock, status, value, *, head=False, allow=None):
    body = json.dumps(value, ensure_ascii=True, allow_nan=False).encode('ascii')
    extra = 'Retry-After: 60\r\n' if status in (429, 503) else ''
    if status == 405 and allow:
        extra += f'Allow: {allow}\r\n'
    if status == 401:
        extra += 'WWW-Authenticate: Bearer\r\n'
    packet = (f'HTTP/1.1 {status} {HTTPStatus(status).phrase}\r\n'
              'Content-Type: application/json; charset=utf-8\r\n'
              f'Content-Length: {len(body)}\r\nConnection: close\r\n'
              f'Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n{extra}\r\n').encode() + (b'' if head else body)
    sock.sendall(packet)


class Handler(socketserver.BaseRequestHandler):
    """One request per connection; bounded headers/body and absolute read deadline.

    Only Content-Length framing is supported. No chunked, compression, upgrade,
    keepalive, redirects, URL decoding, proxy routing or filesystem serving.
    """
    def receive(self, count):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self.request.settimeout(remaining)
        value = self.request.recv(count)
        if not value:
            raise APIError(400, 'incomplete_request')
        return value

    def read_request(self):
        raw = b''
        while b'\r\n\r\n' not in raw:
            if len(raw) >= MAX_HEADERS:
                raise APIError(431, 'headers_too_large')
            raw += self.receive(min(1024, MAX_HEADERS - len(raw)))
        header, body = raw.split(b'\r\n\r\n', 1)
        lines = header.split(b'\r\n')
        if len(lines) > 33 or any(len(line) > 4096 for line in lines):
            raise APIError(431, 'headers_too_large')
        try:
            method, path, version = lines[0].decode('ascii').split(' ')
            self.is_head = method == 'HEAD'
            if version not in ('HTTP/1.1', 'HTTP/1.0') or not re.fullmatch('[A-Z]+', method):
                raise ValueError
            headers = {}
            for line in lines[1:]:
                key, value = line.decode('ascii').split(':', 1)
                if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
                    raise ValueError
                key = key.lower()
                if key in headers or any(ord(c) < 32 or ord(c) == 127 for c in value):
                    raise ValueError
                headers[key] = value.strip(' ')
            if version == 'HTTP/1.1' and not headers.get('host'):
                raise ValueError
        except (ValueError, UnicodeError):
            raise APIError(400, 'invalid_headers') from None
        if not self.server.limiter.allow():
            raise APIError(429, 'rate_limited')
        supplied = headers.get('authorization', '').encode('ascii')
        expected = ('Bearer ' + self.server.settings.token).encode('ascii')
        if not hmac.compare_digest(supplied, expected):
            raise APIError(401, 'unauthorized')
        if any(k in headers for k in ('transfer-encoding', 'content-encoding', 'expect', 'upgrade')):
            raise APIError(400, 'unsupported_framing')
        route = JOB_ROUTE.fullmatch(path)
        allowed = ('GET' if path in ('/health', '/jobs/pending-input') else
                   'POST' if path == '/jobs' or (route and route[2]) else
                   'GET' if route else None)
        if allowed is None:
            raise APIError(404, 'not_found')
        self.allowed_method = allowed
        if method != allowed:
            raise APIError(405, 'method_not_allowed')
        length = headers.get('content-length', '0' if method == 'GET' else '')
        if not re.fullmatch(r'[0-9]{1,6}', length):
            raise APIError(400, 'invalid_content_length')
        length = int(length)
        if length > MAX_BODY:
            raise APIError(413, 'body_too_large')
        if method == 'GET':
            if length or body:
                raise APIError(400, 'unexpected_body')
            return method, path, route, {}
        if headers.get('content-type', '').lower() not in ('application/json', 'application/json; charset=utf-8'):
            raise APIError(415, 'json_required')
        while len(body) < length:
            body += self.receive(length - len(body))
        if len(body) != length:
            raise APIError(400, 'invalid_body_length')
        try:
            data = json.loads(body.decode('utf-8'), object_pairs_hook=strict_object, parse_constant=invalid_constant)
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            raise APIError(400, 'invalid_json') from None
        return method, path, route, data

    def dispatch(self, repo, method, path, route, data):
        if path == '/health':
            repo.db.execute('SELECT 1').fetchone()
            return 200, {'status': 'ok'}
        if path == '/jobs/pending-input':
            jobs = repo.pending_input()
            return 200, {'jobs': [public_job(j) for j in jobs[:100]], 'has_more': len(jobs) > 100}
        if method == 'POST':
            allowed = {'request_id', 'prompt'}
            if path == '/jobs':
                allowed.add('voice_session_id')
            elif route[2] == 'reply':
                allowed.add('input_revision')
            else:
                allowed = set()
            if data.keys() - allowed:
                raise APIError(400, 'invalid_fields')
            if allowed:
                for key in ('request_id', 'prompt'):
                    if not isinstance(data.get(key), str) or not data[key].strip():
                        raise APIError(400, 'invalid_fields')
                for key in ('request_id', 'voice_session_id'):
                    if key in data and (not isinstance(data[key], str) or not ID.fullmatch(data[key])):
                        raise APIError(400, 'invalid_fields')
                if 'input_revision' in allowed and (type(data.get('input_revision')) is not int or data['input_revision'] <= 0):
                    raise APIError(400, 'invalid_fields')
                try:
                    data['prompt'].encode('utf-8')
                except UnicodeError:
                    raise APIError(400, 'invalid_fields') from None
        # Snapshot keeps state/question/revision coherent on GET. Write methods
        # manage their own BEGIN IMMEDIATE transaction in the shared repository.
        if method == 'GET':
            repo.db.execute('BEGIN')
            job = repo.get(route[1])
            job['input_revision'] = repo.input_revision(job['id'])
            repo.db.execute('COMMIT')
            return 200, public_job(job)
        if path == '/jobs':
            job = repo.enqueue(data['prompt'], data['request_id'], voice_session_id=data.get('voice_session_id'))
        elif route[2] == 'reply':
            job = repo.enqueue(data['prompt'], data['request_id'], job_id=route[1], input_revision=data['input_revision'])
        else:
            job = repo.cancel(route[1])
        # Mutation acknowledgements contain only receipt/correlation and state;
        # clients never need the result or another read to finish submission.
        return 202, {'accepted': True, 'id': job['id'], 'voice_session_id': job['voice_session_id'],
                     'state': job['state'], 'cancel_requested': bool(job['cancel_requested'])}

    def handle(self):
        repo = None
        self.deadline = time.monotonic() + self.server.settings.request_timeout
        try:
            method, path, route, data = self.read_request()
            repo = Repository(self.server.config.database, self.server.config.home, timeout=0.5)
            status, value = self.dispatch(repo, method, path, route, data)
        except APIError as exc:
            status, value = exc.status, {'error': exc.code}
        except ValueError as exc:
            # These are stable domain errors, never interpolate exception text.
            code = str(exc)
            status = 404 if code == 'Unknown job' else 413 if code.startswith('Wrapped prompt exceeds') else 409
            value = {'error': {404: 'not_found', 413: 'prompt_too_large', 409: 'conflict'}[status]}
        except sqlite3.Error:
            status, value = 503, {'error': 'storage_unavailable'}
        except TimeoutError:
            status, value = 408, {'error': 'request_timeout'}
        except Exception:
            status, value = 500, {'error': 'internal_error'}
        finally:
            if repo is not None:
                repo.close()
        try:
            self.request.settimeout(0.5)
            respond(self.request, status, value, head=getattr(self, 'is_head', False),
                    allow=getattr(self, 'allowed_method', None))
        except OSError:
            pass  # Client can retry the same request_id after an ambiguous reply.


def serve(config):
    os.umask(0o077)
    settings = Settings.load(config.gateway)
    with Gateway(config, settings) as server:
        # shutdown must run outside serve_forever's thread (socketserver contract).
        def stop(signum, frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
