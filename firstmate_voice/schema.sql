-- Migration 1. Applied transactionally using PRAGMA user_version.
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE jobs (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, home TEXT NOT NULL,
 voice_session_id TEXT NOT NULL, prompt TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','running','waiting_for_input','completed','failed','cancelled')),
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 spoken_response TEXT NOT NULL DEFAULT '', full_response TEXT NOT NULL DEFAULT '',
 question TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE turns (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 job_id TEXT NOT NULL REFERENCES jobs(id), request_id TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('request','reply')), prompt TEXT NOT NULL,
 phase TEXT NOT NULL CHECK(phase IN ('queued','dispatching','sent','claimed','finished')),
 identity TEXT, submitted_at REAL, cancel_sent INTEGER NOT NULL DEFAULT 0,
 spoken_response TEXT NOT NULL DEFAULT '', full_response TEXT NOT NULL DEFAULT '',
 question TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX one_active_turn_per_job ON turns(job_id) WHERE phase != 'finished';
CREATE TABLE events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
 turn_id TEXT, at REAL NOT NULL, channel TEXT NOT NULL CHECK(channel IN ('user','internal')),
 type TEXT NOT NULL, payload TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX events_outbox ON events(channel, notified, id);
