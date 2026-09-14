import asyncio
import json
import os
import re
import urllib.request
from urllib.parse import urlsplit

from .base import Notification


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NtfyNotifier:
    def __init__(self, server: str, topic: str, token: str = '', timeout: float = 5):
        url = urlsplit(server)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('ntfy requires an HTTPS server URL without credentials/query/fragment')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', topic):
            raise ValueError('Invalid or missing ntfy topic')
        if timeout <= 0:
            raise ValueError('ntfy timeout must be positive')
        self.server, self.topic, self.token, self.timeout = server.rstrip('/') + '/', topic, token, timeout

    @classmethod
    def from_config(cls, config):
        def secret(key):
            name = config.get(key + '_env', '')
            value = os.environ.get(name, '')
            if name and not value:
                raise ValueError(f'Missing notification environment variable for {key}')
            return value
        return cls(config.get('server', ''), secret('topic'), secret('token'), float(config.get('timeout', 5)))

    def publish(self, notification: Notification):
        body = json.dumps({'topic': self.topic, 'title': 'First Mate: ' + notification.event_type,
                           'message': notification.message}).encode()
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.server, data=body, headers=headers, method='POST')
        with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise OSError('ntfy rejected notification')

    async def notify(self, notification: Notification):
        await asyncio.to_thread(self.publish, notification)
