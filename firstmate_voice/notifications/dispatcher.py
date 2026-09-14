"""Durable outbox consumer. A provider failure cannot change job state."""
import json
import logging

from .base import Notification, Notifier

NOTIFY = {'needs_input', 'completed', 'failed', 'cancelled'}


class Dispatcher:
    def __init__(self, repository, notifier: Notifier):
        self.repo, self.notifier = repository, notifier

    async def tick(self):
        rows = self.repo.db.execute("SELECT * FROM events WHERE channel='user' AND notified=0 ORDER BY id LIMIT 50").fetchall()
        for row in rows:
            if row['type'] in NOTIFY:
                payload = json.loads(row['payload'])
                message = payload['question'] if row['type'] == 'needs_input' else payload['spoken_response']
                try:
                    await self.notifier.notify(Notification(row['id'], row['job_id'], row['type'], message))
                except Exception:
                    # Do not log URLs, topics, tokens, or payloads from provider exceptions.
                    logging.warning('Notification delivery failed for event %s; will retry', row['id'])
                    return
            self.repo.db.execute('UPDATE events SET notified=1 WHERE id=?', (row['id'],))
