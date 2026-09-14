"""Foreground service suitable for systemd --user, with one lock per canonical home."""
import asyncio
import fcntl
import json
import os
import signal
from contextlib import contextmanager

from .herder.adapter import HerderAdapter
from .herder.herdr import HerdrClient
from .manager import JobManager
from .notifications.dispatcher import Dispatcher
from .notifications.ntfy import NtfyNotifier
from .repository import Repository


@contextmanager
def home_lock(config):
    directory = config.home / 'state/voice'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / 'fmvoice-worker.lock'
    with path.open('a+', encoding='utf-8') as f:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A worker already owns this First Mate home') from None
        f.seek(0)
        owner = f.read().strip()
        if owner and json.loads(owner)['database'] != str(config.database):
            raise ValueError('This home belongs to another database; reconcile before moving it')
        f.seek(0)
        f.truncate()
        json.dump({'database': str(config.database), 'pid': os.getpid()}, f)
        f.flush()
        os.fsync(f.fileno())
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def worker_running(config):
    path = config.home / 'state/voice/fmvoice-worker.lock'
    try:
        with path.open('r') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError:
        pass
    return False


async def serve(config):
    notifier = None
    if config.notifications.get('enabled', False):
        if config.notifications.get('provider', 'ntfy') != 'ntfy':
            raise ValueError('Unsupported notification provider')
        notifier = NtfyNotifier.from_config(config.notifications)
    with home_lock(config):
        repo = Repository(config.database, config.home)
        manager = JobManager(repo, HerderAdapter(config, HerdrClient(config.socket, config.transport_timeout)), config.claim_timeout)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        async def notification_loop():
            dispatcher = Dispatcher(repo, notifier)
            while not stop.is_set():
                await dispatcher.tick()
                try:
                    await asyncio.wait_for(stop.wait(), 5)
                except TimeoutError:
                    pass

        task = asyncio.create_task(notification_loop()) if notifier else None
        try:
            while not stop.is_set():
                await manager.tick()
                if task and task.done():
                    task.result()
                try:
                    await asyncio.wait_for(stop.wait(), config.poll_interval)
                except TimeoutError:
                    pass
        finally:
            stop.set()
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            repo.close()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
