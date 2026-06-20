#!/usr/bin/env python3
"""Live-scrape sources into knowledge_base/, then optionally rebuild the graph.

Off by default — requires DREAM_SCRAPE_LIVE=true. Saudi-IP sources are skipped
unless a proxy/egress is configured (DREAM_SCRAPE_PROXY / DREAM_SCRAPE_EGRESS_REGION).

Examples:
  # OPEN sources only (no Saudi IP needed), 5 pages each, then rebuild graph:
  DREAM_SCRAPE_LIVE=true python scripts/scrape_sources.py --rebuild

  # Everything, via a Saudi proxy:
  DREAM_SCRAPE_LIVE=true DREAM_SCRAPE_PROXY=http://USER:PASS@sa-proxy:PORT \
    python scripts/scrape_sources.py --all --rebuild
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO_ROOT / "src"), str(REPO_ROOT)]

from dream_arabia.scrape.scraper import ScrapeConfig  # noqa: E402
from dream_arabia.scrape.crawl import crawl_all  # noqa: E402
from dream_arabia.graph.builder import build_federated, DEFAULT_KB, DEFAULT_GRAPHS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="include Saudi-IP sources (needs proxy)")
    ap.add_argument("--namespaces", nargs="*", help="limit to specific source namespaces")
    ap.add_argument("--max-pages", type=int, default=5)
    ap.add_argument("--out-dir", default=str(DEFAULT_KB))
    ap.add_argument("--rebuild", action="store_true", help="rebuild the federated graph after")
    args = ap.parse_args()

    config = ScrapeConfig.from_env()
    if not config.live:
        print("Refusing: DREAM_SCRAPE_LIVE is not 'true'. Set it to enable live scraping.")
        return 2

    results = crawl_all(
        config, out_dir=args.out_dir, namespaces=args.namespaces,
        only_open=not args.all, max_pages=args.max_pages,
    )

    pages = pdfs = skipped = errs = 0
    for r in results:
        if r.skipped:
            skipped += 1
            print(f"  SKIP {r.namespace}: {r.skipped}")
            continue
        pages += len(r.pages); pdfs += len(r.pdfs); errs += len(r.errors)
        print(f"  OK   {r.namespace}: {len(r.pages)} pages, {len(r.pdfs)} pdfs"
              + (f", {len(r.errors)} errors" if r.errors else ""))
        for e in r.errors:
            print(f"        ! {e}")

    print(f"\nTotal: {pages} pages, {pdfs} PDFs, {skipped} sources skipped, {errs} errors")

    if args.rebuild:
        graph, report = build_federated(kb_dir=args.out_dir, out_dir=str(DEFAULT_GRAPHS))
        print(f"Rebuilt graph: {report.total_nodes} nodes, {report.total_edges} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
