"""Graph query engine (Phase 5).

Loads the federated graph once and exposes the three operations the agent needs
(per the spec), upgraded from keyword matching to vector retrieval:

- ``get_nodes_by_namespace`` — all nodes for a source.
- ``semantic_search`` — top-k nodes by embedding similarity, with a namespace
  filter (a persona's entry namespaces) — but it's a filter on *search*, not a
  wall: ``traverse`` still follows edges into other namespaces.
- ``traverse`` — BFS from a set of start nodes up to ``max_hops``, following
  cross-entity edges across sources.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

from ..embeddings.base import Embedder, get_embedder
from ..vectorstore.base import VectorStore, get_vector_store
from .model import GNode, Graph, split_node_id


@dataclass
class ChunkHit:
    """A retrieved passage (chunk) together with its parent graph node."""

    node: GNode
    text: str
    score: float


def _chunk(text: str, size: int = 1000, overlap: int = 150, max_chunks: int = 80) -> list[str]:
    """Split a document into overlapping character windows (bounded per doc)."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(size - overlap, 1)
    return [text[i:i + size] for i in range(0, len(text), step)][:max_chunks]


class QueryEngine:
    def __init__(
        self,
        graph: Graph,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        index: bool = True,
    ):
        self.graph = graph
        self.nodes: dict[str, GNode] = {n.id: n for n in graph.nodes}
        self.embedder = embedder or get_embedder()
        self.store = vector_store or get_vector_store()
        self._g = self._build_nx(graph)
        if index:
            self._build_index()

    # --- construction -----------------------------------------------------

    @staticmethod
    def _build_nx(graph: Graph) -> nx.DiGraph:
        g = nx.DiGraph()
        for n in graph.nodes:
            g.add_node(n.id, namespace=n.namespace)
        for e in graph.edges:
            if e.source in g and e.target in g:
                g.add_edge(e.source, e.target, type=e.type, origin=e.origin)
        return g

    @staticmethod
    def _node_text(n: GNode) -> str:
        return f"{n.label}\n{n.content}".strip()

    def _build_index(self) -> None:
        """Index document *chunks* (not whole nodes) so retrieval surfaces the
        specific passage relevant to a query, not just the right document."""
        if not self.graph.nodes:
            return
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []
        for n in self.graph.nodes:
            for i, ch in enumerate(_chunk(self._node_text(n))):
                ids.append(f"{n.id}#{i}")
                texts.append(ch)
                metadatas.append({"namespace": n.namespace, "node_id": n.id, "text": ch})
        if ids:
            self.store.add(ids, self.embedder.embed(texts), metadatas)

    @classmethod
    def from_file(cls, path: str | Path, **kwargs) -> "QueryEngine":
        return cls(Graph.load(path), **kwargs)

    # --- operations -------------------------------------------------------

    def node(self, node_id: str) -> GNode | None:
        return self.nodes.get(node_id)

    def get_nodes_by_namespace(self, namespace: str) -> list[GNode]:
        return [n for n in self.graph.nodes if n.namespace == namespace]

    def search_chunks(
        self, query: str, k: int = 5, namespaces: list[str] | None = None
    ) -> list[ChunkHit]:
        """Top-k passages (chunks) by similarity, with their parent nodes."""
        qv = self.embedder.embed([query])[0]
        hits = self.store.search(qv, k=k, namespaces=namespaces)
        out: list[ChunkHit] = []
        for h in hits:
            n = self.nodes.get(h.metadata.get("node_id"))
            if n is not None:
                out.append(ChunkHit(node=n, text=h.metadata.get("text", ""), score=h.score))
        return out

    def semantic_search(
        self, query: str, k: int = 5, namespaces: list[str] | None = None
    ) -> list[tuple[GNode, float]]:
        """Top-k *nodes* (deduped from chunk hits), optionally namespace-filtered."""
        qv = self.embedder.embed([query])[0]
        hits = self.store.search(qv, k=max(k * 6, k), namespaces=namespaces)
        best: dict[str, float] = {}
        order: list[str] = []
        for h in hits:
            nid = h.metadata.get("node_id")
            if nid is None or nid not in self.nodes:
                continue
            if nid not in best:
                best[nid] = h.score
                order.append(nid)
            elif h.score > best[nid]:
                best[nid] = h.score
        return [(self.nodes[nid], best[nid]) for nid in order[:k]]

    def neighbors(self, node_id: str, undirected: bool = True) -> list[str]:
        if node_id not in self._g:
            return []
        nbrs = set(self._g.successors(node_id))
        if undirected:
            nbrs |= set(self._g.predecessors(node_id))
        return sorted(nbrs)

    def traverse(
        self,
        start_ids: list[str],
        max_hops: int = 2,
        undirected: bool = True,
        include_start: bool = False,
    ) -> list[GNode]:
        """BFS from start nodes up to ``max_hops``, following (cross-source) edges.

        Returns nodes in BFS order (by increasing hop distance). Cross-namespace
        edges are followed — a persona is an entry point, not a wall.
        """
        seen: set[str] = set(start_ids)
        order: list[str] = []
        q: deque[tuple[str, int]] = deque((s, 0) for s in start_ids if s in self._g)
        while q:
            nid, hop = q.popleft()
            if hop > 0:
                order.append(nid)
            if hop >= max_hops:
                continue
            for nb in self.neighbors(nid, undirected=undirected):
                if nb not in seen:
                    seen.add(nb)
                    q.append((nb, hop + 1))
        result_ids = ([s for s in start_ids if s in self.nodes] + order) if include_start else order
        return [self.nodes[i] for i in result_ids if i in self.nodes]

    # --- convenience ------------------------------------------------------

    def edges_between(self, ids: list[str]) -> list[tuple[str, str, str]]:
        s = set(ids)
        return [
            (u, v, d.get("type", "RELATED"))
            for u, v, d in self._g.edges(data=True)
            if u in s and v in s
        ]
