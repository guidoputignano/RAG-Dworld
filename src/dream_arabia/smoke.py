"""Sample-conversation regression (Phase 8 / Definition of Done).

Replays each persona tab's "Sample Conversation Flow" against the agent and
checks every answer:

- cites at least one official source (with year where a dated source is used),
- ends with the persona's handoff URL + a named action,
- respects every HARD guardrail for that persona (no HARD violations).

Shared by ``tests/test_sample_conversations.py`` and
``scripts/run_sample_conversations.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import PERSONAS, handoff_url
from .agent.core import Agent, AgentResponse


@dataclass
class TurnResult:
    persona: str
    question: str
    answer: str
    ok: bool
    reasons: list[str] = field(default_factory=list)


def check_response(persona: str, resp: AgentResponse) -> TurnResult:
    reasons: list[str] = []

    # DoD 1 — an official source is cited
    if not resp.citations:
        reasons.append("no citations")

    # DoD 2 — handoff URL + named action (and all HARD guardrails) via the engine
    for v in resp.report.hard:
        reasons.append(f"HARD:{v.kind}")

    # DoD 3 — handoff URL actually present (belt-and-braces with the engine check)
    handoffs = set(PERSONAS[persona].handoff_urls) | {handoff_url(persona)}
    if not any(u and u in resp.text for u in handoffs):
        reasons.append("missing handoff url")

    return TurnResult(persona=persona, question="", answer=resp.text,
                      ok=not reasons, reasons=reasons)


def run_persona_flow(agent: Agent, persona: str, user_messages: list[str]) -> list[TurnResult]:
    session = agent.start_session(persona)
    results: list[TurnResult] = []
    for msg in user_messages:
        resp = agent.answer(session, msg)
        res = check_response(persona, resp)
        res.question = msg
        results.append(res)
    return results


def run_regression(agent: Agent, flows: dict[str, list[str]], personas: list[str]) -> list[TurnResult]:
    out: list[TurnResult] = []
    for pid in personas:
        out.extend(run_persona_flow(agent, pid, flows.get(pid, [])))
    return out
