# Dream Arabia — Build Plan

A persona-switchable RAG agent answering questions about Saudi government
programs, investment, tourism, talent, study, and resident services — every
answer cited to an official source, every flow ending in a named handoff.

This plan reconciles two inputs in `./docs/`:

- `Saudi_RAG_Agent_Specification_2.pdf` — reference architecture (baseline pipeline).
- `Dream_Arabia_Persona_Training_Matrix_2.xlsx` — **source of truth** for personas,
  training data, and behaviour rules.

**Where the two disagree, the Excel wins.** This document records every place
they diverge and what I'm building instead.

> Status: **AWAITING APPROVAL.** No phase code has been written. Phase 1 does
> not start until you confirm this plan.

---

## 1. What I read

**PDF (11 pages):** five-layer pipeline (scrape → PDF extract → graph build →
agent → UI); markdown-as-universal-format with frontmatter; per-source graph
extraction merged into ONE federated, namespace-tagged graph; in-memory graph
with `get_nodes_by_namespace` / `semantic_search` / `traverse(max_hops)`;
persona = entry point not a filter; FastAPI with `start` / `message` / `switch`;
history capped at 6 turns; weekly cron re-scrape. The PDF assumes **three**
sources (Monshaat, MISA, Visit Saudi), **three** personas, **keyword** search,
and proprietary "Graphify" for extraction.

**Excel (11 tabs):** README, Persona Overview, six persona tabs (P1–P6), Master
PDF Library (PDF-01…PDF-10), Master URL Index (T1–T4, 41 entities), Guardrails
Matrix (15 risk domains). Each persona tab carries: profile, trigger signals, a
5-stage user flow (Discovery → Intent → Reasoning → Matchmaking → Handoff),
training PDFs, training URLs (with `Saudi IP` / `OPEN` access notes), a
persona-specific **AI Behaviour Rules** table (with HARD/SOFT severity), and a
**Sample Conversation Flow** used as the regression target.

---

## 2. Reconciliation — where Excel overrides the PDF

| Topic | PDF baseline | Excel / kickoff (what we build) |
|---|---|---|
| Personas | 3 (Investor, Entrepreneur, Tourist) | **6**: P1 Investor, P2 Entrepreneur, P3 Tourist, P4 Foreign Talent, P5 Student, P6 Citizen/Resident. Build **P1+P2** first; P3–P6 scaffolded behind config. |
| Sources | 3 (monshaat, misa, visitsaudi) | **41 official entities** across 4 tiers (Master URL Index) + 10 PDFs. Modelled as configurable `SOURCES`. |
| Persona scope | entry point, not filter | Same — **kept**. Persona sets START namespaces; traversal still follows cross-source edges. |
| Retrieval | keyword matching (placeholder) | **Vector embeddings from the start**, with namespace filter. Keyword version skipped. |
| Guardrails | mentioned implicitly | **First-class layer.** Parse per-persona AI Behaviour Rules + Guardrails Matrix into a structured ruleset; enforce HARD rules in the agent. |
| Graph extraction | proprietary "Graphify" CLI | Our own per-source extractor with the **same contract** (one graph per source → merge → namespace-injected federated graph). See §4. |
| LLM | "Claude API" + LangChain | LLM via **OpenRouter** (pluggable model/agent), no LangChain dependency required. |
| Statistics | source attribution | Stronger: **every statistic carries source name + year**; data >12 months flagged (Guardrails Matrix). |
| Handoff | "source cited" | Stronger: **every flow ends with a specific URL + a named action**, never "visit the site." |

Nothing in the Excel is silently dropped. Items I'm interpreting rather than
copying verbatim are listed in §9 (Assumptions) and §10 (Questions).

---

## 3. Personas → namespaces

Persona = **entry namespaces** for traversal (not a hard filter). Drawn from each
persona tab's "Training Data · URLs" plus the Master URL Index cross-references.

| ID | Persona | Priority | Primary handoff | Entry namespaces (START set) |
|---|---|---|---|---|
| P1 | Investor | **LAUNCH** | `investsaudi.sa/en` | misa, investsaudi, mim, pif, ecza, svc, kafd, pr, vision2030, datasaudi |
| P2 | Entrepreneur | **LAUNCH** | `misa.gov.sa/en` | misa, investsaudi, monshaat, svc, mim, sdaia, hrsd, pr, magnitt, datasaudi |
| P3 | Tourist | Phase 2 | `visitsaudi.com/en` | visitsaudi, webook, sta, mt, experiencealula, diriyah, redseaglobal, neom, qiddiya, amaala, nusuk, saudia, flynas, datasaudi |
| P4 | Foreign Talent | Phase 2 | `pr.gov.sa` | pr, hrsd, absher, misa, kafd, vision2030, datasaudi, visitsaudi |
| P5 | Student | Phase 3 | university portal | kfupm, kaust, ksu, kau, pnu, iau, seu, moe, vision2030 |
| P6 | Citizen/Resident | Phase 3 | `my.gov.sa/en` | mygov, absher, hrsd, moh, moe, zatca, splonline |

