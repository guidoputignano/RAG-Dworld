"""Phase 4 — per-source extraction + federated merge + cross-entity edges."""
from pathlib import Path

from dream_arabia.graph import (
    extract_source,
    build_federated,
    merge_graphs,
    load_cross_entity_edges,
    discover_source_dirs,
    Graph,
    make_node_id,
    split_node_id,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
# Build from the synthetic fixtures, not the real scraped knowledge_base/.
KB = REPO_ROOT / "tests" / "fixtures" / "kb"


def test_discover_source_dirs_excludes_cross_entity():
    ns = dict(discover_source_dirs(KB))
    assert "misa" in ns and "monshaat" in ns
    assert "cross_entity" not in ns


def test_per_source_extraction_nodes_and_intra_edges():
    g = extract_source("misa", KB / "misa")
    assert g.namespace == "misa"
    # one node per fixture page, local (un-namespaced) ids
    assert "investor_license" in g.node_ids
    assert all("::" not in n.id for n in g.nodes)
    # the in-body link investor_license -> rhq_program becomes an intra edge
    assert any(e.source == "investor_license" and e.target == "rhq_program"
               and e.type == "REFERENCES" for e in g.edges)


def test_node_carries_persona_and_provenance():
    g = extract_source("misa", KB / "misa")
    fdi = next(n for n in g.nodes if n.id == "fdi_report")
    assert "P1" in fdi.personas
    assert str(fdi.year) == "2024"
    assert fdi.source_url.startswith("http")


def test_federated_merge_injects_namespace(tmp_path):
    fed, report = build_federated(kb_dir=KB, out_dir=tmp_path)
    # every node id is namespaced
    assert all("::" in n.id for n in fed.nodes)
    assert make_node_id("misa", "investor_license") in fed.node_ids
    ns, local = split_node_id("misa::investor_license")
    assert ns == "misa" and local == "investor_license"
    # federated_graph.json written
    assert (tmp_path / "federated_graph.json").exists()
    assert (tmp_path / "misa.json").exists()


def test_cross_entity_edges_added_and_dangling_skipped(tmp_path):
    fed, report = build_federated(kb_dir=KB, out_dir=tmp_path)
    cross = [e for e in fed.edges if e.origin == "cross"]
    assert report.cross_edges_added == len(cross) == 3
    # the intentionally-dangling svc edge is skipped and reported, not dropped silently
    assert len(report.cross_edges_skipped) == 1
    assert report.cross_edges_skipped[0]["target"] == "svc::partner_funds"
    # a real cross edge connects the two sources
    assert any(e.source == "misa::investor_license"
               and e.target == "monshaat::incubators_accelerators" for e in cross)


def test_cross_edges_endpoints_are_namespaced():
    edges = load_cross_entity_edges(KB)
    assert edges
    for e in edges:
        assert "::" in e.source and "::" in e.target
        assert e.origin == "cross"


def test_graph_roundtrip(tmp_path):
    fed, _ = build_federated(kb_dir=KB, out_dir=tmp_path)
    p = tmp_path / "rt.json"
    fed.save(p)
    loaded = Graph.load(p)
    assert loaded.node_ids == fed.node_ids
    assert len(loaded.edges) == len(fed.edges)
