"""Discord webhook alerts. No-op when DISCORD_WEBHOOK_URL is unset.

Warnings are de-duplicated via data/cache/notified.json so the same problem isn't re-sent every day;
a warning is re-sent after it has been absent for a run (i.e. it resolved and came back).
"""
from __future__ import annotations

import os
import sys

import requests

from common import read_cache, redact, write_cache


def _post(content: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    content = redact(content)
    if not url:
        print("notify: DISCORD_WEBHOOK_URL not set; would have sent:\n" + content)
        return
    try:
        requests.post(url, json={"content": content[:1900]}, timeout=15).raise_for_status()
    except requests.RequestException as e:  # alerting must never break the build
        print(f"notify: failed to post to Discord: {e}")


def send_failure(message: str) -> None:
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = f"\n{os.environ.get('GITHUB_SERVER_URL')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    _post(f"🔴 **Blue Roux site update failed**\n{message}{run_url}")


def send_warnings(items: list[dict]) -> None:
    prev = set(read_cache("notified.json", {"keys": []})["keys"])
    current = {i["key"] for i in items}
    fresh = [i for i in items if i["key"] not in prev]
    write_cache("notified.json", {"keys": sorted(current)})
    if fresh:
        lines = "\n".join(f"• [{i['source']}] {i['message']}" for i in fresh[:15])
        more = f"\n…and {len(fresh) - 15} more" if len(fresh) > 15 else ""
        _post(f"🟡 **Blue Roux site: new warnings**\n{lines}{more}")


if __name__ == "__main__":
    # `python notify.py "message"` — used by the workflow's failure step
    send_failure(" ".join(sys.argv[1:]) or "See the workflow run for details.")