Adding a persona = a config change (`PERSONA_NAMESPACE_MAP` + a guardrail block),
not new code. P3–P6 ship in config and fixtures but are gated to "scaffolded" so
launch focuses on P1/P2.

---

## 4. Architecture & technology choices (with rationale)

Stack pinned by the kickoff: **Playwright + httpx** (scrape), **markdownify**
(HTML→md), **pdfplumber + OCR fallback** (PDF), **FastAPI** (API). My judgement
calls below; flag any you want changed.

**Graph store — `networkx.DiGraph`, loaded once at startup from
`federated_graph.json`.** The PDF explicitly wants in-memory traversal; the
dataset (programs/visas/rules) is small (hundreds–low-thousands of nodes). A
graph DB (Neo4j) adds infra for no benefit at this scale. JSON-on-disk keeps the
"N graphs at build time, one at query time" property and stays diff-able in git.

**Embeddings — pluggable provider behind one interface, three backends:**
1. `sentence-transformers/all-MiniLM-L6-v2` (local, default for real dev) — free,
   offline after first model download, 384-dim, strong for short program text.
2. OpenAI / OpenRouter-hosted embeddings (optional, config-selected).
3. **Deterministic hashing embedder** (`FakeEmbedder`) for CI/offline tests —
   zero network, reproducible, so the whole build+test loop runs with no model
   download and no API key.

**Vector store — in-memory NumPy cosine index, default.** With a documented
**pgvector** adapter behind the same interface for production scale. The kickoff
says "pgvector is fine," not required; for fixture-scale offline dev, an
in-memory index removes the Postgres dependency while keeping the swap trivial.

**Agent LLM — via OpenRouter**, model configurable (default a Claude model id on
OpenRouter). A `MockLLM` provider returns deterministic, context-grounded answers
for offline regression tests so the Definition-of-Done checks (citation, handoff,
guardrails) run without network. Guardrail enforcement and citation/handoff
formatting are **deterministic post-processing**, not left to the LLM's goodwill.

**Graph extraction — our own extractor replacing "Graphify"**, same contract:
`extract(source_dir) -> graphs/<ns>.json`, then `graph_builder.py` merges +
injects `namespace::` into every node id and folds in
`cross_entity/cross_entity_edges.json`. Extractor is pluggable: an LLM-backed
mode (OpenRouter) for richness, and a deterministic frontmatter/heading-based
mode (default) so the graph builds offline from fixtures.

**Why these together:** the entire pipeline — config, fixtures, graph build,
retrieval, agent, API, regression — runs **offline with no API key** using the
Fake/Mock providers, and upgrades to real embeddings + real LLM + live scrape by
flipping config. That directly serves the "do NOT scrape live during dev; wire
real scraping last behind a flag" constraint.

---

## 5. Repository layout

```
RAG-Dworld/
  docs/                         # the PDF + Excel (committed)
  PLAN.md
  .env.example
  pyproject.toml                # deps + tool config
  config/
    sources.py                  # SOURCES: namespace, url, access(Saudi IP/OPEN), tier, personas
    personas.py                 # PERSONA_NAMESPACE_MAP, priorities, handoff URLs
    guardrails_loader.py        # parse docs/*.xlsx -> structured ruleset
    guardrails.generated.json   # committed snapshot of the parsed ruleset
  knowledge_base/
    misa/ *.md                  # fixtures (frontmatter md) — Phase 1
    monshaat/ *.md              # fixtures — Phase 1
    <other ns>/ ...             # added per phase
    cross_entity/cross_entity_edges.json
  graphs/                       # per-source + federated_graph.json (build artifacts)
  src/dream_arabia/
    extract/pdf_extractor.py    # pdfplumber -> OCR fallback -> frontmatter md
    scrape/scraper.py           # Playwright/httpx -> md, proxy-configurable, OFF by default
    graph/extractor.py          # per-source node/edge extraction (Graphify replacement)
    graph/builder.py            # merge + namespace injection + cross-entity edges
    graph/query.py              # get_by_namespace / semantic_search / traverse(max_hops)
    embeddings/                 # provider interface + local/openrouter/fake
    vectorstore/                # numpy index (+ pgvector adapter)
    llm/                        # OpenRouter client + MockLLM
    guardrails/engine.py        # HARD/SOFT enforcement + citation/handoff validators
    agent/core.py               # persona->entry ns, retrieve, traverse, format cited context
    api/app.py                  # FastAPI: /session/start | /message | /switch
    ui/                         # minimal persona-picker UI
  scripts/
    run_sample_conversations.py # smoke test from each persona tab's Sample Flow
  tests/
```

