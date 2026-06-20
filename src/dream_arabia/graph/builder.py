"""Federated graph builder (Phase 4).

N graphs at build time, one graph at query time: extract each source folder to
``graphs/<namespace>.json``, then merge into ``graphs/federated_graph.json`` with
the namespace injected into every node id and edge endpoint. Finally fold in the
manually curated cross-entity edges (``knowledge_base/cross_entity/
cross_entity_edges.json``) that link nodes across sources — relationships the
per-source extractor can't see because they span documents.

A single source can be re-extracted and re-merged independently.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .extractor import ConceptExtractor, extract_source
from .model import GEdge, GNode, Graph, make_node_id

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KB = REPO_ROOT / "knowledge_base"
DEFAULT_GRAPHS = REPO_ROOT / "graphs"
CROSS_ENTITY_DIRNAME = "cross_entity"
CROSS_ENTITY_FILE = "cross_entity_edges.json"
FEDERATED_FILE = "federated_graph.json"


@dataclass
class BuildReport:
    sources: dict[str, dict] = field(default_factory=dict)  # ns -> {nodes, edges}
    total_nodes: int = 0
    total_edges: int = 0
    cross_edges_added: int = 0
    cross_edges_skipped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sources": self.sources,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "cross_edges_added": self.cross_edges_added,
            "cross_edges_skipped": self.cross_edges_skipped,
        }


def discover_source_dirs(kb_dir: str | Path = DEFAULT_KB) -> list[tuple[str, Path]]:
    """(namespace, dir) for each source folder, excluding cross_entity."""
    kb = Path(kb_dir)
    out = []
    for child in sorted(kb.iterdir()):
        if child.is_dir() and child.name != CROSS_ENTITY_DIRNAME:
            if any(child.glob("*.md")):
                out.append((child.name, child))
    return out


def build_source_graphs(
    kb_dir: str | Path = DEFAULT_KB,
    out_dir: str | Path = DEFAULT_GRAPHS,
    extractor: ConceptExtractor | None = None,
    namespaces: list[str] | None = None,
) -> dict[str, Graph]:
    """Extract each source folder to ``graphs/<namespace>.json``."""
    out_dir = Path(out_dir)
    graphs: dict[str, Graph] = {}
    for ns, src_dir in discover_source_dirs(kb_dir):
        if namespaces is not None and ns not in namespaces:
            continue
        g = extract_source(ns, src_dir, extractor=extractor)
        g.save(out_dir / f"{ns}.json")
        graphs[ns] = g
    return graphs


def _namespace_graph(g: Graph) -> tuple[list[GNode], list[GEdge]]:
    ns = g.namespace or ""
    nodes = []
    for n in g.nodes:
        nid = make_node_id(ns, n.id)
        nodes.append(GNode(
            id=nid, namespace=ns, label=n.label, content=n.content,
            source_url=n.source_url, personas=n.personas, type=n.type,
            title=n.title, year=n.year, publisher=n.publisher,
        ))
    edges = [
        GEdge(source=make_node_id(ns, e.source), target=make_node_id(ns, e.target),
              type=e.type, origin="intra")
        for e in g.edges
    ]
    return nodes, edges


def load_cross_entity_edges(kb_dir: str | Path = DEFAULT_KB) -> list[GEdge]:
    path = Path(kb_dir) / CROSS_ENTITY_DIRNAME / CROSS_ENTITY_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("edges", data) if isinstance(data, dict) else data
    return [GEdge(source=e["source"], target=e["target"],
                  type=e.get("type", "RELATED"), origin="cross") for e in raw]


def merge_graphs(
    source_graphs: dict[str, Graph],
    cross_edges: list[GEdge] | None = None,
) -> tuple[Graph, BuildReport]:
    """Merge per-source graphs into one federated, namespace-tagged graph."""
    report = BuildReport()
    nodes: list[GNode] = []
    edges: list[GEdge] = []
    for ns, g in source_graphs.items():
        ns_nodes, ns_edges = _namespace_graph(g)
        nodes.extend(ns_nodes)
        edges.extend(ns_edges)
        report.sources[ns] = {"nodes": len(ns_nodes), "edges": len(ns_edges)}

    node_ids = {n.id for n in nodes}
    for e in cross_edges or []:
        if e.source in node_ids and e.target in node_ids:
            edges.append(e)
            report.cross_edges_added += 1
        else:
            missing = [x for x in (e.source, e.target) if x not in node_ids]
            report.cross_edges_skipped.append({
                "source": e.source, "target": e.target, "type": e.type,
                "missing": missing,
            })

    report.total_nodes = len(nodes)
    report.total_edges = len(edges)
    return Graph(namespace=None, nodes=nodes, edges=edges), report


def build_federated(
    kb_dir: str | Path = DEFAULT_KB,
    out_dir: str | Path = DEFAULT_GRAPHS,
    extractor: ConceptExtractor | None = None,
    namespaces: list[str] | None = None,
) -> tuple[Graph, BuildReport]:
    """Full build: per-source extraction -> merge -> federated_graph.json."""
    source_graphs = build_source_graphs(kb_dir, out_dir, extractor, namespaces)
    cross = load_cross_entity_edges(kb_dir)
    federated, report = merge_graphs(source_graphs, cross)
    federated.save(Path(out_dir) / FEDERATED_FILE)
    return federated, report


def _cli() -> None:  # pragma: no cover
    fed, report = build_federated()
    print(f"Federated graph: {report.total_nodes} nodes, {report.total_edges} edges")
    print(f"  per source: {report.sources}")
    print(f"  cross-entity edges added: {report.cross_edges_added}, "
          f"skipped (dangling): {len(report.cross_edges_skipped)}")
    for s in report.cross_edges_skipped:
        print(f"    skipped {s['source']} -> {s['target']} (missing {s['missing']})")


if __name__ == "__main__":  # pragma: no cover
    _cli()
