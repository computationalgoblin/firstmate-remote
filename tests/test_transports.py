import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from firstmate_voice.herder.adapter import HerderAdapter, atomic_json
from firstmate_voice.herder.herdr import HerdrClient
from firstmate_voice.notifications.base import Notification
from firstmate_voice.notifications.dispatcher import Dispatcher
from firstmate_voice.notifications.ntfy import NtfyNotifier
from firstmate_voice.repository import Repository
from firstmate_voice.domain import Outcome, State
from tests.helpers import FakeControl, config


class TransportTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    async def test_real_rpc_wire_has_structured_arguments_and_bounded_timeout(self):
        socket = self.root / 'herdr.sock'
        received = []
        async def handle(reader, writer):
            try:
                req = json.loads(await reader.readline())
                received.append(req)
                if req['method'] == 'agent.get':
                    result = {'agent': {'pane_id': req['params']['target']}}
                else:
                    result = {'type': 'agent_keys_sent'}
                writer.write((json.dumps({'id': req['id'], 'result': result}) + '\n').encode())
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, str(socket))
        async with server:
            client = HerdrClient(socket, 1)
            await client.get('w1:p1')
            await client.cancel('w1:p1')
        self.assertEqual(received[1]['params'], {'target': 'w1:p1', 'keys': ['esc']})
        self.assertEqual(received[0]['method'], 'agent.get')

    async def test_rpc_timeout_is_transport_only(self):
        socket = self.root / 'herdr.sock'
        async def handle(reader, writer):
            try:
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, str(socket))
        async with server:
            with self.assertRaises(TimeoutError):
                await HerdrClient(socket, 0.02).get('w1:p1')

    async def test_rpc_error_wrong_id_and_wrong_pane_rejected(self):
        for response in ({'id': 'wrong', 'result': {}}, {'error': {'code': 'bad'}},
                         {'result': {'agent': {'pane_id': 'wrong'}}}):
            socket = self.root / 'bad.sock'
            async def handle(reader, writer):
                try:
                    req = json.loads(await reader.readline())
                    writer.write((json.dumps({'id': req['id']} | response) + '\n').encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()
            server = await asyncio.start_unix_server(handle, str(socket))
            async with server:
                with self.assertRaises((ValueError, OSError)):
                    await HerdrClient(socket, 1).get('w1:p1')
            socket.unlink(missing_ok=True)

    async def test_atomic_request_schema_and_path_traversal_guard(self):
        cfg = config(self.root)
        adapter = HerderAdapter(cfg, FakeControl())
        with self.assertRaises(ValueError):
            adapter.path('../../outside', 'request')
        target = self.root / 'record.json'
        atomic_json(target, {'literal': '$(touch forbidden)\nñ'})
        self.assertEqual(json.loads(target.read_text())['literal'], '$(touch forbidden)\nñ')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob('*.tmp-*')), [])

    async def test_outbox_retry_only_sends_spoken_or_question(self):
        cfg = config(self.root)
        repo = Repository(cfg.database, cfg.home)
        self.addCleanup(repo.close)
        job = repo.enqueue('do', 'one')
        turn = repo.start_next()
        with repo.transaction():
            repo.event(job['id'], 'trace', {'detail': 'PRIVATE'}, channel='internal')
            repo.finish(job['id'], turn['id'], Outcome(State.COMPLETED, 'Spoken', 'FULL PRIVATE', error='ERROR PRIVATE'))
        class FakeNotifier:
            def __init__(self):
                self.fail = True
                self.messages = []
            async def notify(self, n):
                if self.fail:
                    raise OSError('SECRET URL')
                self.messages.append(n.message)
        notifier = FakeNotifier()
        dispatcher = Dispatcher(repo, notifier)
        with self.assertLogs(level='WARNING') as logs:
            await dispatcher.tick()
        self.assertNotIn('SECRET URL', str(logs.output))
        self.assertEqual(repo.get(job['id'])['state'], State.COMPLETED)
        notifier.fail = False
        await Dispatcher(repo, notifier).tick()
        await dispatcher.tick()
        self.assertEqual(notifier.messages, ['Spoken'])

    async def test_ntfy_payload_and_auth_without_network(self):
        notifier = NtfyNotifier('https://push.invalid', 'test-only-topic', 'test-only-token')
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch('urllib.request.OpenerDirector.open', return_value=Response()) as request:
            await notifier.notify(Notification(1, 'job', 'completed', 'Hecho.'))
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_header('Authorization'), 'Bearer test-only-token')
        self.assertEqual(json.loads(sent.data), {'topic': 'test-only-topic', 'title': 'First Mate: completed', 'message': 'Hecho.'})
        for server in ('http://push.invalid', 'https://secret@push.invalid', 'https://push.invalid?token=secret'):
            with self.assertRaises(ValueError):
                NtfyNotifier(server, 'test')
