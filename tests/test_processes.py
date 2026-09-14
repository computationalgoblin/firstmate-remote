import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class ProcessTest(unittest.TestCase):
    def test_cli_exit_and_worker_restart_preserve_inflight_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = root / 'config.toml'
            cfg.write_text('\n'.join([
                f'firstmate_home = {json.dumps(str(root / "home"))}',
                f'database = {json.dumps(str(root / "jobs.sqlite3"))}',
                f'herdr_socket = {json.dumps(str(root / "herdr.sock"))}',
                'herdr_pane = "w1:p1"', 'herdr_session = "offline-test"',
                'poll_interval = 0.01', 'transport_timeout = 1']))
            env = dict(os.environ, HERDR_PANE_ID='w1:p1', HERDR_SOCKET_PATH=str(root / 'herdr.sock'))
            # Production FM_HOME/config overrides must never escape the temp fixture.
            for key in list(env):
                if key == 'FM_HOME' or key.startswith('FMVOICE_'):
                    del env[key]
            def cli(*args):
                run = subprocess.run([sys.executable, '-m', 'firstmate_voice.cli', '--config', str(cfg), *args],
                                     env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                return json.loads(run.stdout)
            def wait_for(condition):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if condition():
                        return
                    time.sleep(0.02)
                self.fail('Offline process fixture did not reach expected state')
            def start_worker():
                return subprocess.Popen([sys.executable, '-m', 'firstmate_voice.cli', '--config', str(cfg), 'worker'], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def stop(process):
                if process.poll() is None:
                    process.terminate()
                stdout, stderr = process.communicate(timeout=8)
                return process.returncode, stdout, stderr
            fake = subprocess.Popen([sys.executable, '-m', 'tests.fake_voice_process', str(root)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            worker = None
            try:
                wait_for(lambda: (root / 'ready').exists())
                job = cli('submit', 'literal $(touch forbidden); `echo nope`', '--request-id', 'stable')
                self.assertEqual(job['state'], 'queued')
                self.assertFalse(cli('status')['worker_running'])
                worker = start_worker()
                wait_for(lambda: list((root / 'home/state/voice/turns').glob('*.claimed.json')))
                self.assertTrue(cli('health')['worker_running'])
                code, _, err = stop(worker)
                self.assertEqual(code, 0, err)
                self.assertEqual(cli('status', job['id'])['state'], 'running')
                self.assertEqual(cli('submit', 'retry', '--request-id', 'stable')['id'], job['id'])
                worker = start_worker()
                (root / 'release').touch()
                wait_for(lambda: cli('status', job['id'])['state'] == 'completed')
                shown = cli('show', job['id'])
                self.assertEqual(shown['spoken_response'], 'Listo.')
                self.assertEqual(shown['full_response'], 'Detalle persistente.')
                self.assertEqual(len(cli('show', job['id'], '--internal')['turns']), 1)
                self.assertEqual(len(cli('jobs')), 1)
                code, _, err = stop(worker)
                self.assertEqual(code, 0, err)
            finally:
                if worker:
                    stop(worker)
                stop(fake)
