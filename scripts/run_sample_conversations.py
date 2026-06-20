#!/usr/bin/env python3
"""Replay each persona tab's Sample Conversation Flow as a smoke test.

Runs fully offline (MockLLM + fake embeddings) by default, so it needs no API
key or network. Exits non-zero if any active persona's flow fails the Definition
of Done. Set DREAM_LLM_PROVIDER=openrouter (+ key) and DREAM_EMBED_PROVIDER=local
to run it against the real model.

Usage:  python scripts/run_sample_conversations.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO_ROOT / "src"), str(REPO_ROOT)]

from config import LAUNCH_PERSONAS, PERSONAS  # noqa: E402
from config.sample_flows import user_turns  # noqa: E402
from dream_arabia.agent import Agent  # noqa: E402
from dream_arabia.graph import QueryEngine  # noqa: E402
from dream_arabia.graph.builder import build_federated  # noqa: E402
from dream_arabia.smoke import run_persona_flow  # noqa: E402


def build_agent() -> Agent:
    graph, _ = build_federated()
    return Agent(QueryEngine(graph))  # embedder/LLM from env (fake/mock defaults)


def main() -> int:
    agent = build_agent()
    flows = user_turns()
    failures = 0

    for pid in LAUNCH_PERSONAS:
        print(f"\n=== {pid} — {PERSONAS[pid].name} ===")
        results = run_persona_flow(agent, pid, flows.get(pid, []))
        for i, r in enumerate(results, 1):
            status = "PASS" if r.ok else "FAIL"
            print(f"  [{status}] turn {i}: {r.question[:60]}")
            if not r.ok:
                failures += 1
                print(f"          reasons: {', '.join(r.reasons)}")

    scaffolded = [p for p in PERSONAS if p not in LAUNCH_PERSONAS]
    print(f"\nScaffolded (not launch-gated): {', '.join(scaffolded)}")

    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
