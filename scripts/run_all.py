"""Orchestrate fetch → build. Each source is isolated: a failure falls back to cached data
and becomes a warning. Hard failures (nothing to build from, build crash) exit non-zero so the
workflow fails (GitHub emails; the workflow's failure step also pings Discord)."""
from __future__ import annotations

import sys
import traceback

import build
import fetch_discogs
import fetch_radio
import fetch_youtube
import match
import notify
from common import load_config, load_yaml, read_cache, warnings


def safe(name, fn, fallback_cache):
    try:
        return fn()
    except Exception as e:
        traceback.print_exc()
        warnings.add(name, f"fetch failed, using cached data: {type(e).__name__}: {e}")
        return read_cache(fallback_cache)


def search_outside_collection(yt: dict, dc: dict) -> None:
    """Uploads not matched within his collection: look for them on Discogs (verified by the
    release page listing the video). Optional: failure is a warning."""
    if load_config()["discogs"]["username"] == "CHANGE_ME":
        return
    try:
        cfg = load_config()
        m = match.run(yt, dc, load_yaml("overrides/matches.yaml"), cfg["matching"], dc.get("search"))
        fetch_discogs.search_unmatched(yt, dc, [u["video"]["id"] for u in m["unmatched"]],
                                       budget=int(cfg["discogs"].get("search_budget", 2000)))
    except Exception as e:
        traceback.print_exc()
        warnings.add("discogs", f"Discogs search for uploads outside the collection failed: {type(e).__name__}: {e}")


def fetch_profiles_for_uploaded(yt: dict, dc: dict) -> None:
    """Artist/label profiles only feed location suggestions, and the site only shows releases that
    have a YouTube video, so fetch them for just those. Optional: failure is a warning."""
    if load_config()["discogs"]["username"] == "CHANGE_ME":
        return
    try:
        cfg = load_config()
        m = match.run(yt, dc, load_yaml("overrides/matches.yaml"), cfg["matching"], dc.get("search"))
        uploaded = {v["release_id"] for v in m["matched"].values() if v["release_id"]}
        print(f"profiles: {len(uploaded)} uploaded releases")
        fetch_discogs.fetch_profiles(dc, uploaded)   # updates dc in place
    except Exception as e:
        traceback.print_exc()
        warnings.add("discogs", f"artist/label profiles fetch failed (location suggestions may be thin): {type(e).__name__}: {e}")


def main() -> int:
    yt = safe("youtube", fetch_youtube.run, "youtube.json")
    dc = safe("discogs", fetch_discogs.run, "discogs.json")
    radio = safe("radio", fetch_radio.run, "radio.json") or {"shows": {}}
    if not yt or not dc:
        notify.send_failure("No YouTube or Discogs data available (no fresh fetch and no cache). Check API secrets.")
        return 1
    search_outside_collection(yt, dc)
    fetch_profiles_for_uploaded(yt, dc)
    try:
        build.run(yt, dc, radio, warnings.items)
    except Exception as e:
        traceback.print_exc()
        notify.send_failure(f"Build crashed: {type(e).__name__}: {e}")
        return 1
    notify.send_warnings(warnings.items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
