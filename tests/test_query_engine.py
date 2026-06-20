"""Phase 5 — query engine: namespace get, semantic search (filtered), traverse."""
from pathlib import Path

import numpy as np
import pytest

from dream_arabia.embeddings import FakeEmbedder, get_embedder
from dream_arabia.vectorstore import MemoryVectorStore
from dream_arabia.graph import build_federated, QueryEngine

REPO_ROOT = Path(__file__).resolve().parent.parent
KB = REPO_ROOT / "knowledge_base"


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs")
    fed, _ = build_federated(kb_dir=KB, out_dir=out)
    return QueryEngine(fed, embedder=FakeEmbedder(), vector_store=MemoryVectorStore())


# --- embeddings / vector store units --------------------------------------

def test_fake_embedder_is_deterministic_and_normalized():
    e = FakeEmbedder()
    a = e.embed(["kafalah loan guarantee"])
    b = e.embed(["kafalah loan guarantee"])
    assert np.allclose(a, b)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)


def test_memory_store_namespace_filter():
    store = MemoryVectorStore()
    e = FakeEmbedder()
    store.add(
        ["misa::a", "monshaat::b"],
        e.embed(["investor licensing registration", "kafalah loan guarantee sme"]),
        [{"namespace": "misa", "id": "misa::a"}, {"namespace": "monshaat", "id": "monshaat::b"}],
    )
    q = e.embed(["kafalah loan"])[0]
    hits_all = store.search(q, k=5)
    hits_misa = store.search(q, k=5, namespaces=["misa"])
    assert {h.metadata["namespace"] for h in hits_misa} == {"misa"}
    assert len(hits_all) >= len(hits_misa)


# --- query engine ---------------------------------------------------------

def test_get_nodes_by_namespace(engine):
    misa = engine.get_nodes_by_namespace("misa")
    assert {n.id for n in misa} >= {"misa::investor_license", "misa::fdi_report"}
    assert all(n.namespace == "misa" for n in misa)


def test_semantic_search_finds_relevant_node(engine):
    hits = engine.semantic_search("foreign direct investment inflow statistics", k=3)
    assert hits
    top_ids = [n.id for n, _ in hits]
    assert "misa::fdi_report" in top_ids


def test_semantic_search_namespace_filter_restricts(engine):
    hits = engine.semantic_search("loan guarantee financing", k=5, namespaces=["monshaat"])
    assert hits
    assert all(n.namespace == "monshaat" for n, _ in hits)


def test_traverse_follows_cross_namespace_edges(engine):
    # start inside misa; a curated cross edge reaches monshaat within 1 hop
    reached = engine.traverse(["misa::investor_license"], max_hops=1)
    reached_ids = {n.id for n in reached}
    assert "monshaat::incubators_accelerators" in reached_ids


def test_traverse_respects_max_hops(engine):
    one = {n.id for n in engine.traverse(["misa::service_manual"], max_hops=1)}
    two = {n.id for n in engine.traverse(["misa::service_manual"], max_hops=2)}
    assert one <= two
    # service_manual -SUPPORTS-> kafalah (1 hop); kafalah's neighbours appear at 2 hops
    assert "monshaat::kafalah_program" in one


def test_traverse_include_start(engine):
    start = "misa::investor_license"
    with_start = {n.id for n in engine.traverse([start], max_hops=1, include_start=True)}
    without = {n.id for n in engine.traverse([start], max_hops=1, include_start=False)}
    assert start in with_start
    assert start not in without


def test_get_embedder_factory_default_is_fake():
    e = get_embedder(env={})
    assert e.name == "fake"