---

## 6. Guardrails design (first-class layer)

Parsed from the Excel into a structured ruleset; each rule:
`{persona, rule_type, domain, trigger, required_response_pattern, severity, route_url}`.

Sources merged: the **Guardrails Matrix** (15 cross-persona domains, risk level,
MUST-NOT / MUST, persona impact) + each persona tab's **AI Behaviour Rules**
(rule_type, rule, trigger, required response, HARD/SOFT).

HARD rules enforced in the agent (examples drawn directly from the Excel):
- Never confirm individual eligibility (RHQ, Premium Residency, Iqama, admission).
- Never quote tax rates / incentive %ages / Nitaqat quotas without an official source URL.
- Never make visa/immigration determinations; route to Absher + suggest legal counsel.
- Strict neutrality on Saudi politics/royal family and on competitor jurisdictions.
- Religious/Hajj questions → logistics only (Nusuk); Mecca/Medina = Muslims-only, stated factually.
- Never describe unbuilt giga-project phases as operational.
- Every statistic → source name + year; flag data >12 months old.
- Every flow ends with a specific handoff URL + a named action.

Enforcement is a deterministic layer that (a) injects the relevant rules into the
system prompt, and (b) post-validates the answer (citation present where a stat
appears, handoff URL+action present, no forbidden pattern), rewriting/blocking on
HARD violations.

---

## 7. Build phases

Each phase: code + a test + a one-line note appended to PLAN.md, **then pause.**

1. **Scaffold & config.** Repo skeleton, `pyproject`, `.env.example`; `SOURCES`,
   `PERSONA_NAMESPACE_MAP`, `guardrails_loader` (Excel→ruleset, committed
   snapshot); fixtures for **2 sources** (misa, monshaat), 3–5 frontmatter md
   pages each. *Test:* config + guardrails load; fixtures have valid frontmatter.
2. **PDF extraction.** `pdfplumber` → OCR fallback → frontmatter markdown. *Test:*
   extract a sample PDF (the spec PDF) to md with correct frontmatter.
3. **Scraper.** Playwright/httpx → markdownify → frontmatter; proxy/egress-region
   configurable; **off by default** (flag-gated). *Test:* scraper parses a local
   HTML fixture to md offline; live mode refuses unless flag+proxy set.
4. **Graph extraction + merge.** Per-source extractor → `graphs/<ns>.json`;
   `builder.py` merges + injects `namespace::` + folds in curated
   `cross_entity_edges.json`. *Test:* federated graph has namespaced ids and the
   cross-entity edges present.
5. **Query engine.** `get_nodes_by_namespace`, embedding `semantic_search` with
   namespace filter, `traverse(start, max_hops)` BFS. *Test:* search returns
   in-namespace hits; traverse crosses a cross-entity edge within max_hops.
6. **Agent core.** persona→entry namespaces, retrieve, traverse from active nodes,
   format cited context, OpenRouter LLM (+MockLLM), guardrail enforcement, history
   cap 6 turns. *Test:* a P1 question yields cited context + handoff; a HARD-rule
   trigger is enforced.
7. **FastAPI.** `/session/start`, `/session/message`, `/session/switch`; in-memory
   sessions (note where Redis slots in). *Test:* full start→message→switch cycle.
8. **UI + smoke tests.** Minimal persona-picker UI; `run_sample_conversations.py`
   replays each persona tab's Sample Conversation Flow. *Test:* P1 & P2 sample
   flows pass the Definition of Done.

---

### Phase notes (appended as each phase completes)

- **Phase 1 ✅** — Scaffold + config done. `SOURCES` (42 entities, 4 tiers),
  `PERSONA_NAMESPACE_MAP` (derived from source membership), `PDF_LIBRARY` (10),
  guardrails parsed from the Excel into 47 rules (33 HARD / 14 SOFT) with a
  committed JSON snapshot, `.env.example` (offline-safe defaults), frontmatter
  markdown util, and 4+4 fixtures for misa/monshaat. 16 tests pass.

- **Phase 2 ✅** — PDF extraction pipeline: `pdfplumber` text → pluggable **OCR
  fallback** (Tesseract if installed, else `NullOCR` that flags pages —
  offline-safe) → frontmatter markdown identical in shape to scraped pages.
  Running headers/footers (incl. page-numbered footers) stripped; CLI + library
  API. 5 new tests (21 total) pass.

