"""Per-source graph extraction (Phase 4) — our Graphify-equivalent.

Contract matches the spec: one run per source folder produces one graph for that
source (``graphs/<namespace>.json``); a separate merge step (``builder.py``)
combines them into the federated graph.

Extraction is pluggable behind ``ConceptExtractor``:

- ``DeterministicExtractor`` (default) — offline, no LLM. One node per markdown
  page; intra-source edges inferred from in-body links that point at another
  page in the same source. Deterministic and test-stable.
- An LLM-backed extractor (OpenRouter) can implement the same protocol later for
  richer concept/relationship extraction; the merge contract is unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from ..markdown_io import Document, iter_documents
from .model import GEdge, GNode, Graph

_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+")


def _local_id_for(doc: Document) -> str:
    if doc.path is not None:
        return doc.path.stem
    # fall back to a slug of the url path
    from ..scrape.scraper import slug_from_url
    return slug_from_url(doc.url)


def _summary(body: str, limit: int = 280) -> str:
    # first non-heading paragraph, trimmed
    for block in body.split("\n\n"):
        block = block.strip()
        if block and not block.startswith("#"):
            text = re.sub(r"\s+", " ", block)
            return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def _normalize_url(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").lower()


class ConceptExtractor(Protocol):
    name: str

    def extract(self, namespace: str, docs: list[Document]) -> Graph:
        ...


class DeterministicExtractor:
    """Offline extractor: page->node, in-body same-source links -> edges."""

    name = "deterministic"

    def extract(self, namespace: str, docs: list[Document]) -> Graph:
        nodes: list[GNode] = []
        # index this source's pages by normalized url for intra-source linking
        url_to_local: dict[str, str] = {}
        local_ids: dict[int, str] = {}
        for i, doc in enumerate(docs):
            local = _local_id_for(doc)
            local_ids[i] = local
            if doc.url:
                url_to_local[_normalize_url(doc.url)] = local

        for i, doc in enumerate(docs):
            local = local_ids[i]
            fm = doc.frontmatter
            nodes.append(GNode(
                id=local,
                namespace=namespace,
                label=doc.title or local,
                content=doc.body,
                source_url=doc.url,
                personas=list(doc.personas),
                type=fm.get("type", "page"),
                title=doc.title,
                year=fm.get("year"),
                publisher=fm.get("publisher"),
            ))

        edges: list[GEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for i, doc in enumerate(docs):
            local = local_ids[i]
            for raw in _URL_RE.findall(doc.body):
                target_local = url_to_local.get(_normalize_url(raw))
                if target_local and target_local != local:
                    e = GEdge(source=local, target=target_local, type="REFERENCES", origin="intra")
                    if e.key() not in seen:
                        seen.add(e.key())
                        edges.append(e)
        return Graph(namespace=namespace, nodes=nodes, edges=edges)


def extract_source(
    namespace: str,
    source_dir: str | Path,
    extractor: ConceptExtractor | None = None,
) -> Graph:
    """Extract a single source folder into a per-source Graph."""
    extractor = extractor or DeterministicExtractor()
    docs = iter_documents(source_dir)
    return extractor.extract(namespace, docs)
