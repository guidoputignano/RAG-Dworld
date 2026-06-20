"""Graph layer (Phase 4-5): per-source extraction, federated merge, query."""
from .model import GNode, GEdge, Graph, make_node_id, split_node_id, NAMESPACE_SEP
from .extractor import (
    ConceptExtractor,
    DeterministicExtractor,
    extract_source,
)
from .builder import (
    build_federated,
    build_source_graphs,
    merge_graphs,
    load_cross_entity_edges,
    discover_source_dirs,
    BuildReport,
    FEDERATED_FILE,
)
from .query import QueryEngine

__all__ = [
    "GNode",
    "GEdge",
    "Graph",
    "make_node_id",
    "split_node_id",
    "NAMESPACE_SEP",
    "ConceptExtractor",
    "DeterministicExtractor",
    "extract_source",
    "build_federated",
    "build_source_graphs",
    "merge_graphs",
    "load_cross_entity_edges",
    "discover_source_dirs",
    "BuildReport",
    "FEDERATED_FILE",
    "QueryEngine",
]
