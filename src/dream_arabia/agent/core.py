"""Agent core (Phase 6).

Combines graph retrieval with LLM generation and guardrail enforcement, following
the spec's per-turn steps:

1. persona -> entry namespaces
2. semantic search (top-k) within those namespaces
3. traverse from retrieved nodes (1 hop) and from prior active nodes (2 hops) —
   following cross-source edges, since a persona is an entry point not a wall
4. format cited context
5. LLM call (OpenRouter or MockLLM) with system(persona + guardrails) + history
6. enforce guardrails on the answer (HARD rules, citation+year, handoff)
7. update active nodes for next turn
8. append to history, capped at 6 turns (12 messages)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import PERSONAS, SOURCES, entry_namespaces, handoff_url
from ..graph.model import GNode
from ..graph.query import QueryEngine
from ..guardrails.engine import GuardrailEngine, ValidationReport
from ..llm.base import LLM, Citation, LLMContext, Message, get_llm

HISTORY_TURN_CAP = 6  # 6 turns == 12 messages (spec)
DEFAULT_TOP_K = 5
MAX_CONTEXT_NODES = 6

# Named handoff action per persona (so the closing line is never a bare "visit").
PERSONA_ACTION = {
    "P1": "register your investor interest",
    "P2": "begin your company registration",
    "P3": "book your trip",
    "P4": "review the Premium Residency categories and apply",
    "P5": "review the admission requirements",
    "P6": "check your status and complete the service",
}


def _snippet(content: str, limit: int = 240) -> str:
    for block in content.split("\n\n"):
        block = block.strip()
        if block and not block.startswith("#") and not block.startswith("---"):
            text = re.sub(r"\s+", " ", block)
            return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def _context_excerpt(content: str, limit: int = 2200) -> str:
    """A generous excerpt of a node's body for the LLM (vs the short UI snippet).

    The full document text is stored on the node; feed the model a real chunk of
    it so answers can quote specific steps/figures/requirements, not just name
    the source. Strips a leading frontmatter fence and collapses blank runs.
    """
    body = re.sub(r"^\s*---.*?---\s*", "", content, flags=re.S)
    # scraped pages carry nav/boilerplate; drop images and link-only (menu) lines
    # so the budget is spent on real prose, not logos and menus.
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)                     # images
    body = re.sub(r"^\s*[-*]?\s*\[[^\]]+\]\([^)]*\)\s*$", "", body, flags=re.M)  # nav links
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body[:limit] + ("…" if len(body) > limit else "")


def _strip_thinking(text: str) -> str:
    """Drop <think>...</think> reasoning that thinking models (e.g. Qwen) emit."""
    text = re.sub(r"<think\b[^>]*>.*?</think>", "", text, flags=re.S | re.I)
    if "</think>" in text.lower():  # unbalanced/truncated open tag — keep the tail
        text = re.split(r"</think>", text, maxsplit=1, flags=re.I)[-1]
    return text.strip()


def _citation_for(node: GNode) -> Citation:
    src = SOURCES.get(node.namespace)
    name = node.publisher or (src.name if src else node.namespace)
    url = node.source_url or (src.url if src else "")
    return Citation(
        namespace=node.namespace,
        name=name,
        url=url,
        year=node.year,
        label=node.label,
        snippet=_snippet(node.content),
    )


@dataclass
class Session:
    persona: str
    history: list[Message] = field(default_factory=list)
    active_node_ids: list[str] = field(default_factory=list)

    def add_turn(self, user: str, assistant: str) -> None:
        self.history.append(Message("user", user))
        self.history.append(Message("assistant", assistant))
        # cap at HISTORY_TURN_CAP turns (2 messages per turn)
        max_msgs = HISTORY_TURN_CAP * 2
        if len(self.history) > max_msgs:
            self.history = self.history[-max_msgs:]


@dataclass
class AgentResponse:
    text: str
    persona: str
    citations: list[Citation]
    retrieved_ids: list[str]
    active_node_ids: list[str]
    report: ValidationReport

    @property
    def guardrails_ok(self) -> bool:
        return self.report.ok_hard


class Agent:
    def __init__(
        self,
        query_engine: QueryEngine,
        llm: LLM | None = None,
        guardrails: GuardrailEngine | None = None,
        top_k: int = DEFAULT_TOP_K,
    ):
        self.qe = query_engine
        self.llm = llm or get_llm()
        self.guardrails = guardrails or GuardrailEngine()
        self.top_k = top_k

    # --- session lifecycle ------------------------------------------------

    def start_session(self, persona: str) -> Session:
        if persona not in PERSONAS:
            raise KeyError(f"Unknown persona: {persona!r}")
        if PERSONAS[persona].status != "active":
            # scaffolded personas exist in config but aren't launched yet
            raise ValueError(f"Persona {persona} is scaffolded, not active for launch")
        return Session(persona=persona)

    def greeting(self, persona: str) -> str:
        p = PERSONAS[persona]
        return (
            f"Welcome. I'm Dream Arabia, here to help as you explore Saudi Arabia "
            f"as a{'n' if p.name[0].lower() in 'aeiou' else ''} {p.name.lower()}. "
            "Ask me anything — I'll cite official sources and point you to the right "
            "next step. What would you like to know?"
        )

    def switch_persona(self, session: Session, persona: str) -> Session:
        if persona not in PERSONAS:
            raise KeyError(f"Unknown persona: {persona!r}")
        session.persona = persona
        session.active_node_ids = []  # reset traversal anchors on switch
        return session

    # --- retrieval --------------------------------------------------------

    def _retrieve(self, session: Session, question: str) -> tuple[list[GNode], list[str]]:
        namespaces = entry_namespaces(session.persona)
        hits = self.qe.semantic_search(question, k=self.top_k, namespaces=namespaces)
        retrieved = [n for n, _ in hits]
        retrieved_ids = [n.id for n in retrieved]

        ordered: list[GNode] = list(retrieved)
        seen = set(retrieved_ids)

        # follow cross-source edges out of what we just retrieved (1 hop)
        for n in self.qe.traverse(retrieved_ids, max_hops=1):
            if n.id not in seen:
                seen.add(n.id)
                ordered.append(n)
        # continue from prior active nodes (2 hops) for follow-up coherence
        if session.active_node_ids:
            for n in self.qe.traverse(session.active_node_ids, max_hops=2):
                if n.id not in seen:
                    seen.add(n.id)
                    ordered.append(n)

        return ordered[:MAX_CONTEXT_NODES], retrieved_ids

    @staticmethod
    def _format_context(nodes: list[GNode]) -> str:
        blocks = []
        for n in nodes:
            src = SOURCES.get(n.namespace)
            name = n.publisher or (src.name if src else n.namespace)
            yr = f", {n.year}" if n.year not in (None, "") else ""
            url = n.source_url or (src.url if src else "")
            blocks.append(f"### {n.label} — {name}{yr} ({url})\n{_context_excerpt(n.content)}")
        return (
            "Retrieved context — answer ONLY from this, and cite specific figures, "
            "steps, and requirements where they appear:\n\n" + "\n\n".join(blocks)
        )

    # --- main entry -------------------------------------------------------

    def answer(self, session: Session, question: str) -> AgentResponse:
        persona = session.persona
        nodes, retrieved_ids = self._retrieve(session, question)
        citations = [_citation_for(n) for n in nodes]

        h_url = handoff_url(persona)
        action = PERSONA_ACTION.get(persona, "continue")
        extra_handoffs = list(PERSONAS[persona].handoff_urls)

        system = self.guardrails.system_prompt(PERSONAS[persona].name, persona, h_url)
        if nodes:
            system = f"{system}\n\n{self._format_context(nodes)}"

        llm_ctx = LLMContext(
            persona=persona,
            persona_name=PERSONAS[persona].name,
            handoff_url=h_url,
            action=action,
            citations=citations,
        )
        messages = list(session.history) + [Message("user", question)]
        raw = _strip_thinking(self.llm.complete(system, messages, context=llm_ctx))

        text, report = self.guardrails.enforce(
            raw, persona, citations, h_url, action=action, extra_handoffs=extra_handoffs
        )

        # update active nodes for next turn's traversal
        session.active_node_ids = list(dict.fromkeys(retrieved_ids + [n.id for n in nodes]))
        session.add_turn(question, text)

        return AgentResponse(
            text=text,
            persona=persona,
            citations=citations,
            retrieved_ids=retrieved_ids,
            active_node_ids=session.active_node_ids,
            report=report,
        )
