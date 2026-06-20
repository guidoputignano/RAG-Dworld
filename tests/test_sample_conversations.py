"""Phase 8 — Definition of Done: replay each persona's Sample Conversation Flow.

Each answer for the active (launch) personas must cite a source, end with the
persona's handoff URL + named action, and respect every HARD guardrail.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import LAUNCH_PERSONAS, PERSONAS
from config.sample_flows import user_turns, load_sample_flows
from dream_arabia.embeddings import FakeEmbedder
from dream_arabia.vectorstore import MemoryVectorStore
from dream_arabia.graph import build_federated, QueryEngine
from dream_arabia.llm import MockLLM
from dream_arabia.agent import Agent
from dream_arabia.smoke import run_persona_flow
from dream_arabia.api import create_app, InMemorySessionStore

REPO_ROOT = Path(__file__).resolve().parent.parent
KB = REPO_ROOT / "knowledge_base"


@pytest.fixture(scope="module")
def agent(tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs")
    fed, _ = build_federated(kb_dir=KB, out_dir=out)
    qe = QueryEngine(fed, embedder=FakeEmbedder(), vector_store=MemoryVectorStore())
    return Agent(qe, llm=MockLLM())


def test_sample_flows_extracted_for_all_six_personas():
    flows = load_sample_flows()
    assert set(flows) == set(PERSONAS)
    # every persona tab has at least one user turn and one Dream turn
    for pid, turns in flows.items():
        assert any(t.role == "user" for t in turns), pid
        assert any(t.role == "assistant" for t in turns), pid


@pytest.mark.parametrize("persona", LAUNCH_PERSONAS)
def test_launch_persona_sample_flow_meets_dod(agent, persona):
    flows = user_turns()
    results = run_persona_flow(agent, persona, flows[persona])
    assert results, f"no turns for {persona}"
    for r in results:
        assert r.ok, f"{persona} turn failed DoD: {r.reasons} :: {r.question}"


def test_p1_flow_cites_a_dated_statistic(agent):
    # The investor flow touches FDI/economic context; at least one answer should
    # carry a year (statistic cited with year per the HARD 'ALWAYS cite' rule).
    flows = user_turns()
    s = agent.start_session("P1")
    answers = [agent.answer(s, m).text for m in flows["P1"]]
    import re
    assert any(re.search(r"\b20\d{2}\b", a) for a in answers)


def test_scaffolded_personas_are_not_launch_gated():
    assert set(LAUNCH_PERSONAS) == {"P1", "P2"}
    assert {"P3", "P4", "P5", "P6"}.isdisjoint(LAUNCH_PERSONAS)


def test_ui_served_and_endpoints_present(agent):
    client = TestClient(create_app(agent=agent, store=InMemorySessionStore()))
    html = client.get("/")
    assert html.status_code == 200
    assert "Dream Arabia" in html.text
    assert "/session/start" in html.text  # the UI wires the endpoints
