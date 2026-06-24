#!/usr/bin/env bash
#
# One-shot live scrape from a Saudi-region VM (e.g. Google Cloud Dammam,
# me-central2). Run this on the VM after cloning the repo and checking out
# the working branch. Because the VM already has a Saudi IP, no VPN/proxy is
# needed — we only set DREAM_SCRAPE_EGRESS_REGION so the scraper's safety gate
# allows the .gov.sa (Saudi-IP-gated) sources.
#
# Usage:
#   bash scripts/scrape_on_vm.sh            # scrape ALL 42 sources + rebuild graph
#   OPEN_ONLY=1 bash scripts/scrape_on_vm.sh   # only the 20 OPEN sources
#   MAX_PAGES=8 bash scripts/scrape_on_vm.sh   # crawl more pages per source
#
# It deliberately STOPS after printing the scrape summary + test results so you
# can review before committing. Commit/push commands are printed at the end.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> 1/5  System dependencies"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-venv python3-pip git
fi

echo "==> 2/5  Python environment"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e .

echo "==> 3/5  Verify this VM has a Saudi IP"
COUNTRY="$(python - <<'PY'
import httpx
try:
    print(httpx.get("https://ipinfo.io/country", timeout=15).text.strip())
except Exception as e:
    print("UNKNOWN")
PY
)"
echo "    Detected egress country: ${COUNTRY}"
if [ "${COUNTRY}" != "SA" ]; then
  echo "    !! WARNING: egress country is '${COUNTRY}', not 'SA'."
  echo "    !! The 22 .gov.sa sources will likely refuse. Run this on a Saudi-region VM."
  echo "    !! Continuing anyway in 5s (Ctrl-C to abort)…"
  sleep 5
fi

echo "==> 4/5  Live scrape"
SCRAPE_ARGS="--all --rebuild"
if [ "${OPEN_ONLY:-0}" = "1" ]; then
  SCRAPE_ARGS="--rebuild"   # default crawl_all(only_open=True) when --all is absent
fi
export DREAM_SCRAPE_LIVE=true
export DREAM_SCRAPE_EGRESS_REGION="${DREAM_SCRAPE_EGRESS_REGION:-sa}"
# shellcheck disable=SC2086
python scripts/scrape_sources.py ${SCRAPE_ARGS} --max-pages "${MAX_PAGES:-5}"

echo "==> 5/5  Test suite + Definition-of-Done regression"
python -m pytest -q || echo "    !! pytest reported failures — review above (fixtures may need updating)."
python scripts/run_sample_conversations.py || echo "    !! DoD regression reported failures — review above."

cat <<'NEXT'

============================================================
Scrape complete. REVIEW the summary above before committing.

If it looks good, commit + push from this VM:

  git add knowledge_base graphs
  git commit -m "Live scrape: real pages + rebuilt federated graph"
  git push -u origin claude/dazzling-bohr-i2mz8v

(The VM needs git auth — a GitHub PAT or `gh auth login`.)
Or copy knowledge_base/ + graphs/ back to your machine and commit there.
============================================================
NEXT
