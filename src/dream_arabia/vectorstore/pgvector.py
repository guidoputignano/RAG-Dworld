"""pgvector adapter (production path).

Documented behind the same VectorStore interface as the in-memory store. Not
exercised in offline dev/CI; requires Postgres + the pgvector extension and a
DSN in ``PGVECTOR_DSN``. Implement when moving to production scale.
"""
from __future__ import annotations

import numpy as np

from .base import SearchHit


class PgVectorStore:  # pragma: no cover - production path, not run offline
    def __init__(self, dsn: str | None = None, table: str = "dream_nodes"):
        if not dsn:
            raise RuntimeError("PGVECTOR_DSN is required for the pgvector backend")
        self.dsn = dsn
        self.table = table
        raise NotImplementedError(
            "pgvector backend is a documented production path; use DREAM_VECTOR_STORE=memory "
            "for development. Wire psycopg + pgvector here when scaling."
        )

    def add(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        ...

    def search(self, query: np.ndarray, k: int = 5, namespaces: list[str] | None = None) -> list[SearchHit]:
        ...
