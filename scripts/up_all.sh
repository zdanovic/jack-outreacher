#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

# Load only tunnel vars from .env (не трогаем номера аккаунтов).
echo "[info] Starting stack (API+UI+cloudflared). Ensure ~/.cloudflared has certs/credentials for the tunnel."

docker-compose up -d

echo "[ok] Stack started. UI: http://localhost (or your Cloudflare Tunnel host)"
