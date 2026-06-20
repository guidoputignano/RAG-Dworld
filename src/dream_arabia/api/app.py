"""FastAPI backend (Phase 7) — start / message / switch.

Session state is held in memory (see ``sessions.py`` for the Redis seam). The
agent (graph + embeddings + LLM + guardrails) is built once and shared across
requests; ``create_app`` accepts an injected agent/store for testing.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

UI_INDEX = Path(__file__).resolve().parent.parent / "ui" / "index.html"

from config import PERSONAS, LAUNCH_PERSONAS
from ..agent.core import Agent, AgentResponse
from ..graph import build_federated, QueryEngine
from ..graph.builder import DEFAULT_GRAPHS, FEDERATED_FILE, DEFAULT_KB
from ..graph.model import Graph
from ..llm.base import Citation
from .sessions import InMemorySessionStore, SessionStore, get_session_store


# --- request / response models -------------------------------------------

class StartRequest(BaseModel):
    persona: str = Field(..., examples=["P1"])


class StartResponse(BaseModel):
    session_id: str
    persona: str
    persona_name: str
    greeting: str


class MessageRequest(BaseModel):
    session_id: str
    message: str


class CitationOut(BaseModel):
    namespace: str
    name: str
    url: str
    year: str | int | None = None
    label: str = ""


class ViolationOut(BaseModel):
    kind: str
    severity: str
    detail: str = ""


class MessageResponse(BaseModel):
    session_id: str
    persona: str
    answer: str
    citations: list[CitationOut]
    guardrails_ok: bool
    violations: list[ViolationOut]
    active_nodes: list[str]


class SwitchRequest(BaseModel):
    session_id: str
    persona: str


class SwitchResponse(BaseModel):
    session_id: str
    persona: str
    persona_name: str
    greeting: str


def _citation_out(c: Citation) -> CitationOut:
    return CitationOut(namespace=c.namespace, name=c.name, url=c.url, year=c.year, label=c.label)


def _to_message_response(sid: str, resp: AgentResponse) -> MessageResponse:
    return MessageResponse(
        session_id=sid,
        persona=resp.persona,
        answer=resp.text,
        citations=[_citation_out(c) for c in resp.citations],
        guardrails_ok=resp.guardrails_ok,
        violations=[ViolationOut(kind=v.kind, severity=v.severity, detail=v.detail) for v in resp.report.violations],
        active_nodes=resp.active_node_ids,
    )


# --- agent construction ---------------------------------------------------

def _load_or_build_graph(kb_dir: Path = DEFAULT_KB, graphs_dir: Path = DEFAULT_GRAPHS) -> Graph:
    federated = Path(graphs_dir) / FEDERATED_FILE
    if federated.exists():
        return Graph.load(federated)
    graph, _ = build_federated(kb_dir=kb_dir, out_dir=graphs_dir)
    return graph


def build_default_agent() -> Agent:
    graph = _load_or_build_graph()
    qe = QueryEngine(graph)  # embedder + vector store from env (fake/memory by default)
    return Agent(qe)


def create_app(agent: Agent | None = None, store: SessionStore | None = None) -> FastAPI:
    app = FastAPI(title="Dream Arabia", version="0.1.0")
    app.state.agent = agent  # lazily built on first use if None
    app.state.store = store or get_session_store()

    def get_agent() -> Agent:
        if app.state.agent is None:
            app.state.agent = build_default_agent()
        return app.state.agent

    def get_store() -> SessionStore:
        return app.state.store

    @app.get("/", response_class=HTMLResponse)
    def ui():
        if UI_INDEX.exists():
            return HTMLResponse(UI_INDEX.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Dream Arabia</h1><p>UI not found.</p>", status_code=404)

    @app.get("/health")
    def health():
        return {"status": "ok", "launch_personas": LAUNCH_PERSONAS}

    @app.get("/personas")
    def personas():
        return {
            pid: {"name": p.name, "status": p.status, "priority": p.priority,
                  "handoff": p.primary_handoff}
            for pid, p in PERSONAS.items()
        }

    @app.post("/session/start", response_model=StartResponse)
    def start(req: StartRequest, agent: Agent = Depends(get_agent), store: SessionStore = Depends(get_store)):
        if req.persona not in PERSONAS:
            raise HTTPException(status_code=404, detail=f"Unknown persona {req.persona!r}")
        try:
            session = agent.start_session(req.persona)
        except ValueError as exc:  # scaffolded persona
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        sid = store.create(session)
        return StartResponse(
            session_id=sid, persona=req.persona,
            persona_name=PERSONAS[req.persona].name,
            greeting=agent.greeting(req.persona),
        )

    @app.post("/session/message", response_model=MessageResponse)
    def message(req: MessageRequest, agent: Agent = Depends(get_agent), store: SessionStore = Depends(get_store)):
        session = store.get(req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown session_id")
        if not req.message.strip():
            raise HTTPException(status_code=422, detail="Empty message")
        resp = agent.answer(session, req.message)
        store.save(req.session_id, session)
        return _to_message_response(req.session_id, resp)

    @app.post("/session/switch", response_model=SwitchResponse)
    def switch(req: SwitchRequest, agent: Agent = Depends(get_agent), store: SessionStore = Depends(get_store)):
        session = store.get(req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown session_id")
        if req.persona not in PERSONAS:
            raise HTTPException(status_code=404, detail=f"Unknown persona {req.persona!r}")
        if PERSONAS[req.persona].status != "active":
            raise HTTPException(status_code=409, detail=f"Persona {req.persona} is not active for launch")
        agent.switch_persona(session, req.persona)
        store.save(req.session_id, session)
        return SwitchResponse(
            session_id=req.session_id, persona=req.persona,
            persona_name=PERSONAS[req.persona].name,
            greeting=agent.greeting(req.persona),
        )

    return app


# Module-level app for `uvicorn dream_arabia.api.app:app`
app = create_app()
