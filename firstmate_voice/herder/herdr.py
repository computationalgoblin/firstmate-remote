"""Bounded JSON-line RPC. Never scrape terminal output or invoke a shell."""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Protocol


class Control(Protocol):
    async def get(self, pane: str) -> dict: ...
    async def cancel(self, pane: str) -> None: ...


class HerdrClient:
    def __init__(self, socket: Path, timeout: float = 5):
        self.socket = socket
        self.timeout = timeout

    async def rpc(self, method: str, params: dict) -> dict:
        async with asyncio.timeout(self.timeout):
            reader, writer = await asyncio.open_unix_connection(str(self.socket), limit=1024 * 1024)
            try:
                request_id = uuid.uuid4().hex
                writer.write((json.dumps({'id': request_id, 'method': method, 'params': params}) + '\n').encode())
                await writer.drain()
                response = json.loads(await reader.readline())
                if not isinstance(response, dict) or response.get('id') != request_id:
                    raise ValueError('Invalid Herdr response identity')
                if 'error' in response:
                    raise OSError('Herdr RPC rejected: ' + json.dumps(response['error']))
                if not isinstance(response.get('result'), dict):
                    raise ValueError('Invalid Herdr result')
                return response['result']
            finally:
                writer.close()
                await writer.wait_closed()

    async def get(self, pane: str) -> dict:
        result = await self.rpc('agent.get', {'target': pane})
        agent = result.get('agent')
        if not isinstance(agent, dict) or agent.get('pane_id') != pane:
            raise ValueError('Herdr returned another pane')
        return agent

    async def cancel(self, pane: str) -> None:
        await self.rpc('agent.send_keys', {'target': pane, 'keys': ['esc']})
