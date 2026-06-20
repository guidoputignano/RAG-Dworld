"""Personas — the six Dream Arabia personas from the Excel matrix.

A persona is an ENTRY POINT, not a hard filter: ``PERSONA_NAMESPACE_MAP`` sets
the namespaces traversal STARTS from. The agent still follows cross-source edges
into other namespaces when the answer needs them (PDF "Key Design Decisions" +
kickoff).

Launch priority (kickoff): P1 + P2 are built end-to-end first; P3-P6 are
scaffolded behind config so adding a persona is a config change, not new code.

The namespace map is derived from SOURCES membership (the Master URL Index is the
single source of truth) so it can never drift from the source table.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .sources import SOURCES, namespaces_for_personas


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    priority: str          # "launch" | "phase2" | "phase3"
    status: str            # "active" | "scaffolded"
    primary_handoff: str
    handoff_urls: tuple[str, ...]
    kpi: str


def _persona(pid, name, priority, status, handoffs, kpi):
    return Persona(pid, name, priority, status, handoffs[0], tuple(handoffs), kpi)


PERSONAS: dict[str, Persona] = {
    p.id: p for p in [
        _persona(
            "P1", "Investor", "launch", "active",
            ["https://investsaudi.sa/en", "https://misa.gov.sa/en", "https://pr.gov.sa"],
            "Qualified leads · MISA registrations initiated · RHQ applications started · investor Premium Residency opened",
        ),
        _persona(
            "P2", "Entrepreneur", "launch", "active",
            ["https://misa.gov.sa/en", "https://www.monshaat.gov.sa/en", "https://www.svc.com.sa/en"],
            "Company registrations initiated · Monshaat referrals · SVC partner-fund connections",
        ),
        _persona(
            "P3", "Tourist", "phase2", "scaffolded",
            ["https://www.visitsaudi.com/en", "https://webook.com/en"],
            "Booking initiations · destination discovery depth · event ticket referrals",
        ),
        _persona(
            "P4", "Foreign Talent", "phase2", "scaffolded",
            ["https://pr.gov.sa", "https://hrsd.gov.sa/en"],
            "Premium Residency applications initiated · employer-side referrals · talent inquiries logged",
        ),
        _persona(
            "P5", "Student", "phase3", "scaffolded",
            ["https://www.kfupm.edu.sa/en"],  # university-specific admissions portal
            "University portal referrals · scholarship inquiry referrals · programme matches",
        ),
        _persona(
            "P6", "Citizen / Resident", "phase3", "scaffolded",
            ["https://my.gov.sa/en", "https://absher.sa"],
            "Service-navigation completions · correct portal routing rate · zero individual determinations",
        ),
    ]
}

# Persona -> entry namespaces (derived from SOURCES; deterministic tier order).
PERSONA_NAMESPACE_MAP: dict[str, list[str]] = {
    pid: namespaces_for_personas(pid) for pid in PERSONAS
}

LAUNCH_PERSONAS: list[str] = [p.id for p in PERSONAS.values() if p.status == "active"]


def entry_namespaces(persona_id: str) -> list[str]:
    """Namespaces a persona's traversal starts from (not a hard filter)."""
    if persona_id not in PERSONA_NAMESPACE_MAP:
        raise KeyError(f"Unknown persona: {persona_id!r}")
    return list(PERSONA_NAMESPACE_MAP[persona_id])


def handoff_url(persona_id: str) -> str:
    """Primary handoff URL for a persona."""
    return PERSONAS[persona_id].primary_handoff
