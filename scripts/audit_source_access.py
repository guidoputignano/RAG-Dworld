#!/usr/bin/env python3
"""Audit each source's real-world reachability and (optionally) correct the
``access`` flag in ``config/sources.py`` from tested results.

Why this exists
---------------
The ``access`` flags were transcribed verbatim from the Excel "Master URL Index"
(the spec's source of truth), which marks every ``.gov.sa`` entity "Saudi IP" at
whole-entity granularity. That is over-broad: many of those public landing pages
are reachable from anywhere; the "Saudi IP" note really applies to the gated
service/login portals behind them. This script replaces that *assumption* with
*measurement*: it GETs each URL and classifies the response.

Honest about the environment
----------------------------
It distinguishes an **environment** egress block (a managed proxy returning
``x-deny-reason: host_not_allowed``) from a real **origin** response. When run
from a restricted environment where the egress allowlist denies the target
hosts, every probe is ``egress_denied`` and **nothing is rewritten** — the audit
is inconclusive and says so. Run it from a session whose egress actually reaches
these sites to get real classifications.

Auto-correct is conservative
----------------------------
``--write`` only **downgrades** ``saudi_ip -> open`` on a definitive ``200`` (a
success from outside Saudi Arabia proves the page is open). Suggested
**upgrades** (an ``open``-labelled site returning a block) are *reported* but not
applied unless ``--apply-blocks`` is given, because a one-shot ``403`` is often
bot/WAF blocking rather than geo-gating.

Usage:
  python scripts/audit_source_access.py                 # dry-run, print table
  python scripts/audit_source_access.py --write          # apply safe fixes + log
  python scripts/audit_source_access.py --write --apply-blocks
  python scripts/audit_source_access.py --namespaces misa neom
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO_ROOT / "src"), str(REPO_ROOT)]

from config import SOURCES  # noqa: E402
from dream_arabia.scrape.scraper import ScrapeConfig  # noqa: E402

SOURCES_PY = REPO_ROOT / "config" / "sources.py"
AUDIT_JSON = REPO_ROOT / "config" / "access_audit.json"

# A realistic browser UA: some origins WAF-block obvious bot agents, which would
# otherwise be misread as a geo/access block.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class Probe:
    namespace: str
    url: str
    current_access: str           # saudi_ip | open  (the existing label)
    classification: str           # open | blocked | login | egress_denied | error
    http_status: int | None
    detail: str
    suggested_access: str | None  # open | saudi_ip | None(=inconclusive/no-change)


def classify(url: str, config: ScrapeConfig) -> tuple[str, int | None, str]:
    """GET a URL and classify the outcome. Pure observation; never raises."""
    import httpx

    try:
        with httpx.Client(
            timeout=config.timeout,
            proxy=config.proxy or None,
            headers={"User-Agent": BROWSER_UA},
            follow_redirects=True,
        ) as c:
            r = c.get(url)
    except Exception as exc:  # connection/timeout/DNS — network-level, inconclusive
        return "error", None, f"{type(exc).__name__}: {str(exc)[:90]}"

    # Managed egress proxy denied the host — this is about *our* environment,
    # not the site. Inconclusive for access classification.
    deny = r.headers.get("x-deny-reason")
    if deny:
        return "egress_denied", r.status_code, deny

    final = str(r.url).lower()
    if r.is_success:  # 2xx
        if any(k in final for k in ("login", "signin", "sso", "/auth", "account/")):
            return "login", r.status_code, f"redirected to a login page ({r.url})"
        return "open", r.status_code, "200 OK from outside Saudi Arabia"
    if r.status_code in (401, 403, 451):
        return "blocked", r.status_code, f"origin returned {r.status_code}"
    return "error", r.status_code, f"unexpected status {r.status_code}"


def suggest(classification: str) -> str | None:
    if classification == "open":
        return "open"
    if classification in ("blocked", "login"):
        return "saudi_ip"
    return None  # egress_denied / error -> leave the existing label untouched


def run_probes(namespaces: list[str] | None, config: ScrapeConfig) -> list[Probe]:
    targets = namespaces or list(SOURCES)
    out: list[Probe] = []
    for ns in targets:
        src = SOURCES[ns]
        cls, status, detail = classify(src.url, config)
        out.append(Probe(ns, src.url, src.access, cls, status, detail, suggest(cls)))
    return out


def plan_changes(probes: list[Probe], apply_blocks: bool) -> dict[str, str]:
    """Namespace -> new access, applying the conservative rules."""
    changes: dict[str, str] = {}
    for p in probes:
        if p.suggested_access is None or p.suggested_access == p.current_access:
            continue
        # safe direction: proven-open downgrade always applies
        if p.suggested_access == "open":
            changes[p.namespace] = "open"
        # risky direction: open -> saudi_ip only when explicitly opted in
        elif apply_blocks:
            changes[p.namespace] = "saudi_ip"
    return changes


def rewrite_sources_py(changes: dict[str, str]) -> list[str]:
    """Replace the access literal in-place on each affected source row."""
    lines = SOURCES_PY.read_text().splitlines(keepends=True)
    applied: list[str] = []
    for i, line in enumerate(lines):
        m = re.match(r'\s*\("([a-z0-9]+)",', line)
        if not m or m.group(1) not in changes:
            continue
        ns = m.group(1)
        new = changes[ns]
        new_line, n = re.subn(r'"(?:saudi_ip|open)"', f'"{new}"', line, count=1)
        if n:
            lines[i] = new_line
            applied.append(ns)
    if applied:
        SOURCES_PY.write_text("".join(lines))
    return applied


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--namespaces", nargs="*", help="limit to specific namespaces")
    ap.add_argument("--write", action="store_true",
                    help="apply safe (saudi_ip->open) fixes to config/sources.py + write audit log")
    ap.add_argument("--apply-blocks", action="store_true",
                    help="also apply risky open->saudi_ip downgrades (use with care)")
    args = ap.parse_args()

    config = ScrapeConfig.from_env()
    print(f"Proxy: {config.proxy or '(none)'} | egress_region: {config.egress_region or '(none)'}\n")

    probes = run_probes(args.namespaces, config)

    # report
    by_cls: dict[str, int] = {}
    print(f"{'ns':16} {'current':9} {'result':13} {'status':6} suggested")
    print("-" * 72)
    for p in sorted(probes, key=lambda x: (x.classification, x.namespace)):
        by_cls[p.classification] = by_cls.get(p.classification, 0) + 1
        sug = "" if p.suggested_access in (None, p.current_access) else f"-> {p.suggested_access}"
        print(f"{p.namespace:16} {p.current_access:9} {p.classification:13} "
              f"{str(p.http_status or ''):6} {sug}")

    print("\nClassification counts:", dict(sorted(by_cls.items())))

    egress = [p.namespace for p in probes if p.classification == "egress_denied"]
    if egress:
        print(f"\n!! {len(egress)} probes were EGRESS-DENIED by this environment's proxy "
              f"(host_not_allowed).\n   These are inconclusive — the audit cannot judge "
              f"the sites' real access from here.\n   Re-run from a session whose egress "
              f"reaches these hosts. Nothing will be rewritten for them.")

    changes = plan_changes(probes, args.apply_blocks)
    if not changes:
        print("\nNo conclusive label changes." + ("" if not egress else
              " (Everything was egress-denied — expected in a restricted env.)"))
        return 0

    print(f"\nProposed changes ({len(changes)}):")
    for ns, new in sorted(changes.items()):
        print(f"  {ns}: {SOURCES[ns].access} -> {new}")

    if not args.write:
        print("\n(dry-run) re-run with --write to apply.")
        return 0

    applied = rewrite_sources_py(changes)
    AUDIT_JSON.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "proxy": config.proxy, "egress_region": config.egress_region,
        "probes": [asdict(p) for p in probes],
        "applied": applied,
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"\nApplied {len(applied)} change(s) to {SOURCES_PY.name}; "
          f"audit log -> {AUDIT_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
