"""Phase 1 — guardrails parse from the Excel into an enforceable ruleset."""
from config.guardrails_loader import (
    load_ruleset,
    load_generated,
    GENERATED_JSON,
    DEFAULT_XLSX,
)


def test_workbook_and_snapshot_agree():
    live = load_ruleset(DEFAULT_XLSX)
    snap = load_generated(GENERATED_JSON)
    assert len(live.rules) == len(snap.rules) > 0


def test_persona_and_matrix_rules_present():
    rs = load_ruleset()
    persona_rules = [r for r in rs.rules if r.source == "persona"]
    matrix_rules = [r for r in rs.rules if r.source == "matrix"]
    assert len(matrix_rules) == 15            # Guardrails Matrix domains
    assert {r.persona for r in persona_rules} == {"P1", "P2", "P3", "P4", "P5", "P6"}


def test_severities_are_valid():
    rs = load_ruleset()
    assert all(r.severity in {"HARD", "SOFT"} for r in rs.rules)
    assert rs.hard(), "expected some HARD rules"


def test_p1_hard_rules_capture_key_constraints():
    rs = load_ruleset()
    p1_hard = rs.hard("P1")
    blob = " ".join(r.rule.lower() + " " + r.rule_type.lower() for r in p1_hard)
    # never confirm individual RHQ eligibility; never quote tax rates without source
    assert "rhq" in blob
    assert "tax" in blob
    # 'ALWAYS cite' statistic rule is HARD for P1
    assert any("statistic" in r.rule.lower() for r in p1_hard)


def test_matrix_all_personas_rules_apply_to_everyone():
    rs = load_ruleset()
    politics = [r for r in rs.rules if r.source == "matrix" and "politics" in (r.domain or "").lower()]
    assert politics and set(politics[0].personas) == {"P1", "P2", "P3", "P4", "P5", "P6"}


def test_for_persona_merges_matrix_and_persona_rules():
    rs = load_ruleset()
    p4 = rs.for_persona("P4")
    assert any(r.source == "persona" for r in p4)
    assert any(r.source == "matrix" for r in p4)
