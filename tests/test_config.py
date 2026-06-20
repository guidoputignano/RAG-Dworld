"""Phase 1 — config sanity: SOURCES and PERSONA_NAMESPACE_MAP load and cohere."""
from config import (
    SOURCES,
    PDF_LIBRARY,
    PERSONAS,
    PERSONA_NAMESPACE_MAP,
    LAUNCH_PERSONAS,
    entry_namespaces,
    handoff_url,
)


def test_six_personas_two_launch():
    assert set(PERSONAS) == {"P1", "P2", "P3", "P4", "P5", "P6"}
    assert LAUNCH_PERSONAS == ["P1", "P2"]
    assert PERSONAS["P3"].status == "scaffolded"


def test_sources_have_valid_access_and_tier():
    assert len(SOURCES) == 42  # full Master URL Index
    for ns, s in SOURCES.items():
        assert s.namespace == ns
        assert s.access in {"saudi_ip", "open"}
        assert s.tier in {"T1", "T2", "T3", "T4"}
        assert s.url.startswith("http")
        assert all(p in PERSONAS for p in s.personas)


def test_namespace_map_is_derived_and_nonempty_for_launch():
    # Persona = entry point: each launch persona starts from several namespaces.
    for pid in LAUNCH_PERSONAS:
        ns = entry_namespaces(pid)
        assert ns, f"{pid} has no entry namespaces"
        # every entry namespace actually lists the persona
        for n in ns:
            assert pid in SOURCES[n].personas


def test_p1_p2_entry_namespaces_include_anchors():
    assert "misa" in PERSONA_NAMESPACE_MAP["P1"]
    assert "pif" in PERSONA_NAMESPACE_MAP["P1"]
    assert "monshaat" in PERSONA_NAMESPACE_MAP["P2"]
    assert "svc" in PERSONA_NAMESPACE_MAP["P2"]


def test_handoff_urls():
    assert handoff_url("P1") == "https://investsaudi.sa/en"
    assert handoff_url("P2") == "https://misa.gov.sa/en"


def test_pdf_library():
    assert len(PDF_LIBRARY) == 10
    assert PDF_LIBRARY["PDF-04"].year == "Jan 2024"
    assert "P1" in PDF_LIBRARY["PDF-04"].personas
