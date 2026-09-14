"""Short-lived administrative clients; submit/reply/cancel only touch SQLite."""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

from .config import Config
from .herder.adapter import HerderAdapter
from .herder.herdr import HerdrClient
from .repository import Repository
from .worker import serve, worker_running


def parser():
    p = argparse.ArgumentParser(prog='fmvoice')
    p.add_argument('--config', type=Path, default=Path(os.environ.get('FMVOICE_CONFIG', '~/.config/fmvoice/config.toml')))
    sub = p.add_subparsers(dest='command', required=True)
    submit = sub.add_parser('submit')
    submit.add_argument('prompt')
    submit.add_argument('--request-id', default=None)
    submit.add_argument('--voice-session-id')
    sub.add_parser('jobs')
    status = sub.add_parser('status')
    status.add_argument('job_id', nargs='?')
    show = sub.add_parser('show')
    show.add_argument('job_id')
    show.add_argument('--internal', action='store_true', help='Include private transport diagnostics and turn identities')
    reply = sub.add_parser('reply')
    reply.add_argument('job_id')
    reply.add_argument('prompt')
    reply.add_argument('--request-id', default=None)
    cancel = sub.add_parser('cancel')
    cancel.add_argument('job_id')
    sub.add_parser('worker')
    sub.add_parser('gateway', help='Run the authenticated HTTP submission service')
    sub.add_parser('health')
    return p


def public_job(job):
    return {k: v for k, v in job.items() if k != 'home'}


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    repo = None
    try:
        config = Config.load(args.config)
        if args.command == 'gateway':
            from .gateway import serve as serve_gateway
            serve_gateway(config)
            return 0
        if args.command == 'worker':
            asyncio.run(serve(config))
            return 0
        if args.command == 'health':
            value = asyncio.run(HerderAdapter(config, HerdrClient(config.socket, config.transport_timeout)).health())
            value['worker_running'] = worker_running(config)
        else:
            repo = Repository(config.database, config.home)
            if args.command == 'submit':
                value = public_job(repo.enqueue(args.prompt, args.request_id or str(uuid.uuid4()), voice_session_id=args.voice_session_id))
            elif args.command == 'reply':
                value = public_job(repo.enqueue(args.prompt, args.request_id or str(uuid.uuid4()), job_id=args.job_id))
            elif args.command == 'cancel':
                value = public_job(repo.cancel(args.job_id))
            elif args.command == 'jobs':
                value = [public_job(j) for j in repo.jobs()]
            elif args.command == 'status':
                value = public_job(repo.get(args.job_id)) if args.job_id else {'worker_running': worker_running(config), 'jobs': len(repo.jobs())}
            else:
                value = public_job(repo.get(args.job_id))
                value['events'] = repo.events(args.job_id, args.internal)
                if args.internal:
                    value['turns'] = repo.turns(args.job_id)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, TimeoutError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if repo:
            repo.close()


if __name__ == '__main__':
    sys.exit(main())
