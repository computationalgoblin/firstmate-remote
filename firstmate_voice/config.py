"""Explicit local configuration; no production session or notification defaults."""
import os
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path
    database: Path
    socket: Path
    pane: str
    session: str
    transport_timeout: float = 5
    claim_timeout: float = 15
    poll_interval: float = 0.25
    notifications: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Config":
        with path.expanduser().open("rb") as f:
            data = tomllib.load(f)
        def required(key, env):
            value = os.environ.get(env) or data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Configure {key} or {env}")
            return value
        cfg = cls(
            Path(required("firstmate_home", "FM_HOME")).expanduser().resolve(),
            Path(required("database", "FMVOICE_DATABASE")).expanduser().resolve(),
            Path(required("herdr_socket", "FMVOICE_HERDR_SOCKET")).expanduser().resolve(),
            required("herdr_pane", "FMVOICE_HERDR_PANE"),
            required("herdr_session", "FMVOICE_HERDR_SESSION"),
            float(data.get("transport_timeout", 5)), float(data.get("claim_timeout", 15)),
            float(data.get("poll_interval", 0.25)), data.get("notifications", {}),
        )
        if any(not math.isfinite(v) or v <= 0 for v in
               (cfg.transport_timeout, cfg.claim_timeout, cfg.poll_interval)):
            raise ValueError("Timeouts and poll_interval must be positive")
        return cfg
