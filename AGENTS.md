# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Integration authority and recovery constraints: `docs/integration.md`; the real request/response channel is First Mate’s v1 voice-file contract, not Herdr terminal output.
- Install/run/test commands: `README.md`. Offline suite: `python3 -m unittest discover -v`. The live smoke requires explicit opt-in and the authorized Herdr laboratory helper; never target the fleet’s default session from a test.
- Keep `spoken_response`/question separate from full responses and internal diagnostics; notifications must consume only the safe fields. No changes to First Mate or Herdr core are part of this package.

- HTTP deployment/public contract, including the read-only cursor feed: `docs/http-api.md`; iPhone construction and hardware validation: `docs/ios-shortcut.md`. Gateway health only checks persistence; execution remains in the worker. Voice cursors advance locally after speech; ntfy delivery never acknowledges listening.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
