"""Serial durable execution; independent of notification providers and CLI lifetime."""
import time

from .domain import cancelled, failed
from .herder.adapter import IdentityChanged


class JobManager:
    def __init__(self, repository, adapter, claim_timeout=15):
        self.repo, self.adapter, self.claim_timeout = repository, adapter, claim_timeout
        self.last_diagnostic = None
        self.last_status = None

    def observe(self, turn, health):
        status = (turn['id'], health.get('agent_status', 'unknown'))
        if status != self.last_status:
            self.repo.event(turn['job_id'], 'herdr_status', {'agent_status': status[1]},
                            turn_id=turn['id'], channel='internal')
            self.last_status = status

    def finish(self, turn, outcome):
        with self.repo.transaction():
            self.repo.finish(turn['job_id'], turn['id'], outcome)

    def diagnostic(self, turn, error):
        message = f'{type(error).__name__}: {error}'
        if message != self.last_diagnostic:
            self.repo.event(turn['job_id'], 'transport_error', {'detail': message},
                            turn_id=turn['id'], channel='internal')
            self.last_diagnostic = message

    async def tick(self):
        turn = self.repo.active()
        if turn is None:
            if self.adapter.foreign_inflight():
                return
            turn = self.repo.start_next()
            if turn is None:
                return
        try:
            await self.advance(turn)
        except IdentityChanged as exc:
            self.adapter.withdraw(turn['id'])
            self.finish(turn, failed(str(exc)))
        except (OSError, ValueError, TimeoutError) as exc:
            # Transport outages are internal and retryable, never a job deadline.
            self.diagnostic(turn, exc)

    async def advance(self, turn):
        job = self.repo.get(turn['job_id'])
        result = self.adapter.outcome(turn['id'])
        if result:
            self.finish(turn, cancelled() if job['cancel_requested'] else result)
            return
        files = self.adapter.recover(turn['id'])
        if job['cancel_requested']:
            if self.adapter.withdraw(turn['id']) or (turn['identity'] is None and not files):
                self.finish(turn, cancelled())
                return
            if not files:
                self.finish(turn, failed('Voice turn records missing; cancellation cannot safely target this turn'))
                return
            if not turn['cancel_sent']:
                await self.adapter.check_identity(turn['identity'])
                # Persist BEFORE Escape: do not send a second Escape after a crash.
                # An ambiguous transport failure remains pending for reconciliation.
                self.repo.update_turn(turn['id'], cancel_sent=1)
                await self.adapter.cancel(turn['identity'], turn['id'])
            else:
                await self.adapter.check_identity(turn['identity'])
            return  # Wait for extension's terminal record; keep the home slot held.
        if turn['identity'] is None:
            health = await self.adapter.health()
            self.observe(turn, health)
            identity = self.adapter.identity(health)
            # Replies must remain attached to the original live Pi conversation.
            previous = [t for t in self.repo.turns(turn['job_id']) if t['seq'] < turn['seq'] and t['identity']]
            if previous and previous[-1]['identity'] != identity:
                raise IdentityChanged('The conversation changed before the reply')
            now = time.time()
            self.repo.update_turn(turn['id'], identity=identity, submitted_at=now)
            turn = turn | {'identity': identity, 'submitted_at': now}
            await self.adapter.submit(turn, identity)
            self.repo.update_turn(turn['id'], phase='sent')
            return
        self.observe(turn, await self.adapter.check_identity(turn['identity']))
        if not files:
            # Includes crash between durable dispatch intent and publication. Never
            # re-send: it might instead be a consumed turn whose files were swept.
            self.finish(turn, failed('Voice turn records missing; delivery is uncertain and was not retried'))
            return
        if 'claimed' in files:
            if turn['phase'] != 'claimed':
                with self.repo.transaction():
                    self.repo.update_turn(turn['id'], phase='claimed')
                    self.repo.event(turn['job_id'], 'voice_claimed', {}, turn_id=turn['id'], channel='internal')
        elif 'request' in files and time.time() - turn['submitted_at'] >= self.claim_timeout:
            if self.adapter.withdraw(turn['id']):
                self.finish(turn, failed('First Mate did not claim the request within the transport timeout'))
        # A claimed turn has no total execution timeout.
