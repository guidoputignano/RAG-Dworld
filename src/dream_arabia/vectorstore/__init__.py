"""Vector store (Phase 5): in-memory NumPy index (+ pgvector adapter)."""
from .base import VectorStore, SearchHit, get_vector_store
from .memory import MemoryVectorStore

__all__ = ["VectorStore", "SearchHit", "get_vector_store", "MemoryVectorStore"]
