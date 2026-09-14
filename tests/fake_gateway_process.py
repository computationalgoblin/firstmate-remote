"""Run the real gateway CLI with an ephemeral-port readiness hook for tests."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

from firstmate_voice.cli import main
from firstmate_voice.gateway import Gateway

root = Path(sys.argv[1])
activate = Gateway.server_activate


def announce(server):
    activate(server)
    # stdout is only a fixture readiness channel, not an application access log.
    print(json.dumps({'port': server.server_address[1]}), flush=True)


with patch.object(Gateway, 'server_activate', announce):
    sys.exit(main(['--config', str(root / 'config.toml'), 'gateway']))
