import asyncio
import json
import os
import re
import urllib.request
from urllib.parse import urlsplit

from .base import Notification

READ_SHORTCUT_URL = 'shortcuts://run-shortcut?name=Leer%20First%20Mate'
RESPOND_SHORTCUT_URL = 'shortcuts://run-shortcut?name=First%20Mate%20Responder'
# `auto` opens Responder for questions and Leer for everything else.
CLICK_MODES = ('', READ_SHORTCUT_URL, 'auto')
# Fixed presentation per event type: title, ntfy priority (1–5) and emoji tags.
PRESENTATION = {
    'needs_input': ('First Mate pregunta', 4, ['question']),
    'completed': ('First Mate: listo', 3, ['white_check_mark']),
    'failed': ('First Mate: error', 4, ['warning']),
    'cancelled': ('First Mate: cancelado', 2, ['no_entry_sign']),
}
DEFAULT_PRESENTATION = ('First Mate', 3, [])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NtfyNotifier:
    def __init__(self, server: str, topic: str, token: str = '', timeout: float = 5, *, click: str = ''):
        # Exact allowlist: no secrets, input text, arbitrary URLs or interpolation.
        if not isinstance(click, str) or click not in CLICK_MODES:
            raise ValueError('Invalid ntfy click; use "auto", the fixed Leer First Mate URL or an empty string')
        self.click = click
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
        if not isinstance(config, dict) or config.keys() - {
                'provider', 'enabled', 'server', 'topic_env', 'token_env', 'timeout', 'click'}:
            raise ValueError('Invalid notification configuration fields')
        def secret(key):
            name = config.get(key + '_env', '')
            value = os.environ.get(name, '')
            if name and not value:
                raise ValueError(f'Missing notification environment variable for {key}')
            return value
        return cls(config.get('server', ''), secret('topic'), secret('token'), float(config.get('timeout', 5)),
                   click=config.get('click', ''))

    def publish(self, notification: Notification):
        title, priority, tags = PRESENTATION.get(notification.event_type, DEFAULT_PRESENTATION)
        payload = {'topic': self.topic, 'title': title, 'message': notification.message, 'priority': priority}
        if tags:
            payload['tags'] = tags
        if self.click == 'auto':
            payload['click'] = RESPOND_SHORTCUT_URL if notification.event_type == 'needs_input' else READ_SHORTCUT_URL
        elif self.click:
            payload['click'] = self.click
        body = json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.server, data=body, headers=headers, method='POST')
        with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise OSError('ntfy rejected notification')

    async def notify(self, notification: Notification):
        await asyncio.to_thread(self.publish, notification)
