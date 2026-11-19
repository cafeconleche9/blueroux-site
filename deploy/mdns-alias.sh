#!/usr/bin/env bash
# Publish blueroux.local -> this machine's current LAN IP over mDNS (Avahi).
# Re-publishes automatically if the IP changes (e.g. DHCP lease changes, wifi reconnect).
set -u
NAME="${1:-blueroux.local}"

current_ip() {
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i+1); exit }}'
}

pid=""
published=""
trap '[ -n "$pid" ] && kill "$pid" 2>/dev/null; exit 0' TERM INT

while true; do
  ip="$(current_ip)"
  if [ -n "$ip" ] && [ "$ip" != "$published" ]; then
    [ -n "$pid" ] && kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null
    avahi-publish -a -R "$NAME" "$ip" &
    pid=$!
    published="$ip"
    echo "published $NAME -> $ip"
  elif [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    published=""   # avahi-publish died (e.g. avahi restarted): publish again next loop
  fi
  sleep 20
done
