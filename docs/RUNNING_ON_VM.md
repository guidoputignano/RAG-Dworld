# Running the live scrape from a Saudi-region VM

The 22 `.gov.sa` sources are geo-gated to Saudi IPs. The cleanest way to reach
them is a VM whose IP is physically in Saudi Arabia — e.g. **Google Cloud,
Dammam region (`me-central2`)**. From there no VPN/proxy is needed; the VM's
own egress is Saudi.

## 1. Create the VM (Google Cloud, Dammam)

`me-central2` is Dammam (zones `-a`/`-b`/`-c`).

**Scrape-only VM** (delete it after; `e2-small` is plenty):

```bash
gcloud compute instances create dream-scrape \
  --zone=me-central2-a \
  --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud
```

**Scrape + keep it running as a public API/UI server** (more RAM for real
providers, a static IP, a firewall tag, and a bigger disk):

```bash
# one-time: reserve a static IP and open the API port
gcloud compute addresses create dream-ip --region=me-central2
gcloud compute firewall-rules create allow-dream-api \
  --allow=tcp:8000 --source-ranges=0.0.0.0/0 --target-tags=dream

gcloud compute instances create dream-arabia \
  --zone=me-central2-a \
  --machine-type=e2-medium \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --tags=dream --address=dream-ip
```

Use `e2-standard-2` (8 GB) if you'll run **local** embeddings *and* expect real
traffic. The Saudi location is only required for *scraping*; serving the scraped
data needs no Saudi IP, but Dammam keeps latency low for Saudi users.

## 2. SSH in and clone the branch

```bash
gcloud compute ssh dream-scrape --zone=me-central2-a

# on the VM:
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/guidoputignano/RAG-Dworld.git
cd RAG-Dworld
git checkout claude/dazzling-bohr-i2mz8v
```

## 3. Run the one-shot scrape

```bash
bash scripts/scrape_on_vm.sh
```

This installs deps, **verifies the VM's egress country is `SA`**, scrapes all
42 sources (OPEN + `.gov.sa`), rebuilds `graphs/federated_graph.json`, then runs
the test suite and the Definition-of-Done regression. It stops before committing
so you can review the summary.

Variants:

```bash
OPEN_ONLY=1 bash scripts/scrape_on_vm.sh   # only the 20 OPEN sources
MAX_PAGES=8 bash scripts/scrape_on_vm.sh   # crawl more pages per source
```

### What it runs under the hood

```bash
DREAM_SCRAPE_LIVE=true DREAM_SCRAPE_EGRESS_REGION=sa \
  python scripts/scrape_sources.py --all --rebuild
```

`DREAM_SCRAPE_EGRESS_REGION=sa` satisfies the scraper's safety gate (which
refuses `.gov.sa` sources unless an egress region or proxy is declared). The VM
is already in Saudi, so traffic routes natively — no proxy URL required.

## 4. Commit + push (after reviewing the summary)

The VM needs git auth (a GitHub PAT, or `gh auth login`):

```bash
git add knowledge_base graphs
git commit -m "Live scrape: real pages + rebuilt federated graph"
git push -u origin claude/dazzling-bohr-i2mz8v
```

Or copy `knowledge_base/` + `graphs/` back to your machine and commit there.

## 5. (Optional) Keep it running as a public server

After the data is in place, serve the API + persona-picker UI as a persistent
`systemd` service:

```bash
bash scripts/serve_on_vm.sh        # installs + starts on :8000, survives reboots
```

Then open `http://<vm-external-ip>:8000/`. To use real answers instead of the
offline MockLLM, drop a `.env` in the repo root before running (e.g.
`DREAM_LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...`,
`DREAM_EMBED_PROVIDER=local`) — `serve_on_vm.sh` wires it into the service.

For a domain + automatic HTTPS, put Caddy in front (`deploy/Caddyfile`); then you
can bind uvicorn to `127.0.0.1` and expose only 80/443.

> ⚠️ Exposing the API publicly means anyone can call the agent (which may use a
> paid LLM). Before real users: add HTTPS, and consider an API key / rate limit.

## Notes

- A few portals (**Absher, Nusuk, my.gov.sa**) sit behind login walls / heavy
  bot protection. Even from a Saudi IP, automated scraping may only get public
  landing pages. The script reports per-source errors instead of failing the
  whole run.
- Some fixture-based tests may need updating once real pages replace fixtures —
  review failures, don't blindly delete fixtures.
