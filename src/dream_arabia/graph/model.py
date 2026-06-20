"""Graph data model shared by the extractor, builder, and query engine.

A node id is local within a per-source graph (e.g. ``investor_license``) and
becomes namespaced after merge (e.g. ``misa::investor_license``). Edges always
reference node ids in the same id-space as the graph they belong to.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

NAMESPACE_SEP = "::"


def make_node_id(namespace: str, local_id: str) -> str:
    """``misa`` + ``investor_license`` -> ``misa::investor_license`` (idempotent)."""
    if NAMESPACE_SEP in local_id:
        return local_id
    return f"{namespace}{NAMESPACE_SEP}{local_id}"


def split_node_id(node_id: str) -> tuple[str | None, str]:
    if NAMESPACE_SEP in node_id:
        ns, local = node_id.split(NAMESPACE_SEP, 1)
        return ns, local
    return None, node_id


@dataclass
class GNode:
    id: str
    namespace: str
    label: str
    content: str = ""
    source_url: str = ""
    personas: list[str] = field(default_factory=list)
    type: str = "page"
    title: str = ""
    year: str | int | None = None
    publisher: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [])}

    @classmethod
    def from_dict(cls, d: dict) -> "GNode":
        return cls(
            id=d["id"],
            namespace=d.get("namespace", split_node_id(d["id"])[0] or ""),
            label=d.get("label", d.get("title", d["id"])),
            content=d.get("content", ""),
            source_url=d.get("source_url", ""),
            personas=list(d.get("personas", [])),
            type=d.get("type", "page"),
            title=d.get("title", d.get("label", "")),
            year=d.get("year"),
            publisher=d.get("publisher"),
        )


@dataclass
class GEdge:
    source: str
    target: str
    type: str = "RELATED"
    origin: str = "intra"  # "intra" (within a source) | "cross" (curated cross-entity)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GEdge":
        return cls(
            source=d["source"],
            target=d["target"],
            type=d.get("type", "RELATED"),
            origin=d.get("origin", "intra"),
        )

    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.type)


@dataclass
class Graph:
    """A graph of nodes + edges (per-source before merge, federated after)."""

    namespace: str | None = None  # set for per-source graphs
    nodes: list[GNode] = field(default_factory=list)
    edges: list[GEdge] = field(default_factory=list)

    @property
    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def to_dict(self) -> dict:
        d: dict = {"nodes": [n.to_dict() for n in self.nodes],
                   "edges": [e.to_dict() for e in self.edges]}
        if self.namespace is not None:
            d = {"namespace": self.namespace, **d}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Graph":
        return cls(
            namespace=d.get("namespace"),
            nodes=[GNode.from_dict(n) for n in d.get("nodes", [])],
            edges=[GEdge.from_dict(e) for e in d.get("edges", [])],
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Graph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
