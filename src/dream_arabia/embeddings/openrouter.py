"""OpenAI-compatible embeddings client (OpenRouter / OpenAI). Network + key."""
from __future__ import annotations

import os

import numpy as np

from .base import l2_normalize


class OpenRouterEmbedder:
    name = "openrouter"

    def __init__(self, model: str = "openai/text-embedding-3-small", env: dict | None = None):
        env = env if env is not None else os.environ
        self.model = model
        self.base_url = (env.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.api_key = env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY") or ""
        self.dim = 1536  # text-embedding-3-small default

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - needs network
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set for openrouter embeddings")
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        vecs = np.array([d["embedding"] for d in data], dtype=np.float32)
        self.dim = vecs.shape[1]
        return l2_normalize(vecs)
