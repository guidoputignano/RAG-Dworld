"""Crawl orchestrator (live scraping driver).

Walks each source: fetch the landing page, follow a few same-domain internal
links (breadth-first up to ``max_pages``), convert each to frontmatter markdown,
and download + extract any linked PDFs. Reuses the tested Phase 2/3 primitives.

Live fetching is gated by ``ensure_allowed`` (off unless DREAM_SCRAPE_LIVE=true,
and Saudi-IP sources need a proxy/egress). The HTML and PDF fetchers are
injectable so the crawl logic is testable offline without a network.
"""
from __future__ import annotations

import tempfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from config import SOURCES
from ..extract.pdf_extractor import extract_to_file
from ..markdown_io import write as write_doc
from .scraper import (
    ScrapeConfig,
    ScrapeDisabled,
    ScrapeProxyRequired,
    ensure_allowed,
    fetch_static,
    find_internal_links,
    find_pdf_links,
    page_to_document,
    slug_from_url,
)

HtmlFetcher = Callable[[str, ScrapeConfig], str]
PdfFetcher = Callable[[str, ScrapeConfig], bytes]


def _default_pdf_fetcher(url: str, config: ScrapeConfig) -> bytes:  # pragma: no cover - network
    import httpx

    with httpx.Client(timeout=config.timeout, proxy=config.proxy or None,
                      headers={"User-Agent": config.user_agent}, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


@dataclass
class CrawlResult:
    namespace: str
    pages: list[str] = field(default_factory=list)   # saved md paths
    pdfs: list[str] = field(default_factory=list)     # saved md paths from PDFs
    skipped: str | None = None                        # reason if skipped
    errors: list[str] = field(default_factory=list)


def crawl_source(
    namespace: str,
    config: ScrapeConfig,
    *,
    out_dir: str | Path,
    max_pages: int = 5,
    fetch_html: HtmlFetcher | None = None,
    fetch_pdf: PdfFetcher | None = None,
    extract_pdfs: bool = True,
) -> CrawlResult:
    src = SOURCES[namespace]
    result = CrawlResult(namespace=namespace)
    try:
        ensure_allowed(namespace, config)
    except (ScrapeDisabled, ScrapeProxyRequired) as exc:
        result.skipped = str(exc)
        return result

    fetch_html = fetch_html or fetch_static
    fetch_pdf = fetch_pdf or _default_pdf_fetcher
    out_dir = Path(out_dir)

    seen_pages: set[str] = set()
    seen_pdfs: set[str] = set()
    queue: deque[str] = deque([src.url])

    while queue and len(seen_pages) < max_pages:
        url = queue.popleft()
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            html = fetch_html(url, config)
        except Exception as exc:  # network/HTTP errors are per-page, not fatal
            result.errors.append(f"{url}: {type(exc).__name__}: {str(exc)[:80]}")
            continue

        doc = page_to_document(html, source=namespace, url=url, personas=list(src.personas))
        path = out_dir / namespace / f"{slug_from_url(url)}.md"
        write_doc(doc, path)
        result.pages.append(str(path))

        for link in find_internal_links(html, url):
            if link not in seen_pages and len(seen_pages) + len(queue) < max_pages:
                queue.append(link)

        if extract_pdfs:
            for pdf_url in find_pdf_links(html, url):
                if pdf_url in seen_pdfs:
                    continue
                seen_pdfs.add(pdf_url)
                try:
                    data = fetch_pdf(pdf_url, config)
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                        tmp.write(data)
                        tmp.flush()
                        md_path = out_dir / namespace / f"{slug_from_url(pdf_url)}.md"
                        extract_to_file(tmp.name, md_path, source=namespace, url=pdf_url,
                                        personas=list(src.personas))
                    result.pdfs.append(str(md_path))
                except Exception as exc:
                    result.errors.append(f"{pdf_url}: {type(exc).__name__}: {str(exc)[:80]}")

    return result


def crawl_all(
    config: ScrapeConfig,
    *,
    out_dir: str | Path,
    namespaces: list[str] | None = None,
    only_open: bool = True,
    max_pages: int = 5,
    fetch_html: HtmlFetcher | None = None,
    fetch_pdf: PdfFetcher | None = None,
) -> list[CrawlResult]:
    targets = namespaces or list(SOURCES)
    results = []
    for ns in targets:
        if only_open and SOURCES[ns].requires_saudi_ip:
            results.append(CrawlResult(namespace=ns, skipped="saudi_ip source (only_open=True)"))
            continue
        results.append(crawl_source(
            ns, config, out_dir=out_dir, max_pages=max_pages,
            fetch_html=fetch_html, fetch_pdf=fetch_pdf,
        ))
    return results
