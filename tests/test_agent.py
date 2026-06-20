"""Phase 6 — agent core: retrieval+traversal, guardrails, history cap, MockLLM."""
from pathlib import Path

import pytest

from dream_arabia.embeddings import FakeEmbedder
from dream_arabia.vectorstore import MemoryVectorStore
from dream_arabia.graph import build_federated, QueryEngine
from dream_arabia.llm import MockLLM, Citation
from dream_arabia.guardrails import GuardrailEngine
from dream_arabia.agent import Agent, Session, HISTORY_TURN_CAP

REPO_ROOT = Path(__file__).resolve().parent.parent
KB = REPO_ROOT / "knowledge_base"


@pytest.fixture(scope="module")
def agent(tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs")
    fed, _ = build_federated(kb_dir=KB, out_dir=out)
    qe = QueryEngine(fed, embedder=FakeEmbedder(), vector_store=MemoryVectorStore())
    return Agent(qe, llm=MockLLM(), guardrails=GuardrailEngine())


# --- guardrail engine units ----------------------------------------------

def test_guardrail_detects_missing_handoff():
    g = GuardrailEngine()
    rep = g.validate("Here is some info with no link.", "P1", [], ["https://investsaudi.sa/en"])
    assert any(v.kind == "missing_handoff" for v in rep.hard)


def test_guardrail_detects_eligibility_confirmation():
    g = GuardrailEngine()
    ans = "Yes, you qualify for RHQ. Register at https://misa.gov.sa/en"
    rep = g.validate(ans, "P1", [], ["https://misa.gov.sa/en"])
    assert any(v.kind == "forbidden:confirm_eligibility" for v in rep.hard)


def test_guardrail_detects_tax_rate_without_source():
    g = GuardrailEngine()
    ans = "The corporate tax rate is 15% for your company."  # no URL
    rep = g.validate(ans, "P1", [], ["https://misa.gov.sa/en"])
    assert any("tax_rate" in v.kind for v in rep.hard)


def test_guardrail_requires_year_when_dated_source_used():
    g = GuardrailEngine()
    dated = [Citation("misa", "MISA FDI Report", "https://misa.gov.sa", year="2024")]
    ans = "FDI is growing. Register at https://investsaudi.sa/en"  # no year
    rep = g.validate(ans, "P1", dated, ["https://investsaudi.sa/en"])
    assert any(v.kind == "missing_citation_year" for v in rep.hard)


def test_guardrail_enforce_appends_handoff():
    g = GuardrailEngine()
    fixed, rep = g.enforce("Some answer.", "P2", [], "https://misa.gov.sa/en",
                           action="begin your company registration")
    assert "https://misa.gov.sa/en" in fixed
    assert not any(v.kind == "missing_handoff" for v in rep.hard)


# --- agent end-to-end (MockLLM) ------------------------------------------

def test_p1_fdi_answer_is_compliant(agent):
    s = agent.start_session("P1")
    resp = agent.answer(s, "What is the FDI inflow into Saudi Arabia?")
    # statistic source cited with year, handoff present, no HARD violations
    assert "2024" in resp.text
    assert any(c.namespace == "misa" for c in resp.citations)
    assert "https://investsaudi.sa/en" in resp.text
    assert resp.guardrails_ok, resp.report.violations


def test_p2_funding_answer_is_compliant(agent):
    s = agent.start_session("P2")
    resp = agent.answer(s, "What startup funding routes are available — grants, VC, loans?")
    assert resp.citations
    assert any(c.namespace == "monshaat" for c in resp.citations)
    assert "https://misa.gov.sa/en" in resp.text
    assert resp.guardrails_ok, resp.report.violations


def test_retrieval_can_cross_namespaces(agent):
    # P2 entry includes monshaat + misa; a question about registration should pull MISA
    s = agent.start_session("P2")
    resp = agent.answer(s, "As a foreign founder how do I register my company with MISA?")
    namespaces = {c.namespace for c in resp.citations}
    assert "misa" in namespaces


def test_history_capped_at_six_turns(agent):
    s = agent.start_session("P1")
    for i in range(8):
        agent.answer(s, f"Tell me about investing, question {i}")
    assert len(s.history) <= HISTORY_TURN_CAP * 2


def test_switch_persona_resets_active_nodes(agent):
    s = agent.start_session("P1")
    agent.answer(s, "Tell me about RHQ")
    assert s.active_node_ids
    agent.switch_persona(s, "P2")
    assert s.persona == "P2"
    assert s.active_node_ids == []


def test_scaffolded_persona_rejected_at_start(agent):
    with pytest.raises(ValueError):
        agent.start_session("P3")  # scaffolded, not active
