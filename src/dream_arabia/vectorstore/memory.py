"""In-memory NumPy vector store with cosine similarity + namespace filtering.

Vectors are stored L2-normalised, so cosine similarity is a single matrix-vector
dot product. At fixture/program scale (hundreds to low-thousands of nodes) this
is instant and needs no external service. The namespace filter is applied to the
``metadata['namespace']`` field so retrieval can be restricted to a persona's
entry namespaces.
"""
from __future__ import annotations

import numpy as np

from ..embeddings.base import l2_normalize
from .base import SearchHit


class MemoryVectorStore:
    def __init__(self):
        self._ids: list[str] = []
        self._meta: list[dict] = []
        self._vecs: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        vecs = l2_normalize(np.asarray(vectors, dtype=np.float32))
        if vecs.shape[0] != len(ids) or len(ids) != len(metadatas):
            raise ValueError("ids, vectors, and metadatas must be the same length")
        self._ids.extend(ids)
        self._meta.extend(metadatas)
        self._vecs = vecs if self._vecs is None else np.vstack([self._vecs, vecs])

    def search(
        self, query: np.ndarray, k: int = 5, namespaces: list[str] | None = None
    ) -> list[SearchHit]:
        if self._vecs is None or len(self._ids) == 0:
            return []
        q = l2_normalize(np.asarray(query, dtype=np.float32).reshape(1, -1))[0]
        sims = self._vecs @ q  # cosine, since all rows are normalised

        if namespaces is not None:
            allowed = set(namespaces)
            mask = np.array([m.get("namespace") in allowed for m in self._meta])
            if not mask.any():
                return []
            sims = np.where(mask, sims, -np.inf)

        k = min(k, int(np.isfinite(sims).sum()))
        if k <= 0:
            return []
        # top-k by score (descending)
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [
            SearchHit(id=self._ids[i], score=float(sims[i]), metadata=self._meta[i])
            for i in top
            if np.isfinite(sims[i])
        ]
