#!/usr/bin/env bash
# Install the daily update timer as a systemd *user* unit. Run as your normal user (no sudo).
set -euo pipefail
[ "$(id -u)" -ne 0 ] || { echo "Run as your normal user, not root." >&2; exit 1; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"
for f in blueroux-update.service blueroux-update-failed.service; do
  sed "s#@REPO@#$REPO#g" "$REPO/deploy/$f" > "$DEST/$f"
done
cp "$REPO/deploy/blueroux-update.timer" "$DEST/"

chmod +x "$REPO/deploy/update.sh" "$REPO/deploy/mdns-alias.sh"
[ -f "$REPO/.env" ] && chmod 600 "$REPO/.env" || echo "NOTE: no .env yet. Copy .env.example to .env and add your keys."

systemctl --user daemon-reload
systemctl --user enable --now blueroux-update.timer
systemctl --user list-timers blueroux-update.timer --no-pager
echo
echo "Update now:   systemctl --user start --no-block blueroux-update"
echo "Watch it:     journalctl --user -fu blueroux-update   (Ctrl-C stops watching, not the job)"
echo "Result:       systemctl --user status blueroux-update"
