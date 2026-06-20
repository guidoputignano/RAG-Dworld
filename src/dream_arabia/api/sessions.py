"""Session store (Phase 7).

In-memory for now (single process). The ``SessionStore`` protocol marks the seam
where Redis goes for production / horizontal scale: implement ``RedisSessionStore``
serialising ``Session`` (persona, history, active_node_ids) to a Redis hash keyed
by session id, and select it via ``DREAM_SESSION_BACKEND=redis`` + ``REDIS_URL``.
"""
from __future__ import annotations

import os
import uuid
from typing import Protocol

from ..agent.core import Session


class SessionStore(Protocol):
    def create(self, session: Session) -> str: ...
    def get(self, session_id: str) -> Session | None: ...
    def save(self, session_id: str, session: Session) -> None: ...
    def delete(self, session_id: str) -> None: ...


class InMemorySessionStore:
    def __init__(self):
        self._store: dict[str, Session] = {}

    def create(self, session: Session) -> str:
        sid = uuid.uuid4().hex
        self._store[sid] = session
        return sid

    def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    def save(self, session_id: str, session: Session) -> None:
        self._store[session_id] = session

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._store)


def get_session_store(backend: str | None = None, env: dict | None = None) -> SessionStore:
    env = env if env is not None else os.environ
    backend = (backend or env.get("DREAM_SESSION_BACKEND") or "memory").lower()
    if backend == "memory":
        return InMemorySessionStore()
    if backend == "redis":  # pragma: no cover - production path
        raise NotImplementedError(
            "Redis session store is the documented production seam. Implement "
            "RedisSessionStore (serialise Session to a Redis hash) and set REDIS_URL."
        )
    raise ValueError(f"Unknown session backend: {backend!r}")
