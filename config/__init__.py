"""Dream Arabia configuration package.

Single source of truth for sources, persona->namespace mapping, and the
guardrail ruleset parsed from the Excel training matrix.
"""
from .sources import SOURCES, PDF_LIBRARY, source, namespaces_for_personas
from .personas import (
    PERSONAS,
    PERSONA_NAMESPACE_MAP,
    LAUNCH_PERSONAS,
    entry_namespaces,
    handoff_url,
)

__all__ = [
    "SOURCES",
    "PDF_LIBRARY",
    "source",
    "namespaces_for_personas",
    "PERSONAS",
    "PERSONA_NAMESPACE_MAP",
    "LAUNCH_PERSONAS",
    "entry_namespaces",
    "handoff_url",
]
