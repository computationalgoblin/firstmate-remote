import json
import os
from pathlib import Path

from firstmate_voice.config import Config
from firstmate_voice.herder.adapter import HerderAdapter, atomic_json


def config(root):
    home = root / 'home'
    home.mkdir()
    return Config(home, root / 'jobs.sqlite3', root / 'herdr.sock', 'w1:p1', 'test', poll_interval=0.01)


class FakeControl:
    def __init__(self):
        self.cancels = 0
        self.state = 'idle'
        self.session = 'private-session-reference'
        self.error = None

    async def get(self, pane):
        if self.error:
            raise self.error
        return {'pane_id': pane, 'agent_status': self.state,
                'agent_session': {'kind': 'path', 'value': self.session}}

    async def cancel(self, pane):
        self.cancels += 1


class FakeAdapter(HerderAdapter):
    async def health(self):
        agent = await self.control.get(self.config.pane)
        return {'pane': self.config.pane, 'agent_session': agent['agent_session'],
                'agent_status': agent['agent_status']}


def claim(adapter, turn):
    os.rename(adapter.path(turn['id'], 'request'), adapter.path(turn['id'], 'claimed'))


def result(adapter, turn, *, needs_input=False, error=None, raw=None):
    kind = 'error' if error is not None else 'answer'
    answer = raw if raw is not None else json.dumps({'spoken_response': 'Resultado breve.',
             'full_response': 'Detalle del resultado.', 'needs_input': needs_input,
             'question': '¿Qué color?' if needs_input else ''})
    atomic_json(adapter.path(turn['id'], kind), {'version': 1, 'id': turn['id'], kind: error if error is not None else answer})
    adapter.path(turn['id'], 'claimed').unlink(missing_ok=True)
