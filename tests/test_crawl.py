"""Crawl orchestrator — tested offline with injected fetchers (no network)."""
from pathlib import Path

from dream_arabia import markdown_io
from dream_arabia.scrape.scraper import ScrapeConfig
from dream_arabia.scrape.crawl import crawl_source, crawl_all

LANDING = """
<html><head><title>DataSaudi</title></head><body>
<h1>DataSaudi Statistics</h1>
<p>Open statistics portal.</p>
<a href="/en/gdp">GDP</a>
<a href="/en/fdi">FDI</a>
<a href="https://datasaudi.sa/files/report.pdf">Report PDF</a>
</body></html>
"""
SUB = "<html><head><title>Sub</title></head><body><h1>Sub page</h1><p>Detail.</p></body></html>"


def _fake_html(url, config):
    return LANDING if url.rstrip("/").endswith("datasaudi.sa/en") else SUB


def test_crawl_open_source_writes_pages(tmp_path):
    cfg = ScrapeConfig(live=True)  # datasaudi is OPEN -> allowed
    res = crawl_source("datasaudi", cfg, out_dir=tmp_path, max_pages=3,
                       fetch_html=_fake_html, extract_pdfs=False)
    assert res.skipped is None
    assert len(res.pages) >= 1
    doc = markdown_io.read(res.pages[0])
    assert doc.source == "datasaudi"
    assert doc.frontmatter["scraped"] is True


def test_crawl_follows_internal_links_up_to_max(tmp_path):
    cfg = ScrapeConfig(live=True)
    res = crawl_source("datasaudi", cfg, out_dir=tmp_path, max_pages=3,
                       fetch_html=_fake_html, extract_pdfs=False)
    assert len(res.pages) <= 3
    assert len(res.pages) >= 2  # landing + at least one internal link


def test_crawl_extracts_linked_pdf(tmp_path):
    cfg = ScrapeConfig(live=True)
    # minimal one-page PDF bytes via reportlab-free stub: reuse the repo spec PDF
    spec = Path(__file__).resolve().parent.parent / "docs" / "Saudi_RAG_Agent_Specification_2.pdf"
    pdf_bytes = spec.read_bytes()

    res = crawl_source("datasaudi", cfg, out_dir=tmp_path, max_pages=1,
                       fetch_html=_fake_html, fetch_pdf=lambda u, c: pdf_bytes)
    assert res.pdfs, res.errors
    doc = markdown_io.read(res.pdfs[0])
    assert doc.frontmatter["extracted"] is True


def test_saudi_ip_source_skipped_without_proxy(tmp_path):
    cfg = ScrapeConfig(live=True)  # no proxy
    res = crawl_source("misa", cfg, out_dir=tmp_path, fetch_html=_fake_html)
    assert res.skipped and "Saudi" in res.skipped


def test_crawl_all_only_open_skips_saudi(tmp_path):
    cfg = ScrapeConfig(live=True)
    results = crawl_all(cfg, out_dir=tmp_path, namespaces=["datasaudi", "misa"],
                        only_open=True, max_pages=1, fetch_html=_fake_html)
    by_ns = {r.namespace: r for r in results}
    assert by_ns["misa"].skipped
    assert by_ns["datasaudi"].skipped is None


def test_crawl_disabled_without_live_flag(tmp_path):
    cfg = ScrapeConfig(live=False)
    res = crawl_source("datasaudi", cfg, out_dir=tmp_path, fetch_html=_fake_html)
    assert res.skipped and "disabled" in res.skipped.lower()
