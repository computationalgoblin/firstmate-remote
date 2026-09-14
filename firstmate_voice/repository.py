"""SQLite transactions shared by short-lived CLI clients and the worker."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .domain import State, TERMINAL, Outcome, validate_transition, transcript


class Repository:
    def __init__(self, path: Path, home: Path, *, timeout=10):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.touch(mode=0o600, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=timeout, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.home = str(home.resolve())
            with self.transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    for statement in Path(__file__).with_name("schema.sql").read_text().split(';'):
                        if statement.strip():
                            self.db.execute(statement)
                    self.db.execute("PRAGMA user_version=1")
                elif version != 1:
                    raise ValueError(f"Unsupported database version {version}")
                self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('home',?)", (self.home,))
                if self.db.execute("SELECT value FROM metadata WHERE key='home'").fetchone()[0] != self.home:
                    raise ValueError("Database belongs to a different First Mate home")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, job_id, event_type, payload, *, turn_id=None, channel="user"):
        self.db.execute("INSERT INTO events(job_id,turn_id,at,channel,type,payload) VALUES (?,?,?,?,?,?)",
                        (job_id, turn_id, time.time(), channel, event_type, json.dumps(payload, ensure_ascii=False)))

    def get(self, job_id):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown job")
        return dict(row)

    def jobs(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM jobs ORDER BY created_at,id")]

    def pending_input(self, limit=101):
        # One snapshot includes the revision, so a subsequent question can never
        # inherit a reply selected from an older pending-input response.
        return [dict(r) for r in self.db.execute(
            "SELECT jobs.*, (SELECT MAX(seq) FROM turns WHERE job_id=jobs.id) AS input_revision "
            "FROM jobs WHERE state=? ORDER BY created_at,id LIMIT ?", (State.WAITING, limit))]

    def input_revision(self, job_id):
        return self.db.execute("SELECT MAX(seq) FROM turns WHERE job_id=?", (job_id,)).fetchone()[0]

    def turns(self, job_id):
        return [dict(r) for r in self.db.execute("SELECT * FROM turns WHERE job_id=? ORDER BY seq", (job_id,))]

    def events(self, job_id, internal=False):
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in self.db.execute(
            "SELECT * FROM events WHERE job_id=? AND (? OR channel='user') ORDER BY id", (job_id, internal))]

    def transition(self, job_id, state):
        validate_transition(self.get(job_id)["state"], state)
        self.db.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=?", (state, time.time(), job_id))

    def enqueue(self, prompt, request_id, *, job_id=None, voice_session_id=None, input_revision=None):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must not be empty")
        if not isinstance(request_id, str) or not 0 < len(request_id) <= 200:
            raise ValueError("request_id must contain 1–200 characters")
        with self.transaction():
            existing = self.db.execute("SELECT job_id,kind FROM turns WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if ((job_id and existing['job_id'] != job_id)
                        or existing['kind'] != ('reply' if job_id else 'request')):
                    raise ValueError("request_id already belongs to another operation")
                return self.get(existing['job_id'])
            kind = "reply" if job_id else "request"
            job_id = job_id or str(uuid.uuid4())
            if kind == "reply":
                job = self.get(job_id)
                if job['state'] != State.WAITING:
                    raise ValueError("Job is not waiting for input")
                if input_revision is not None and input_revision != self.input_revision(job_id):
                    raise ValueError("Question changed")
                voice_session_id = job['voice_session_id']
                self.transition(job_id, State.QUEUED)
                self.db.execute("UPDATE jobs SET spoken_response='',full_response='',question='',error='' WHERE id=?", (job_id,))
            else:
                voice_session_id = voice_session_id or str(uuid.uuid4())
                if not isinstance(voice_session_id, str) or not 0 < len(voice_session_id) <= 200:
                    raise ValueError("Invalid voice_session_id")
                now = time.time()
                self.db.execute("INSERT INTO jobs(id,request_id,home,voice_session_id,prompt,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                                (job_id, request_id, self.home, voice_session_id, prompt, State.QUEUED, now, now))
            wrapped = transcript(prompt, job_id, voice_session_id, kind)
            if len(wrapped.encode()) > 16384:
                raise ValueError("Wrapped prompt exceeds voice contract limit of 16384 bytes")
            turn_id = "fmr-" + uuid.uuid4().hex
            self.db.execute("INSERT INTO turns(id,job_id,request_id,kind,prompt,phase) VALUES (?,?,?,?,?,'queued')",
                            (turn_id, job_id, request_id, kind, wrapped))
            self.event(job_id, "accepted", {"spoken_response": "Petición encolada."}, turn_id=turn_id)
            return self.get(job_id)

    def cancel(self, job_id):
        with self.transaction():
            job = self.get(job_id)
            if job['state'] in TERMINAL:
                return job
            if job['state'] == State.RUNNING:
                self.db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
            else:
                self.finish(job_id, None, Outcome(State.CANCELLED, "Petición cancelada."))
            return self.get(job_id)

    def active(self):
        row = self.db.execute("SELECT * FROM turns WHERE phase IN ('dispatching','sent','claimed') ORDER BY seq LIMIT 1").fetchone()
        return dict(row) if row else None

    def start_next(self):
        with self.transaction():
            if self.active():
                return self.active()
            row = self.db.execute("SELECT * FROM turns WHERE phase='queued' ORDER BY seq LIMIT 1").fetchone()
            if not row:
                return None
            self.transition(row['job_id'], State.RUNNING)
            self.db.execute("UPDATE turns SET phase='dispatching' WHERE id=?", (row['id'],))
            self.event(row['job_id'], "working", {}, turn_id=row['id'])
            return dict(row) | {"phase": "dispatching"}

    def update_turn(self, turn_id, **fields):
        allowed = {'phase', 'identity', 'submitted_at', 'cancel_sent'}
        if not fields or fields.keys() - allowed:
            raise ValueError("Invalid turn fields")
        self.db.execute(f"UPDATE turns SET {','.join(k+'=?' for k in fields)} WHERE id=?", (*fields.values(), turn_id))

    def finish(self, job_id, turn_id, outcome):
        # Caller owns the transaction: result, state, and outbox commit together.
        self.transition(job_id, outcome.state)
        values = (outcome.spoken_response, outcome.full_response, outcome.question, outcome.error)
        self.db.execute("UPDATE jobs SET spoken_response=?,full_response=?,question=?,error=? WHERE id=?", (*values, job_id))
        self.db.execute("UPDATE turns SET phase='finished',spoken_response=?,full_response=?,question=?,error=? WHERE job_id=? AND phase!='finished'", (*values, job_id))
        event_type = 'needs_input' if outcome.state == State.WAITING else outcome.state
        self.event(job_id, event_type, dict(zip(('spoken_response','full_response','question','error'), values)), turn_id=turn_id)
