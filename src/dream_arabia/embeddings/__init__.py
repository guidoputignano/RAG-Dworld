"""Embeddings (Phase 5): pluggable providers behind one interface."""
from .base import Embedder, get_embedder, embed_one, l2_normalize
from .fake import FakeEmbedder

__all__ = ["Embedder", "get_embedder", "embed_one", "l2_normalize", "FakeEmbedder"]
