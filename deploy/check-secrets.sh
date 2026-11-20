#!/usr/bin/env bash
# Refuse to publish if any API key/token could end up on GitHub.
#
#   deploy/check-secrets.sh            check every file git would upload (run before pushing)
#   deploy/check-secrets.sh --history  also check every past commit (run before making the repo public)
#
# Looks for the actual values in .env, plus the shapes of Google API keys and Discord webhook URLs.
# Matching values are never printed, only the file (or commit) they're in.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

values=()
if [[ -f .env ]]; then
  while IFS='=' read -r k v; do
    [[ "$k" =~ ^[[:space:]]*# || -z "$k" ]] && continue
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    [[ ${#v} -ge 8 ]] && values+=("$v")
  done < .env
fi
patterns='AIza[0-9A-Za-z_-]{35}|discord(app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+'

fail=0
report() { echo "  ✗ $1"; fail=1; }

# .env itself must be ignored
if ! git check-ignore -q .env; then report ".env is NOT ignored by git (add it to .gitignore)"; fi

echo "Checking files git would upload…"
mapfile -d '' files < <(git ls-files -z --cached --others --exclude-standard)
for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  for v in "${values[@]}"; do
    grep -qF -- "$v" "$f" && report "$f contains a value from .env"
  done
  grep -qE -- "$patterns" "$f" && report "$f contains something that looks like an API key or webhook URL"
done

# the built site isn't in git, but it's what GitHub Pages publishes
if [[ -d dist ]]; then
  echo "Checking the built site (dist/)…"
  for v in "${values[@]}"; do
    grep -rlF -- "$v" dist | while read -r f; do echo "  ✗ $f contains a value from .env"; done | grep . && fail=1
  done
  grep -rlE -- "$patterns" dist | while read -r f; do echo "  ✗ $f contains something that looks like an API key or webhook URL"; done | grep . && fail=1
fi

if [[ "${1:-}" == "--history" ]] && git rev-parse -q --verify HEAD >/dev/null; then
  echo "Checking every past commit…"
  for c in $(git rev-list --all); do
    body="$(git show --format= -p "$c")"
    for v in "${values[@]}"; do
      grep -qF -- "$v" <<<"$body" && report "commit $c contains a value from .env"
    done
    grep -qE -- "$patterns" <<<"$body" && report "commit $c contains something that looks like an API key or webhook URL"
  done
fi

if (( fail )); then
  echo "Secrets found: don't push. Remove them (and, if already committed, ask for help rewriting history)."
  exit 1
fi
echo "  ✓ no secrets found (${#values[@]} .env values and key/webhook patterns checked)"
