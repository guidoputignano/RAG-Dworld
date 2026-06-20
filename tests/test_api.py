"""Phase 7 — FastAPI: start / message / switch with in-memory sessions."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dream_arabia.embeddings import FakeEmbedder
from dream_arabia.vectorstore import MemoryVectorStore
from dream_arabia.graph import build_federated, QueryEngine
from dream_arabia.llm import MockLLM
from dream_arabia.agent import Agent
from dream_arabia.api import create_app, InMemorySessionStore

REPO_ROOT = Path(__file__).resolve().parent.parent
KB = REPO_ROOT / "knowledge_base"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    out = tmp_path_factory.mktemp("graphs")
    fed, _ = build_federated(kb_dir=KB, out_dir=out)
    qe = QueryEngine(fed, embedder=FakeEmbedder(), vector_store=MemoryVectorStore())
    agent = Agent(qe, llm=MockLLM())
    app = create_app(agent=agent, store=InMemorySessionStore())
    return TestClient(app)


def test_health_and_personas(client):
    assert client.get("/health").json()["status"] == "ok"
    personas = client.get("/personas").json()
    assert personas["P1"]["status"] == "active"
    assert personas["P3"]["status"] == "scaffolded"


def test_start_returns_session_and_greeting(client):
    r = client.post("/session/start", json={"persona": "P1"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"]
    assert body["persona"] == "P1"
    assert "Welcome" in body["greeting"]


def test_start_scaffolded_persona_conflicts(client):
    r = client.post("/session/start", json={"persona": "P3"})
    assert r.status_code == 409


def test_start_unknown_persona_404(client):
    assert client.post("/session/start", json={"persona": "P9"}).status_code == 404


def test_message_returns_compliant_answer(client):
    sid = client.post("/session/start", json={"persona": "P1"}).json()["session_id"]
    r = client.post("/session/message",
                    json={"session_id": sid, "message": "What is the FDI inflow?"})
    assert r.status_code == 200
    body = r.json()
    assert body["guardrails_ok"] is True
    assert "2024" in body["answer"]
    assert "https://investsaudi.sa/en" in body["answer"]
    assert body["citations"]


def test_message_unknown_session_404(client):
    r = client.post("/session/message", json={"session_id": "nope", "message": "hi"})
    assert r.status_code == 404


def test_empty_message_422(client):
    sid = client.post("/session/start", json={"persona": "P1"}).json()["session_id"]
    r = client.post("/session/message", json={"session_id": sid, "message": "   "})
    assert r.status_code == 422


def test_full_start_message_switch_cycle(client):
    sid = client.post("/session/start", json={"persona": "P1"}).json()["session_id"]
    client.post("/session/message", json={"session_id": sid, "message": "Tell me about RHQ"})
    # switch to P2
    sw = client.post("/session/switch", json={"session_id": sid, "persona": "P2"})
    assert sw.status_code == 200 and sw.json()["persona"] == "P2"
    # message after switch routes with the new persona handoff
    r = client.post("/session/message",
                    json={"session_id": sid, "message": "How do I get startup funding?"})
    assert r.status_code == 200
    assert "https://misa.gov.sa/en" in r.json()["answer"]


def test_switch_to_scaffolded_conflicts(client):
    sid = client.post("/session/start", json={"persona": "P1"}).json()["session_id"]
    r = client.post("/session/switch", json={"session_id": sid, "persona": "P3"})
    assert r.status_code == 409
