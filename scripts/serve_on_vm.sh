#!/usr/bin/env bash
#
# Run the Dream Arabia API + persona-picker UI as a persistent systemd service.
# Run this AFTER the data is in place (scripts/scrape_on_vm.sh, or knowledge_base/
# + graphs/ already present). Installs a systemd unit so the server survives
# reboots and crashes.
#
# Usage:
#   bash scripts/serve_on_vm.sh             # install + start on port 8000
#   PORT=8080 bash scripts/serve_on_vm.sh
#
# Provider config (real LLM/embeddings) is read from a .env file in the repo
# root if present — e.g. DREAM_LLM_PROVIDER=openrouter, OPENROUTER_API_KEY=...,
# DREAM_EMBED_PROVIDER=local. Without it, the offline MockLLM defaults are used.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PORT="${PORT:-8000}"
SERVICE="dream-arabia"
VENV="$REPO_ROOT/.venv"

echo "==> 1/4  Python environment"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e .

echo "==> 2/4  Ensure the federated graph exists"
if [ ! -f graphs/federated_graph.json ]; then
  echo "    building graph from knowledge_base/ ..."
  "$VENV/bin/python" -m dream_arabia.graph.builder
fi

echo "==> 3/4  Install systemd service '$SERVICE' (port $PORT)"
ENVLINE=""
if [ -f "$REPO_ROOT/.env" ]; then ENVLINE="EnvironmentFile=$REPO_ROOT/.env"; fi
sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<UNIT
[Unit]
Description=Dream Arabia RAG API + UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$REPO_ROOT
$ENVLINE
ExecStart=$VENV/bin/uvicorn dream_arabia.api.app:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"

echo "==> 4/4  Status"
sleep 2
sudo systemctl --no-pager --full status "$SERVICE" | head -n 12 || true

IP="$(python3 - <<'PY'
import httpx
try: print(httpx.get("https://ipinfo.io/ip", timeout=10).text.strip())
except Exception: print("<vm-external-ip>")
PY
)"
cat <<DONE

============================================================
Service '$SERVICE' is running on port $PORT.
  UI:     http://$IP:$PORT/
  health: http://$IP:$PORT/health

One-time firewall rule (if not added yet):
  gcloud compute firewall-rules create allow-dream-api \\
    --allow=tcp:$PORT --source-ranges=0.0.0.0/0 --target-tags=dream

Logs:    sudo journalctl -u $SERVICE -f
Restart: sudo systemctl restart $SERVICE
Stop:    sudo systemctl disable --now $SERVICE

For a domain + automatic HTTPS, see deploy/Caddyfile (then you can bind
uvicorn to 127.0.0.1 and expose only 80/443).
============================================================
DONE
