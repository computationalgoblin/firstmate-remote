import asyncio
import concurrent.futures
import http.client
import json
import socket
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, Mock

from firstmate_voice.gateway import Gateway, Settings, RateLimiter, Handler, MAX_CONNECTIONS
from firstmate_voice.domain import Outcome, State
from firstmate_voice.manager import JobManager
from firstmate_voice.repository import Repository
from tests.helpers import config, FakeAdapter, FakeControl, claim, result

TOKEN = 'offline_test_token_' + 'x' * 32


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = config(Path(self.temp.name))
        self.repo = Repository(self.cfg.database, self.cfg.home)
        self.addCleanup(self.repo.close)
        self.server = Gateway(self.cfg, Settings(TOKEN, port=0, rate_limit=10000, request_timeout=0.2))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.adapter = FakeAdapter(self.cfg, FakeControl())
        self.manager = JobManager(self.repo, self.adapter)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method='GET', path='/health', data=None, *, token=TOKEN, headers=None, raw=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        try:
            h = {'Content-Type': 'application/json'}
            if token is not None:
                h['Authorization'] = 'Bearer ' + token
            h.update(headers or {})
            body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
            conn.request(method, path, body=body, headers=h)
            response = conn.getresponse()
            payload = response.read()
            result = response.status, json.loads(payload) if payload else None
            self.assertEqual(response.getheader('Cache-Control'), 'no-store')
            self.assertEqual(response.getheader('Connection'), 'close')
            if response.status == 405:
                self.assertIn(response.getheader('Allow'), ('GET', 'POST'))
            return result
        finally:
            conn.close()

    def wire(self, raw, shutdown=True):
        with socket.create_connection(self.server.server_address, timeout=2) as sock:
            sock.sendall(raw)
            if shutdown:
                sock.shutdown(socket.SHUT_WR)
            response = b''
            while chunk := sock.recv(65536):
                response += chunk
            return int(response.split(b' ')[1]), response

    def submit(self, rid='request', **extra):
        status, job = self.request('POST', '/jobs', {'request_id': rid, 'prompt': 'private prompt', **extra})
        self.assertEqual(status, 202, job)
        self.assertIs(job['accepted'], True)
        return job

    def tick(self):
        asyncio.run(self.manager.tick())

    def question(self, job):
        self.tick()
        turn = self.repo.active()
        claim(self.adapter, turn)
        result(self.adapter, turn, needs_input=True)
        self.tick()
        return self.request(path='/jobs/' + job['id'])[1]

    def test_authentication_every_route_and_safe_comparison(self):
        paths = [('GET', '/health'), ('GET', '/jobs/pending-input'), ('POST', '/jobs'),
                 ('GET', '/voice/events?after=0&limit=2'),
                 ('GET', '/jobs/' + '0' * 36), ('POST', '/jobs/' + '0' * 36 + '/reply'),
                 ('POST', '/jobs/' + '0' * 36 + '/cancel')]
        for method, path in paths:
            for token in (None, '', 'bad', TOKEN + 'x'):
                self.assertEqual(self.request(method, path, {}, token=token)[0], 401)
        with patch('firstmate_voice.gateway.hmac.compare_digest', wraps=__import__('hmac').compare_digest) as compare:
            self.assertEqual(self.request(), (200, {'status': 'ok'}))
            compare.assert_called_once()
        self.assertEqual(self.repo.jobs(), [])

    def test_strict_methods_routes_headers_and_json(self):
        for method, path, status in [('PUT', '/jobs', 405), ('GET', '/jobs', 405),
                                     ('POST', '/health', 405), ('HEAD', '/health', 405),
                                     ('GET', '/health?internal=1', 404), ('GET', '/%68ealth', 404),
                                     ('GET', '/jobs/pending-input/', 404), ('GET', '/../../private', 404)]:
            self.assertEqual(self.request(method, path, {})[0], status)
        for raw in (b'[]', b'null', b'{', b'{"prompt":"x","prompt":"y"}', b'{"x":NaN}',
                    b'{"x":Infinity}', b'\xff', b'[' * 1500 + b']' * 1500):
            self.assertEqual(self.request('POST', '/jobs', raw=raw)[0], 400)
        for data in ({}, {'prompt': 'x'}, {'request_id': 'x'}, {'request_id': True, 'prompt': 'x'},
                     {'request_id': 'x', 'prompt': ' '}, {'request_id': 'x', 'prompt': 3},
                     {'request_id': '../private', 'prompt': 'x'}, {'request_id': 'x', 'prompt': '\ud800'},
                     {'request_id': 'x', 'prompt': 'x', 'internal': True},
                     {'request_id': 'x', 'prompt': 'x', 'voice_session_id': None}):
            self.assertEqual(self.request('POST', '/jobs', data)[0], 400)
        self.assertEqual(self.request('POST', '/jobs', {}, headers={'Content-Type': 'text/plain'})[0], 415)
        for header in (b'Content-Length: 0\r\nContent-Length: 0', b'Transfer-Encoding: chunked',
                       b'Content-Encoding: gzip', b'Expect: 100-continue', b'Bad Header: no'):
            raw = b'POST /jobs HTTP/1.1\r\nHost: local\r\nAuthorization: Bearer ' + TOKEN.encode() + b'\r\n' + header + b'\r\n\r\n'
            self.assertEqual(self.wire(raw)[0], 400)
        self.assertEqual(self.repo.jobs(), [])

    def test_sizes_deadline_and_storage_contention(self):
        self.assertEqual(self.request('POST', '/jobs', raw=b'x' * 16385)[0], 413)
        # JSON fits the HTTP limit, but not the wrapped voice-file contract.
        self.assertEqual(self.request('POST', '/jobs', {'request_id': 'big', 'prompt': 'x' * 16000})[0], 413)
        self.assertEqual(self.wire(b'GET /health HTTP/1.1\r\nX: ' + b'x' * 8200)[0], 431)
        self.assertEqual(self.wire(b'GET /health HTTP/1.1\r\n', shutdown=False)[0], 408)
        body_header = (f'POST /jobs HTTP/1.1\r\nHost: local\r\nAuthorization: Bearer {TOKEN}\r\n'
                       'Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{').encode()
        self.assertEqual(self.wire(body_header, shutdown=False)[0], 408)
        with self.repo.transaction():
            self.assertEqual(self.request('POST', '/jobs', {'request_id': 'lock', 'prompt': 'x'}),
                             (503, {'error': 'storage_unavailable'}))
        self.assertEqual(self.repo.jobs(), [])

    def test_rate_limit_and_window_reset(self):
        now = [10.0]
        self.server.limiter = RateLimiter(2, 60, clock=lambda: now[0])
        self.assertEqual(self.request(token='bad')[0], 401)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)
        now[0] += 60
        self.assertEqual(self.request()[0], 200)
        # Admission count is atomic even with concurrent callers.
        limiter = RateLimiter(2, 60)
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            self.assertEqual(sum(pool.map(lambda _: limiter.allow(), range(30))), 2)

    def test_connection_pool_is_bounded(self):
        for _ in range(MAX_CONNECTIONS):
            self.server.slots.acquire()
        try:
            self.assertEqual(self.request()[0], 503)
        finally:
            for _ in range(MAX_CONNECTIONS):
                self.server.slots.release()
        self.assertEqual(self.request()[0], 200)

    def test_immediate_durable_idempotent_submission_and_lookup(self):
        with patch('firstmate_voice.herder.herdr.HerdrClient.rpc', side_effect=AssertionError('No Herdr')):
            job = self.submit(voice_session_id='my-voice-session')
            again = self.submit()
            self.assertEqual(job['id'], again['id'])
            self.assertEqual(again['voice_session_id'], 'my-voice-session')
            self.assertEqual(job['state'], 'queued')
        self.assertEqual(len(self.repo.jobs()), 1)
        self.assertEqual(len(self.repo.turns(job['id'])), 1)
        status, fetched = self.request(path='/jobs/' + job['id'])
        self.assertEqual(status, 200)
        self.assertEqual(fetched['state'], 'queued')
        self.assertNotIn('prompt', fetched)
        missing = '/jobs/00000000-0000-0000-0000-000000000000'
        for method, path, data in [('GET', missing, None), ('POST', missing + '/cancel', {}),
                                   ('POST', missing + '/reply', {'request_id': 'r', 'prompt': 'x', 'input_revision': 1})]:
            self.assertEqual(self.request(method, path, data)[0], 404)

    def test_concurrent_retries_make_one_job(self):
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            jobs = list(pool.map(lambda _: self.submit(), range(6)))
        self.assertEqual(len({job['id'] for job in jobs}), 1)
        self.assertEqual(len(self.repo.jobs()), 1)

    def test_pending_reply_idempotency_and_stale_question(self):
        self.assertEqual(self.request(path='/jobs/pending-input')[1], {'jobs': [], 'has_more': False})
        job = self.submit(voice_session_id='conversation')
        waiting = self.question(job)
        job2 = self.submit('second')
        self.question(job2)
        pending = self.request(path='/jobs/pending-input')[1]['jobs']
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0], waiting)
        path = '/jobs/' + job['id'] + '/reply'
        reply = {'request_id': 'answer', 'prompt': 'azul', 'input_revision': waiting['input_revision']}
        status, accepted = self.request('POST', path, reply)
        self.assertEqual(status, 202)
        self.assertEqual(accepted['id'], job['id'])
        self.assertEqual(accepted['voice_session_id'], 'conversation')
        self.assertEqual(self.request('POST', path, reply)[0], 202)
        self.assertEqual(len(self.repo.turns(job['id'])), 2)
        self.assertEqual(self.request('POST', path, dict(reply, request_id='new'))[0], 409)
        self.question(job)
        self.assertEqual(self.request('POST', path, dict(reply, request_id='stale'))[0], 409)
        self.assertEqual(self.request('POST', path, dict(reply, request_id='request'))[0], 409)
        self.assertEqual(self.request('POST', '/jobs', {'request_id': 'answer', 'prompt': 'x'})[0], 409)
        self.assertEqual(self.request('POST', '/jobs/' + job2['id'] + '/reply', reply)[0], 409)
        for revision in (True, 0, -1, None, '1'):
            self.assertEqual(self.request('POST', path, dict(reply, input_revision=revision))[0], 400)

    def test_cancel_queued_waiting_running_and_terminal(self):
        queued = self.submit()
        path = '/jobs/' + queued['id'] + '/cancel'
        self.assertEqual(self.request('POST', path, {})[1]['state'], 'cancelled')
        self.assertEqual(self.request('POST', path, {})[1]['state'], 'cancelled')
        waiting = self.submit('waiting')
        self.question(waiting)
        self.assertEqual(self.request('POST', '/jobs/' + waiting['id'] + '/cancel', {})[1]['state'], 'cancelled')
        running = self.submit('running')
        self.tick()
        status, cancelled = self.request('POST', '/jobs/' + running['id'] + '/cancel', {})
        self.assertEqual(status, 202)
        self.assertEqual(cancelled['state'], 'running')
        self.assertIs(cancelled['cancel_requested'], True)
        self.assertEqual(self.adapter.control.cancels, 0)
        self.tick()
        self.assertEqual(self.request(path='/jobs/' + running['id'])[1]['state'], 'cancelled')

    def test_public_allowlist_and_errors_never_expose_private_data(self):
        job = self.submit()
        self.tick()
        turn = self.repo.active()
        claim(self.adapter, turn)
        result(self.adapter, turn, raw=json.dumps({'spoken_response': 'Listo.', 'question': '', 'needs_input': False,
                                                  'full_response': 'PRIVATE full response tools thoughts /home/secret'}))
        self.tick()
        self.repo.db.execute('UPDATE jobs SET error=? WHERE id=?', ('PRIVATE diagnostic', job['id']))
        self.repo.event(job['id'], 'transport_error', {'detail': 'PRIVATE logs'}, channel='internal')
        for path in ('/health', '/jobs/pending-input', '/jobs/' + job['id']):
            status, value = self.request(path=path)
            self.assertEqual(status, 200)
            self.assertNotIn('PRIVATE', json.dumps(value))
            self.assertNotIn(self.temp.name, json.dumps(value))
            self.assertNotIn(TOKEN, json.dumps(value))
        value = self.request(path='/jobs/' + job['id'])[1]
        self.assertEqual(set(value), {'id', 'voice_session_id', 'state', 'created_at', 'updated_at',
                                      'spoken_response', 'question', 'cancel_requested'})
        with patch.object(Repository, 'get', side_effect=RuntimeError('PRIVATE /home/secret ' + TOKEN)):
            self.assertEqual(self.request(path='/jobs/' + job['id']), (500, {'error': 'internal_error'}))
        self.assertEqual(self.submit()['state'], 'completed')

    def test_settings_fail_closed_without_secrets_in_errors(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                Settings.load({})
        for changes in ({'token': 'short'}, {'host': '0.0.0.0'}, {'host': '100.64.0.1'},
                        {'port': True}, {'request_timeout': float('nan')}, {'rate_limit': 0},
                        {'rate_window': False}):
            with self.assertRaises(ValueError):
                replace(Settings(TOKEN), **changes)
        self.assertNotIn(TOKEN, repr(Settings(TOKEN)))
        with patch.dict('os.environ', {'PRIVATE_TEST_TOKEN': TOKEN}, clear=True):
            self.assertEqual(Settings.load({'token_env': 'PRIVATE_TEST_TOKEN'}).token, TOKEN)

    def test_absolute_deadline_is_not_reset_by_partial_reads(self):
        handler = object.__new__(Handler)
        handler.deadline = 10
        handler.request = Mock()
        handler.request.recv.return_value = b'x'
        with patch('firstmate_voice.gateway.time.monotonic', side_effect=[8, 9, 10]):
            self.assertEqual(handler.receive(1), b'x')
            self.assertEqual(handler.receive(1), b'x')
            with self.assertRaises(TimeoutError):
                handler.receive(1)
        self.assertEqual([call.args[0] for call in handler.request.settimeout.call_args_list], [2, 1])
        self.assertEqual(handler.request.recv.call_count, 2)

    def test_pending_list_is_bounded_and_marks_truncation(self):
        for index in range(101):
            job = self.repo.enqueue('PRIVATE prompt', f'pending-{index}')
            turn = self.repo.start_next()
            with self.repo.transaction():
                self.repo.finish(job['id'], turn['id'], Outcome(State.WAITING, 'Pregunta.',
                                 full_response='PRIVATE detail', question='¿Continuar?'))
        status, value = self.request(path='/jobs/pending-input')
        self.assertEqual(status, 200)
        self.assertEqual(len(value['jobs']), 100)
        self.assertIs(value['has_more'], True)
        self.assertNotIn('PRIVATE', json.dumps(value))
        self.assertEqual(len({job['id'] for job in value['jobs']}), 100)

    def finish_voice(self, rid, state=State.COMPLETED):
        job = self.repo.enqueue('PRIVATE prompt', rid)
        turn = self.repo.start_next()
        with self.repo.transaction():
            self.repo.event(job['id'], 'completed', {'spoken_response': 'PRIVATE internal'}, channel='internal')
            self.repo.finish(job['id'], turn['id'], Outcome(state, 'Resultado ' + rid,
                             full_response='PRIVATE full_response /home/secret tools reasoning',
                             question='¿Continuar ' + rid + '?', error='PRIVATE diagnostics'))
        return job

    def feed(self, after=0, limit=20):
        status, page = self.request(path=f'/voice/events?after={after}&limit={limit}')
        self.assertEqual(status, 200, page)
        return page

    def test_voice_feed_order_pagination_arrivals_and_read_only_replay(self):
        # Equal/backwards wall clocks must not collapse or reorder nearby events.
        with patch('firstmate_voice.repository.time.time', return_value=100):
            first = self.finish_voice('one')
            second = self.finish_voice('two')
        before = [tuple(r) for r in self.repo.db.execute('SELECT * FROM events ORDER BY id')]
        page = self.feed(limit=1)
        self.assertEqual(page['events'][0]['job_id'], first['id'])
        self.assertTrue(page['has_more'])
        self.assertEqual(page, self.feed(limit=1))  # Lost HTTP response or no speech: retry unchanged.
        self.assertEqual(before, [tuple(r) for r in self.repo.db.execute('SELECT * FROM events ORDER BY id')])
        with patch('firstmate_voice.repository.time.time', return_value=50):
            third = self.finish_voice('three')  # Arrives between pages.
        next_page = self.feed(page['next_cursor'], 1)
        self.assertEqual(next_page['events'][0]['job_id'], second['id'])
        self.assertTrue(next_page['has_more'])
        last = self.feed(next_page['next_cursor'], 1)
        self.assertEqual(last['events'][0]['job_id'], third['id'])
        self.assertFalse(last['has_more'])
        ids = [p['events'][0]['event_id'] for p in (page, next_page, last)]
        self.assertEqual(ids, sorted(set(ids)))
        self.assertEqual(self.feed(last['next_cursor']),
                         {'events': [], 'next_cursor': last['next_cursor'], 'has_more': False})
        # Reading one item, then interruption before saving, repeats that item.
        # After saving only the first ID, later items remain available.
        replay = self.feed(ids[0])
        self.assertEqual([e['job_id'] for e in replay['events']], [second['id'], third['id']])
        self.assertEqual(replay, self.feed(ids[0]))

    def test_voice_feed_history_survives_reply_and_notification_ack(self):
        job = self.finish_voice('question', State.WAITING)
        question = self.feed()['events'][0]
        revision = self.repo.input_revision(job['id'])
        self.repo.enqueue('PRIVATE answer', 'reply', job_id=job['id'], input_revision=revision)
        turn = self.repo.start_next()
        with self.repo.transaction():
            self.repo.finish(job['id'], turn['id'], Outcome(State.COMPLETED, 'Listo.', 'PRIVATE detail'))
        self.repo.db.execute('UPDATE events SET notified=1')
        # A fresh connection represents another gateway/process after restart.
        with_repo = Repository(self.cfg.database, self.cfg.home)
        try:
            page = with_repo.voice_events()
        finally:
            with_repo.close()
        self.assertEqual(page['events'][0], question)
        self.assertEqual([e['event_type'] for e in page['events']], ['needs_input', 'completed'])
        self.assertEqual(page['events'][1]['job_id'], job['id'])
        self.assertEqual(page, self.feed())

    def test_voice_feed_allowlist_every_semantic_type(self):
        for index, state in enumerate((State.WAITING, State.COMPLETED, State.FAILED, State.CANCELLED)):
            self.finish_voice(str(index), state)
        page = self.feed()
        self.assertEqual(len(page['events']), 4)
        self.assertEqual(set(page), {'events', 'next_cursor', 'has_more'})
        for event in page['events']:
            field = 'question' if event['event_type'] == 'needs_input' else 'spoken_response'
            self.assertEqual(set(event), {'event_id', 'job_id', 'event_type', field, 'at'})
            self.assertEqual(event[field], '¿Continuar 0?' if field == 'question' else
                             'Resultado ' + str(['needs_input', 'completed', 'failed', 'cancelled'].index(event['event_type'])))
        for secret in ('PRIVATE', 'full_response', 'error', 'prompt', 'turn_id', 'notified', TOKEN, self.temp.name):
            self.assertNotIn(secret, json.dumps(page))

    def test_voice_feed_empty_internal_tail_and_rolled_back_event(self):
        empty = {'events': [], 'next_cursor': 0, 'has_more': False}
        self.assertEqual(self.feed(), empty)
        job = self.repo.enqueue('PRIVATE', 'queued')
        self.repo.event(job['id'], 'trace', {'detail': 'PRIVATE'}, channel='internal')
        self.assertEqual(self.feed(), empty)
        with self.assertRaises(RuntimeError):
            with self.repo.transaction():
                self.repo.event(job['id'], 'completed', {'spoken_response': 'Rolled back'})
                raise RuntimeError('rollback')
        self.assertEqual(self.feed(), empty)
        self.repo.cancel(job['id'])
        page = self.feed()
        self.assertEqual([e['event_type'] for e in page['events']], ['cancelled'])
        self.repo.event(job['id'], 'trace', {}, channel='internal')
        self.assertEqual(self.feed(page['next_cursor']),
                         {'events': [], 'next_cursor': page['next_cursor'], 'has_more': False})

    def test_voice_feed_limits_queries_methods_and_future_cursor(self):
        for query in ('?', '?after=', '?limit=0', '?limit=51', '?limit=-1', '?limit=true',
                      '?after=-1', '?after=01', '?after=1.0', '?after=1e2', '?after=%31',
                      '?after=+1', '?after=9007199254740992', '?after=9223372036854775808',
                      '?after=0&after=0', '?limit=1&limit=2', '?internal=1', '?token=PRIVATE',
                      '?after=0&', '?after=0#fragment', '?limit=01'):
            with self.subTest(query=query):
                self.assertEqual(self.request(path='/voice/events' + query), (400, {'error': 'invalid_query'}))
        self.assertEqual(self.request(path='/voice/events?after=1'), (409, {'error': 'cursor_ahead'}))
        self.assertEqual(self.request(path='/voice/events?after=9007199254740991')[0], 409)
        self.assertEqual(self.request('POST', '/voice/events', {})[0], 405)
        self.assertEqual(self.request(path='/voice/events/', data=None)[0], 404)
        self.assertEqual(self.request(path='/voice/events', data={})[0], 400)
        for index in range(51):
            self.finish_voice(str(index))
        self.assertEqual(len(self.request(path='/voice/events')[1]['events']), 20)
        page = self.request(path='/voice/events?limit=50&after=0')[1]
        self.assertEqual(len(page['events']), 50)
        self.assertTrue(page['has_more'])
        self.assertEqual(len(self.feed(page['next_cursor'], 50)['events']), 1)

    def test_voice_feed_corruption_fails_without_skipping_or_leaking(self):
        job = self.finish_voice('ok')
        for payload in ('PRIVATE invalid JSON', '{}', '[]', '{"spoken_response":42}',
                        json.dumps({'spoken_response': 'x' * 901}), '{"spoken_response":" "}'):
            with self.subTest(payload=payload):
                with self.repo.transaction():
                    self.repo.event(job['id'], 'completed', {})
                    self.repo.db.execute('UPDATE events SET payload=? WHERE id=(SELECT MAX(id) FROM events)', (payload,))
                self.assertEqual(self.request(path='/voice/events'), (503, {'error': 'storage_unavailable'}))
                self.repo.db.execute('DELETE FROM events WHERE id=(SELECT MAX(id) FROM events)')

    def test_voice_feed_upgrade_preserves_phase3_history_and_seeks_index(self):
        self.finish_voice('old')
        old = self.feed()
        # Recreate the Phase 3 schema (same tables, before the feed index).
        self.repo.db.execute('DROP INDEX events_voice')
        self.repo.db.execute('PRAGMA user_version=1')
        upgraded = Repository(self.cfg.database, self.cfg.home)
        try:
            self.assertEqual(upgraded.db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(upgraded.voice_events(), old)
            # A large outbox must not force sorting all past user events on GET.
            plan = upgraded.db.execute(
                "EXPLAIN QUERY PLAN SELECT id,job_id,type,at,payload FROM events INDEXED BY events_voice WHERE id>? "
                "AND channel='user' AND type IN ('needs_input','completed','failed','cancelled') "
                "ORDER BY id LIMIT ?", (0, 21)).fetchall()
            self.assertTrue(any('events_voice' in row[3] for row in plan), plan)
            self.assertFalse(any('TEMP B-TREE' in row[3] for row in plan), plan)
        finally:
            upgraded.close()

    def test_voice_feed_maximum_text_and_exact_cursor_boundary(self):
        from firstmate_voice.repository import MAX_VOICE_CURSOR
        job = self.repo.enqueue('PRIVATE', 'boundary')
        self.repo.db.execute("UPDATE sqlite_sequence SET seq=? WHERE name='events'", (MAX_VOICE_CURSOR - 1,))
        self.repo.event(job['id'], 'completed', {'spoken_response': 'ñ' * 900})
        page = self.feed()
        self.assertEqual(page['next_cursor'], MAX_VOICE_CURSOR)
        self.assertEqual(page['events'][0]['spoken_response'], 'ñ' * 900)
        self.assertEqual(self.feed(MAX_VOICE_CURSOR)['events'], [])
        self.repo.event(job['id'], 'completed', {'spoken_response': 'Beyond exact client range'})
        self.assertEqual(self.request(path=f'/voice/events?after={MAX_VOICE_CURSOR}'),
                         (503, {'error': 'storage_unavailable'}))
