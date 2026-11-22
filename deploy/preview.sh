#!/usr/bin/env bash
# Preview your edits: rebuilds the site from the saved data (no downloading, no keys needed)
# and serves it at http://localhost:8000 . Press Ctrl-C to stop.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../scripts"
SITE_BASE_URL="" ../.venv/bin/python -c "
import build
from common import read_cache
build.run(read_cache('youtube.json'), read_cache('discogs.json'), read_cache('radio.json'), [])
"
echo
echo "Preview: open http://localhost:8000  (Ctrl-C to stop)"
cd ../dist && exec python3 -m http.server 8000 --bind 127.0.0.1
