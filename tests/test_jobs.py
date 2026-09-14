import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from firstmate_voice.domain import State, TRANSITIONS, parse_answer, validate_transition
from firstmate_voice.manager import JobManager
from firstmate_voice.repository import Repository
from firstmate_voice.worker import home_lock
from tests.helpers import FakeAdapter, FakeControl, claim, config, result


class JobsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = config(Path(self.tmp.name))
        self.repo = Repository(self.cfg.database, self.cfg.home)
        self.addCleanup(lambda: self.repo.close())
        self.control = FakeControl()
        self.adapter = FakeAdapter(self.cfg, self.control)
        self.manager = JobManager(self.repo, self.adapter)

    def submit(self, request='request-1'):
        return self.repo.enqueue('haz algo', request)

    async def start(self):
        job = self.submit()
        await self.manager.tick()
        turn = self.repo.active()
        return job, turn

    async def test_lifecycle_queue_and_separate_responses(self):
        job, turn = await self.start()
        second = self.submit('request-2')
        claim(self.adapter, turn)
        self.control.state = 'blocked'  # Herdr blocked never means needs_input.
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)
        self.assertEqual(self.repo.get(second['id'])['state'], State.QUEUED)
        result(self.adapter, turn)
        await self.manager.tick()
        done = self.repo.get(job['id'])
        self.assertEqual(done['state'], State.COMPLETED)
        self.assertNotEqual(done['spoken_response'], done['full_response'])
        self.assertEqual(self.repo.turns(job['id'])[0]['spoken_response'], done['spoken_response'])
        await self.manager.tick()
        self.assertEqual(self.repo.active()['job_id'], second['id'])

    async def test_idempotency_across_clients_and_restart(self):
        first = self.submit()
        other = Repository(self.cfg.database, self.cfg.home)
        try:
            self.assertEqual(other.enqueue('different', 'request-1')['id'], first['id'])
        finally:
            other.close()
        await self.manager.tick()
        turn = self.repo.active()
        claim(self.adapter, turn)
        self.repo.close()
        self.repo = Repository(self.cfg.database, self.cfg.home)
        self.manager = JobManager(self.repo, self.adapter)
        self.assertEqual(self.submit()['id'], first['id'])
        await self.manager.tick()
        self.assertFalse(self.adapter.path(turn['id'], 'request').exists())
        result(self.adapter, turn)
        await self.manager.tick()
        self.assertEqual(len(self.repo.turns(first['id'])), 1)
        self.assertEqual(self.repo.get(first['id'])['state'], State.COMPLETED)

    async def test_question_reply_preserves_job_session_and_turn_history(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        result(self.adapter, turn, needs_input=True)
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['question'], '¿Qué color?')
        reply = self.repo.enqueue('azul', 'reply-1', job_id=job['id'])
        self.assertEqual(reply['voice_session_id'], job['voice_session_id'])
        self.assertEqual(reply['state'], State.QUEUED)
        await self.manager.tick()
        follow = self.repo.active()
        self.assertNotEqual(follow['id'], turn['id'])
        self.assertIn(job['id'], follow['prompt'])
        self.assertEqual(self.repo.enqueue('azul', 'reply-1', job_id=job['id'])['id'], job['id'])
        claim(self.adapter, follow)
        result(self.adapter, follow)
        await self.manager.tick()
        history = self.repo.turns(job['id'])
        self.assertEqual(history[0]['question'], '¿Qué color?')
        self.assertEqual(len(history), 2)
        self.assertEqual(self.repo.get(job['id'])['state'], State.COMPLETED)

    async def test_cancel_queued_and_waiting(self):
        job = self.submit()
        self.assertEqual(self.repo.cancel(job['id'])['state'], State.CANCELLED)
        await self.manager.tick()
        self.assertIsNone(self.repo.active())
        job = self.submit('next')
        await self.manager.tick()
        turn = self.repo.active()
        claim(self.adapter, turn)
        result(self.adapter, turn, needs_input=True)
        await self.manager.tick()
        self.assertEqual(self.repo.cancel(job['id'])['state'], State.CANCELLED)
        self.assertEqual(self.control.cancels, 0)

    async def test_cancel_unclaimed_withdraws_without_escape(self):
        job, turn = await self.start()
        self.repo.cancel(job['id'])
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.CANCELLED)
        self.assertFalse(self.adapter.path(turn['id'], 'request').exists())
        self.assertEqual(self.control.cancels, 0)

    async def test_cancel_claimed_waits_for_result_and_never_repeats_escape(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        self.repo.cancel(job['id'])
        second = self.submit('second')
        await self.manager.tick()
        self.manager = JobManager(self.repo, self.adapter)
        await self.manager.tick()
        self.assertEqual(self.control.cancels, 1)
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)
        self.assertEqual(self.repo.get(second['id'])['state'], State.QUEUED)
        result(self.adapter, turn, error='interrumpido')
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.CANCELLED)

    async def test_result_wins_over_claim_timeout_and_transport_outage(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        result(self.adapter, turn)
        self.control.error = OSError('socket offline')
        with patch('firstmate_voice.manager.time.time', return_value=10**12):
            await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.COMPLETED)

    async def test_no_job_deadline_and_internal_transport_errors(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        with patch('firstmate_voice.manager.time.time', return_value=10**12):
            await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)
        self.control.error = OSError('PRIVATE TOOL TRACE')
        await self.manager.tick()
        self.assertNotIn('PRIVATE TOOL TRACE', json.dumps(self.repo.events(job['id'])))
        self.assertIn('PRIVATE TOOL TRACE', json.dumps(self.repo.events(job['id'], True)))
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)

    async def test_claim_transport_timeout(self):
        job, turn = await self.start()
        with patch('firstmate_voice.manager.time.time', return_value=10**12):
            await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.FAILED)
        self.assertFalse(self.adapter.path(turn['id'], 'request').exists())

    async def test_claim_racing_timeout_preserves_turn(self):
        job, turn = await self.start()
        withdraw = self.adapter.withdraw
        def race(turn_id):
            claim(self.adapter, turn)
            return withdraw(turn_id)
        with patch.object(self.adapter, 'withdraw', side_effect=race), patch('firstmate_voice.manager.time.time', return_value=10**12):
            await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)

    async def test_missing_dispatch_record_never_resubmits(self):
        job, turn = await self.start()
        self.adapter.path(turn['id'], 'request').unlink()
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.FAILED)
        self.assertFalse(self.adapter.recover(turn['id']))

    async def test_restart_identity_failure_does_not_cancel_new_agent(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        self.repo.cancel(job['id'])
        self.control.session = 'new-session'
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.FAILED)
        self.assertEqual(self.control.cancels, 0)

    async def test_reply_refuses_changed_conversation(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        result(self.adapter, turn, needs_input=True)
        await self.manager.tick()
        self.repo.enqueue('azul', 'reply', job_id=job['id'])
        self.control.session = 'new-session'
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.FAILED)
        self.assertFalse(list(self.adapter.directory.glob('*.request.json')))

    async def test_upstream_error_and_invalid_answer_are_not_spoken(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        result(self.adapter, turn, error='technical error details')
        await self.manager.tick()
        value = self.repo.get(job['id'])
        self.assertEqual(value['error'], 'technical error details')
        self.assertNotIn('technical', value['spoken_response'])
        for raw in ('raw logs and reasoning', '{"needs_input": "false"}', '[]'):
            outcome = parse_answer(raw)
            self.assertEqual(outcome.state, State.FAILED)
            self.assertNotIn(raw, outcome.spoken_response)

    async def test_foreign_voice_turn_blocks_dispatch(self):
        self.adapter.directory.mkdir(parents=True)
        path = self.adapter.directory / 'desktop.claimed.json'
        path.write_text('{}')
        job = self.submit()
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.QUEUED)
        path.unlink()
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.RUNNING)

    async def test_completion_during_cancel_identity_rpc_skips_escape(self):
        job, turn = await self.start()
        claim(self.adapter, turn)
        self.repo.cancel(job['id'])
        original = self.control.get
        async def settle(pane):
            result(self.adapter, turn)
            return await original(pane)
        with patch.object(self.control, 'get', side_effect=settle):
            await self.manager.tick()
        self.assertEqual(self.control.cancels, 0)
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.CANCELLED)

    async def test_cancel_uncertain_missing_turn_never_sends_escape(self):
        job, turn = await self.start()
        self.adapter.path(turn['id'], 'request').unlink()
        self.repo.cancel(job['id'])
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.FAILED)
        self.assertEqual(self.control.cancels, 0)

    async def test_recovery_after_publication_before_phase_commit(self):
        job, turn = await self.start()
        self.repo.update_turn(turn['id'], phase='dispatching')
        self.manager = JobManager(self.repo, self.adapter)
        await self.manager.tick()
        claim(self.adapter, turn)
        result(self.adapter, turn)
        await self.manager.tick()
        self.assertEqual(self.repo.get(job['id'])['state'], State.COMPLETED)
        self.assertEqual(len(self.repo.turns(job['id'])), 1)

    def test_concurrent_clients_share_request_id_atomically(self):
        from concurrent.futures import ThreadPoolExecutor
        def client(_):
            repo = Repository(self.cfg.database, self.cfg.home)
            try:
                return repo.enqueue('same request', 'concurrent')['id']
            finally:
                repo.close()
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(client, range(12)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.repo.turns(ids[0])), 1)

    def test_transitions_exhaustive(self):
        for old in State:
            for new in State:
                if new in TRANSITIONS[old]:
                    validate_transition(old, new)
                else:
                    with self.assertRaises(ValueError):
                        validate_transition(old, new)

    def test_input_bounds_and_rollback(self):
        for text in ('', 'ñ' * 16384):
            with self.assertRaises(ValueError):
                self.repo.enqueue(text, 'bad')
        self.assertEqual(self.repo.jobs(), [])
        job = self.submit()
        with self.assertRaises(ValueError):
            self.repo.enqueue('premature', 'reply', job_id=job['id'])
        self.assertEqual(len(self.repo.turns(job['id'])), 1)

    def test_one_worker_per_home_even_with_another_database(self):
        with home_lock(self.cfg):
            with self.assertRaises(ValueError), home_lock(self.cfg):
                pass
        from dataclasses import replace
        with self.assertRaises(ValueError), home_lock(replace(self.cfg, database=self.cfg.database.with_name('another.sqlite3'))):
            pass

    def test_migration_is_reproducible_and_home_bound(self):
        self.assertEqual(self.repo.db.execute('PRAGMA user_version').fetchone()[0], 2)
        with self.assertRaises(ValueError):
            Repository(self.cfg.database, self.cfg.home / 'other')
        self.assertEqual(self.repo.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
