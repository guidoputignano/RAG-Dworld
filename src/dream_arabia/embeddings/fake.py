"""Deterministic hashing embedder — offline, reproducible, no dependencies.

Bag-of-hashed-tokens projected into a fixed-dimensional space, L2-normalised so
dot product == cosine similarity. It is not semantically deep, but texts that
share vocabulary score higher — enough to drive and test namespace-filtered
retrieval with zero network and zero model download.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

from .base import l2_normalize

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class FakeEmbedder:
    name = "fake"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _hash(self, token: str) -> int:
        h = hashlib.sha1(token.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big")

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = _tokens(text)
            if not toks:
                continue
            for tok in toks:
                hv = self._hash(tok)
                idx = hv % self.dim
                sign = 1.0 if (hv >> 16) & 1 else -1.0  # signed hashing reduces collisions
                out[i, idx] += sign
        return l2_normalize(out)
