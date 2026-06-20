# Running the live scrape from a Saudi-region VM

The 22 `.gov.sa` sources are geo-gated to Saudi IPs. The cleanest way to reach
them is a VM whose IP is physically in Saudi Arabia — e.g. **Google Cloud,
Dammam region (`me-central2`)**. From there no VPN/proxy is needed; the VM's
own egress is Saudi.

## 1. Create the VM (Google Cloud, Dammam)

Console or gcloud:

```bash
gcloud compute instances create dream-scrape \
  --zone=me-central2-a \
  --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud
```

`me-central2` is Dammam (zones `-a`/`-b`/`-c`). `e2-small` is plenty.

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

## Notes

- A few portals (**Absher, Nusuk, my.gov.sa**) sit behind login walls / heavy
  bot protection. Even from a Saudi IP, automated scraping may only get public
  landing pages. The script reports per-source errors instead of failing the
  whole run.
- Some fixture-based tests may need updating once real pages replace fixtures —
  review failures, don't blindly delete fixtures.
