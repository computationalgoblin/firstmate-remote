"""Version-1 First Mate voice contract; only final answer/error files carry content."""
import json
import os
import time
import uuid
from pathlib import Path

from ..config import Config
from ..domain import failed, parse_answer
from .herdr import Control


class IdentityChanged(Exception):
    pass


def read_json(path: Path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Voice record exceeds 1 MiB')
    return json.loads(path.read_text())


def atomic_json(path: Path, value: dict):
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temp.open('x', encoding='utf-8') as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, ensure_ascii=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


class HerderAdapter:
    def __init__(self, config: Config, control: Control):
        self.config, self.control = config, control
        self.directory = config.home / 'state/voice/turns'

    def path(self, turn_id, suffix):
        if not turn_id.startswith('fmr-') or not turn_id[4:].isalnum():
            raise ValueError('Invalid owned turn id')
        return self.directory / f'{turn_id}.{suffix}.json'

    def binding(self):
        value = read_json(self.config.home / 'state/voice/binding.json')
        if not isinstance(value, dict) or value.get('version') != 1 or type(value.get('pid')) is not int or value['pid'] <= 1:
            raise ValueError('Invalid voice binding')
        os.kill(value['pid'], 0)
        return value

    async def health(self):
        binding = self.binding()
        # Bind the configured target to the voice primary, not merely any Pi pane.
        env = dict(item.split(b'=', 1) for item in
                   Path(f"/proc/{binding['pid']}/environ").read_bytes().split(b'\0') if b'=' in item)
        if env.get(b'HERDR_PANE_ID', b'').decode() != self.config.pane:
            raise ValueError('Configured pane does not own the voice binding')
        socket = env.get(b'HERDR_SOCKET_PATH', b'').decode()
        if not socket or Path(socket).resolve() != self.config.socket:
            raise ValueError('Configured socket does not own the voice binding')
        agent = await self.control.get(self.config.pane)
        session = agent.get('agent_session')
        if not isinstance(session, dict) or not session.get('value') or session.get('kind') not in ('path', 'id'):
            raise ValueError('Herdr has no stable agent session identity')
        return {'binding': binding, 'pane': self.config.pane, 'socket': str(self.config.socket),
                'herdr_session': self.config.session, 'agent_session': session,
                'agent_status': agent.get('agent_status', 'unknown')}

    @staticmethod
    def identity(health):
        return json.dumps({k: v for k, v in health.items() if k != 'agent_status'}, sort_keys=True)

    async def check_identity(self, identity):
        health = await self.health()
        if self.identity(health) != identity:
            raise IdentityChanged('The First Mate session changed')
        return health

    def foreign_inflight(self):
        # Cooperate with desktop PTT where observable; upstream remains final arbiter.
        return any(self.directory.glob('*.request.json')) or any(self.directory.glob('*.claimed.json'))

    async def submit(self, turn, identity):
        await self.check_identity(identity)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.recover(turn['id']):
            return
        atomic_json(self.path(turn['id'], 'request'), {'version': 1, 'id': turn['id'],
                    'transcript': turn['prompt'], 'requestedAt': int(time.time())})

    async def send_input(self, turn, identity):
        await self.submit(turn, identity)

    def recover(self, turn_id):
        return {kind for kind in ('request', 'claimed', 'answer', 'error') if self.path(turn_id, kind).exists()}

    def outcome(self, turn_id):
        for kind in ('error', 'answer'):
            path = self.path(turn_id, kind)
            if not path.exists():
                continue
            try:
                value = read_json(path)
                if not isinstance(value, dict) or value.get('id') != turn_id or value.get('version') != 1 or not isinstance(value.get(kind), str):
                    raise ValueError('Invalid voice result record')
                return failed(value['error']) if kind == 'error' else parse_answer(value['answer'])
            except (ValueError, UnicodeError):
                return failed('Malformed voice result; raw record withheld from user events')
        return None

    def withdraw(self, turn_id):
        # Atomic race against the extension's request -> claimed rename.
        try:
            os.rename(self.path(turn_id, 'request'), self.path(turn_id, 'withdrawn'))
            return True
        except FileNotFoundError:
            return False

    async def cancel(self, identity, turn_id):
        await self.check_identity(identity)
        # The turn may settle during the identity RPC. Re-read before Escape.
        files = self.recover(turn_id)
        if 'answer' in files or 'error' in files or 'claimed' not in files:
            return
        await self.control.cancel(self.config.pane)
