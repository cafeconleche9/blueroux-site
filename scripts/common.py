"""Shared helpers: config, JSON cache, polite HTTP, warning collection."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
DIST = ROOT / "dist"


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_yaml(rel: str) -> dict:
    p = ROOT / rel
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}


def read_cache(name: str, default=None):
    p = CACHE / name
    if not p.exists():
        return default
    return json.loads(p.read_text())


def write_cache(name: str, data) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
    tmp.replace(CACHE / name)


def valid_id(v) -> bool:
    """True for a real Discogs id. Credits with no page of their own come through as
    None / "None" / 0 (e.g. "Not On Label"); those must be skipped, not int()'d."""
    s = str(v)
    return s.isdigit() and int(s) > 0


SECRET_ENV_VARS =("YOUTUBE_API_KEY", "DISCOGS_TOKEN", "DISCORD_WEBHOOK_URL")


def redact(text: str) -> str:
    """Replace any secret's value with *** so error text can never leak it to the
    status page, the committed cache, or Discord."""
    for name in SECRET_ENV_VARS:
        val = os.environ.get(name)
        if val and len(val) >= 4:
            text = text.replace(val, "***")
    return text


def print_exc() -> None:
    """traceback.print_exc(), but with secrets scrubbed (tracebacks end up in journalctl / Actions logs)."""
    import traceback
    print(redact(traceback.format_exc()), file=sys.stderr, end="")


def _redacting_excepthook(exc_type, exc, tb):
    import traceback
    print(redact("".join(traceback.format_exception(exc_type, exc, tb))), file=sys.stderr, end="")


sys.excepthook = _redacting_excepthook   # crashes nobody caught get scrubbed too


class Warnings:
    """Collects non-fatal problems; run_all sends them to Discord and the status page."""

    def __init__(self):
        self.items: list[dict] = []

    def add(self, source: str, message: str, key: str | None = None):
        message = redact(message)
        key = redact(key or f"{source}:{message}")
        self.items.append({"source": source, "message": message, "key": key})
        print(f"WARNING [{source}] {message}")


warnings = Warnings()


class Http:
    """requests wrapper with a minimum interval between calls and simple retry/backoff."""

    def __init__(self, user_agent: str, min_interval: float = 0.0, headers: dict | None = None):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, **(headers or {})})
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, params: dict | None = None, retries: int = 4, **kw) -> requests.Response:
        for attempt in range(retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params, timeout=30, **kw)
            except requests.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == retries - 1:
                    r.raise_for_status()
                time.sleep(int(r.headers.get("Retry-After", 2 ** attempt * 5)))
                continue
            return r
        raise RuntimeError("unreachable")
