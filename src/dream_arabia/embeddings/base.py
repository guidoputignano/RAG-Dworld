"""Embedder interface + factory.

Three backends behind one interface so the whole pipeline runs offline by
default and upgrades by config:

- ``fake``  — deterministic hashing embedder (no deps, no network; CI default).
- ``local`` — sentence-transformers (free, offline after first model download).
- ``openrouter`` — OpenAI-compatible embeddings endpoint (network + key).

Selected via ``DREAM_EMBED_PROVIDER`` (see ``.env.example``).
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (len(texts), dim) float32 array of embeddings."""
        ...


def embed_one(embedder: Embedder, text: str) -> np.ndarray:
    return embedder.embed([text])[0]


def l2_normalize(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def get_embedder(provider: str | None = None, model: str | None = None, env: dict | None = None) -> Embedder:
    env = env if env is not None else os.environ
    provider = (provider or env.get("DREAM_EMBED_PROVIDER") or "fake").lower()
    model = model or env.get("DREAM_EMBED_MODEL") or "sentence-transformers/all-MiniLM-L6-v2"
    if provider == "fake":
        from .fake import FakeEmbedder
        return FakeEmbedder()
    if provider == "local":
        from .local import LocalEmbedder
        return LocalEmbedder(model=model)
    if provider == "openrouter":
        from .openrouter import OpenRouterEmbedder
        return OpenRouterEmbedder(model=model, env=env)
    raise ValueError(f"Unknown embedding provider: {provider!r}")
