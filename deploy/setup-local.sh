#!/usr/bin/env bash
# One-time setup for hosting the site on the local network at http://blueroux.local
# Run with:  sudo ./deploy/setup-local.sh
# Safe to re-run. Then run ./deploy/install-timer.sh as your normal user (no sudo).
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo:  sudo $0" >&2; exit 1; fi
USER_NAME="${SUDO_USER:-}"
[ -n "$USER_NAME" ] && [ "$USER_NAME" != root ] || { echo "Run via sudo from your normal account." >&2; exit 1; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAN="${LAN_CIDR:-192.168.0.0/24}"
WEBROOT=/var/www/blueroux

echo "==> Installing packages (nginx, avahi-utils, rsync)"
apt-get install -y nginx avahi-utils rsync

echo "==> Web root: $WEBROOT (owned by $USER_NAME so updates don't need sudo)"
install -d -o "$USER_NAME" -g "$USER_NAME" "$WEBROOT"
if [ ! -f "$WEBROOT/index.html" ]; then
  echo "<!doctype html><title>Blue Roux</title><p>Site not built yet. Run: systemctl --user start blueroux-update" > "$WEBROOT/index.html"
  chown "$USER_NAME:$USER_NAME" "$WEBROOT/index.html"
fi

echo "==> nginx site"
install -m 644 "$REPO/deploy/nginx-blueroux.conf" /etc/nginx/sites-available/blueroux
ln -sf /etc/nginx/sites-available/blueroux /etc/nginx/sites-enabled/blueroux
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> mDNS name: blueroux.local"
install -m 755 "$REPO/deploy/mdns-alias.sh" /usr/local/bin/blueroux-mdns
sed -e "s#@REPO@#$REPO#g" -e "s#@USER@#$USER_NAME#g" "$REPO/deploy/blueroux-mdns.service" > /etc/systemd/system/blueroux-mdns.service
systemctl daemon-reload
systemctl enable blueroux-mdns.service
systemctl restart blueroux-mdns.service   # restart (not just start) so a re-run picks up changes
sleep 3
if avahi-resolve -n blueroux.local >/dev/null 2>&1; then
  echo "    blueroux.local resolves ✓"
else
  echo "    WARNING: blueroux.local does not resolve yet. Check: journalctl -u blueroux-mdns -n 20"
fi

echo "==> Firewall (ufw): allow web + mDNS from the home network only"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow from "$LAN" to any port 80 proto tcp comment 'blueroux site (LAN only)'
  ufw allow from "$LAN" to any port 5353 proto udp comment 'mDNS (LAN only)'
else
  echo "ufw not active; skipping"
fi

echo "==> Let $USER_NAME's timers run while logged out"
loginctl enable-linger "$USER_NAME"

echo
echo "Done. Next, as your normal user (no sudo):  $REPO/deploy/install-timer.sh"
echo "Then visit http://blueroux.local from any device on the wifi."
