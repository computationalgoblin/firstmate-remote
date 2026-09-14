import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from firstmate_voice.config import Config
from firstmate_voice.domain import parse_answer, State
from firstmate_voice.herder.adapter import HerderAdapter, atomic_json
from tests.helpers import config, FakeControl


class ConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_refuses_binding_pane_socket_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = config(Path(temp))
            adapter = HerderAdapter(cfg, FakeControl())
            binding = cfg.home / 'state/voice/binding.json'
            binding.parent.mkdir(parents=True)
            atomic_json(binding, {'version': 1, 'pid': os.getpid()})
            for env in (b'HERDR_PANE_ID=wrong\0', b'HERDR_PANE_ID=w1:p1\0HERDR_SOCKET_PATH=/wrong\0'):
                with patch.object(Path, 'read_bytes', return_value=env):
                    with self.assertRaises(ValueError):
                        await adapter.health()

    def test_required_and_finite_configuration(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            path = Path(temp) / 'config.toml'
            path.write_text('')
            with self.assertRaises(ValueError):
                Config.load(path)
            base = '\n'.join(['firstmate_home="~/test-home"', 'database="~/test.sqlite3"',
                             'herdr_socket="~/test.sock"', 'herdr_session="test"', 'herdr_pane="w1:p1"'])
            for value in ('nan', 'inf', '0', '-1'):
                path.write_text(base + '\npoll_interval=' + value)
                with self.assertRaises(ValueError):
                    Config.load(path)
            path.write_text(base)
            with patch.dict(os.environ, {'FM_HOME': temp}):
                self.assertEqual(Config.load(path).home, Path(temp))

    def test_only_final_structured_fields_become_voice(self):
        raw = 'INTERNAL LOG\n```json\n{"spoken_response":"Listo.","full_response":"Detalle.","needs_input":false,"question":""}\n```'
        outcome = parse_answer(raw)
        self.assertEqual(outcome.state, State.COMPLETED)
        self.assertEqual(outcome.spoken_response, 'Listo.')
        self.assertNotIn('INTERNAL LOG', outcome.full_response)
