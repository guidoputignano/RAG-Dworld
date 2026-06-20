# Dream Arabia

A persona-switchable RAG agent that answers questions about Saudi government
programs, investment, tourism, talent, study, and resident services — every
answer cited to an official source, every flow ending in a named handoff.

Built from two inputs in [`docs/`](docs/): the reference architecture
(`Saudi_RAG_Agent_Specification_2.pdf`) and the source of truth for personas,
data, and behaviour (`Dream_Arabia_Persona_Training_Matrix_2.xlsx`). Where they
disagree, the Excel wins. See [`PLAN.md`](PLAN.md) for the full design and the
per-phase build log.

## Highlights

- **Six personas**, P1 Investor + P2 Entrepreneur launched, P3–P6 scaffolded
  behind config (adding a persona is a config change, not new code).
- **Persona = entry point, not a wall.** It sets where traversal starts; the
  agent still follows cross-source edges into other namespaces.
- **One federated, namespace-tagged graph** (`misa::…`, `monshaat::…`) merged
  from per-source graphs, plus curated cross-entity edges.
- **Vector retrieval** with a namespace filter (pluggable embeddings + vector
  store).
- **Guardrails are a first-class layer**, parsed from the Excel and enforced:
  statistics cited with source + year, every answer ends with a handoff URL +
  named action, and HARD rules (no eligibility confirmation, no tax-rate without
  source, no visa determinations, strict neutrality, religious questions →
  logistics only).
- **Offline-first.** The whole pipeline (graph build, retrieval, agent, API,
  regression) runs with **no API key and no network** using deterministic
  fake-embeddings + a MockLLM. Real embeddings (sentence-transformers),
  OpenRouter LLM, and live scraping are config flips.

## Quickstart (offline)

```bash
pip install -e .                      # or: pip install -e .[embeddings,dev]
cp .env.example .env                  # defaults are offline-safe

# Build the federated graph from fixtures
python -m dream_arabia.graph.builder

# Run the Definition-of-Done regression (replays each persona's sample flow)
python scripts/run_sample_conversations.py

# Serve the API + persona-picker UI
uvicorn dream_arabia.api.app:app --reload   # open http://127.0.0.1:8000/
```

## API

- `POST /session/start` `{persona}` → `{session_id, greeting}`
- `POST /session/message` `{session_id, message}` → `{answer, citations, guardrails_ok, violations, active_nodes}`
- `POST /session/switch` `{session_id, persona}` → resets active nodes
- `GET /` persona-picker UI · `GET /personas` · `GET /health`

Sessions are in memory; `api/sessions.py` marks the Redis seam for production.

## Going live

Set in `.env`: `DREAM_EMBED_PROVIDER=local`, `DREAM_LLM_PROVIDER=openrouter`
(+ `OPENROUTER_API_KEY`, `DREAM_LLM_MODEL`), and for scraping
`DREAM_SCRAPE_LIVE=true` with `DREAM_SCRAPE_PROXY`/`DREAM_SCRAPE_EGRESS_REGION`
(many .gov.sa sources require a Saudi IP). Vector store can move to pgvector via
`DREAM_VECTOR_STORE=pgvector`.

## Tests

```bash
python -m pytest -q
```
