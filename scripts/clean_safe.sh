#!/usr/bin/env bash
# Safe cleanup script:
# - stops the stack
# - snapshots data/sessions volumes to backups/<timestamp>/
# - prunes containers/images/networks/build cache
# - DOES NOT prune volumes (to avoid data loss)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_NAME="$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]')"
DATA_VOL="${PROJECT_NAME}_app_data"
SESS_VOL="${PROJECT_NAME}_app_sessions"

timestamp="$(date -u +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT_DIR/backups/$timestamp"
mkdir -p "$BACKUP_DIR"

echo "[info] Using volumes: $DATA_VOL, $SESS_VOL"
echo "[info] Backup dir: $BACKUP_DIR"

need_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[error] docker not found in PATH"; exit 1
  fi
}

backup_volume() {
  local vol="$1"
  local out="$2"
  if ! docker volume inspect "$vol" >/dev/null 2>&1; then
    echo "[warn] volume '$vol' not found. Skipping backup for it."
    return 0
  fi
  echo "[info] Snapshotting volume $vol -> $out"
  docker run --rm -v "$vol:/data:ro" -v "$BACKUP_DIR:/backup" alpine sh -c "
    set -e
    if ls -A /data >/dev/null 2>&1; then
      cd /data && tar czf \"/backup/$out\" .
    else
      echo '' | tar czf \"/backup/$out\" -T -  # create empty tar
    fi
  "
}

need_docker

echo "[step] Stopping stack"
docker compose down --remove-orphans || true

echo "[step] Backing up volumes"
backup_volume "$DATA_VOL" "app_data.tgz"
backup_volume "$SESS_VOL" "app_sessions.tgz"

echo "[step] Pruning containers/networks/images/build cache (volumes untouched)"
docker container prune -f
docker network prune -f
docker image prune -af
docker builder prune -af

echo "[done] Cleanup complete. Backups: $BACKUP_DIR"
echo "[info] Start stack with: ./scripts/up_all.sh"
