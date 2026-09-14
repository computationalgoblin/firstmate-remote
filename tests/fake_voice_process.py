"""Offline extension and Herdr socket double, used only by process integration tests."""
import asyncio
import json
import os
import sys
from pathlib import Path

from firstmate_voice.herder.adapter import atomic_json


async def main():
    root = Path(sys.argv[1])
    turns = root / 'home/state/voice/turns'
    turns.mkdir(parents=True, exist_ok=True)
    atomic_json(turns.parent / 'binding.json', {'version': 1, 'pid': os.getpid(), 'startedAt': 'test'})

    async def rpc(reader, writer):
        try:
            request = json.loads(await reader.readline())
            if request['method'] == 'agent.get':
                result = {'agent': {'pane_id': 'w1:p1', 'agent_status': 'idle',
                          'agent_session': {'kind': 'path', 'value': 'offline-pi-session'}}}
            elif request['method'] == 'agent.send_keys':
                for path in turns.glob('*.claimed.json'):
                    turn_id = path.name.split('.')[0]
                    atomic_json(turns / f'{turn_id}.error.json', {'version': 1, 'id': turn_id, 'error': 'cancelled'})
                    path.unlink()
                result = {'type': 'agent_keys_sent'}
            else:
                raise AssertionError(request['method'])
            writer.write((json.dumps({'id': request['id'], 'result': result}) + '\n').encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(rpc, str(root / 'herdr.sock'))
    (root / 'ready').touch()
    async with server:
        while True:
            for path in turns.glob('*.request.json'):
                value = json.loads(path.read_text())
                path.rename(turns / f"{value['id']}.claimed.json")
            if (root / 'release').exists():
                for path in turns.glob('*.claimed.json'):
                    value = json.loads(path.read_text())
                    answer = {'spoken_response': 'Listo.', 'full_response': 'Detalle persistente.',
                              'needs_input': False, 'question': ''}
                    atomic_json(turns / f"{value['id']}.answer.json", {'version': 1, 'id': value['id'], 'answer': json.dumps(answer)})
                    path.unlink()
            await asyncio.sleep(0.01)


asyncio.run(main())
