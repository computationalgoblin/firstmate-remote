from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Notification:
    event_id: int
    job_id: str
    event_type: str
    message: str


class Notifier(Protocol):
    async def notify(self, notification: Notification) -> None: ...