- **Phase 3 ✅** — Scraper: httpx (static) + Playwright (JS, lazy/optional) →
  markdownify → frontmatter markdown, same shape as PDFs. **Live scraping off by
  default** (`ensure_allowed` refuses unless `DREAM_SCRAPE_LIVE=true`, and
  refuses Saudi-IP sources without a proxy/egress). Pure offline path:
  HTML→markdown, PDF-link + internal-link discovery, slugging. 8 new tests (29
  total) pass.

- **Phase 4 ✅** — Per-source graph extraction (Graphify-equivalent, pluggable;
  `DeterministicExtractor` default: page→node, in-body sibling links→intra edges)
  → `graphs/<ns>.json`, then `builder.py` merges into `federated_graph.json` with
  `namespace::` injected into every node id + edge endpoint, and folds in the
  curated `cross_entity/cross_entity_edges.json` (validates endpoints; dangling
  edges skipped **and reported**, not dropped). Fixture build: 8 nodes, 5 edges
  (2 intra + 3 cross, 1 dangling skipped). 7 new tests (36 total) pass.

- **Phase 5 ✅** — Query engine over the federated graph: `get_nodes_by_namespace`,
  `semantic_search` (embedding similarity with a namespace *filter*, not a wall)
  and `traverse(start, max_hops)` BFS that follows cross-namespace edges.
  Pluggable embeddings (`fake` default / `local` sentence-transformers /
  `openrouter`) + in-memory NumPy cosine vector store (pgvector adapter stubbed
  behind the same interface). 12 new tests (45 total) pass.

- **Phase 6 ✅** — Agent core: persona→entry namespaces, semantic search +
  cross-source traverse (1 hop from retrieved, 2 from prior active nodes), cited
  context formatting, LLM via **OpenRouter** (configurable model) with an offline
  **MockLLM** that composes compliant answers from the structured context.
  **Guardrail engine** renders persona HARD/SOFT rules into the system prompt and
  validates/enforces output (handoff URL + named action, statistics carry
  source+year, negation-aware HARD forbidden patterns: eligibility confirmation,
  guaranteed outcomes, tax-rate-without-source, visa determinations). History
  capped at 6 turns; persona switch resets active nodes. 17 new tests (56 total).

## 8. Definition of done

Replay the **Sample Conversation Flow** from each persona tab as a regression
test. Each answer must:
- cite an official source **with year** wherever a statistic appears,
- end with the persona's **handoff URL + a named action**,
- respect **every HARD guardrail** for that persona.

Launch gate: P1 and P2 pass. P3–P6 wired in config/fixtures and pass as they're
turned on.

---

## 9. Assumptions (forced)

1. **"Graphify" is unavailable**, so I implement an equivalent extractor with the
   same per-source→merge→namespace contract. (Deviation from PDF, not Excel.)
2. **Offline-first dev:** real embeddings/LLM/scrape need network or keys, which
   the kickoff forbids during dev — so Fake/Mock providers are the defaults and
   real providers are config-flipped. Behaviour/citation/handoff are validated
   deterministically so tests don't depend on a live model.
3. **Namespaces** are derived one-per-entity from the Master URL Index (e.g.
   `misa`, `investsaudi`, `pr`, `kfupm`). Personas with no persona-specific PDFs
   (P5, P6) rely on URL-derived fixtures + base stats, per the Excel notes.
4. **Fixtures, not live data:** fixture markdown approximates real page content
   for build/test. It is clearly marked as fixture and is not authoritative.
5. **README "don't cross-pollinate" knowledge slices** is honored at *training/
   ingestion* (each namespace ingested cleanly), while the agent still traverses
   cross-source edges at query time per "persona = entry point." These aren't in
   conflict: clean slices at build, federated traversal at query.
6. **Embedding model** `all-MiniLM-L6-v2` and **OpenRouter default model** are
   starting choices, easily swapped in config.

## 10. Questions before I start (please confirm)

1. **Vector store default:** OK to default to in-memory NumPy for dev/test with a
   pgvector adapter documented for prod? (Alternative: stand up Postgres+pgvector
   now.) — *Recommended: in-memory now.*
2. **OpenRouter default model:** any preferred model id (e.g. a specific Claude),
   or shall I pick a sensible default and leave it configurable?
3. **Scope of "launch first":** confirm P1+P2 fully built end-to-end this pass,
   P3–P6 only scaffolded (config + fixtures + guardrails parsed, not regression-
   gated) — matching the kickoff.
4. **Fixtures content:** fine for me to author plausible fixture pages grounded in
   the real URLs/PDF titles from the Excel (clearly marked as fixtures), given we
   are not scraping live?

Once you approve (and answer 1–4), I'll start **Phase 1** and pause after it.
