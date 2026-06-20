"""Local embedder via sentence-transformers (optional dependency, lazy import)."""
from __future__ import annotations

import numpy as np

from .base import l2_normalize


class LocalEmbedder:
    name = "local"

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model
        self._model = None
        self.dim = 384  # all-MiniLM-L6-v2; refined after load

    def _ensure(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "`pip install dream-arabia[embeddings]` or set DREAM_EMBED_PROVIDER=fake"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
            self.dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - needs model
        model = self._ensure()
        vecs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=False)
        return l2_normalize(np.asarray(vecs, dtype=np.float32))
