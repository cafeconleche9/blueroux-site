#!/usr/bin/env bash
# Fetch fresh data, rebuild the site, and publish it to the folder nginx serves.
# If anything fails, the previously published site stays up untouched.
set -euo pipefail
export PYTHONUNBUFFERED=1   # log lines show up in journalctl as they happen

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEBROOT="${WEBROOT:-/var/www/blueroux}"
cd "$REPO"

if [ -f .env ]; then
  set -a; . ./.env; set +a      # YOUTUBE_API_KEY, DISCOGS_TOKEN, DISCORD_WEBHOOK_URL
fi

cd scripts
../.venv/bin/python run_all.py
cd ..

[ -f dist/index.html ] || { echo "build produced no dist/index.html; not publishing" >&2; exit 1; }
rsync -a --delete dist/ "$WEBROOT"/
echo "published to $WEBROOT at $(date -Is)"
