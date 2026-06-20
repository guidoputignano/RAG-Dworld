"""Vector store interface + factory.

Default ``memory`` (NumPy cosine index) for offline dev/test; ``pgvector`` slots
in behind the same interface for production scale (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class SearchHit:
    id: str
    score: float
    metadata: dict


class VectorStore(Protocol):
    def add(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        ...

    def search(
        self, query: np.ndarray, k: int = 5, namespaces: list[str] | None = None
    ) -> list[SearchHit]:
        ...


def get_vector_store(backend: str | None = None, env: dict | None = None) -> VectorStore:
    env = env if env is not None else os.environ
    backend = (backend or env.get("DREAM_VECTOR_STORE") or "memory").lower()
    if backend == "memory":
        from .memory import MemoryVectorStore
        return MemoryVectorStore()
    if backend == "pgvector":
        from .pgvector import PgVectorStore
        return PgVectorStore(dsn=env.get("PGVECTOR_DSN"))
    raise ValueError(f"Unknown vector store backend: {backend!r}")
