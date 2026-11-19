"""Fetch the public Discogs collection plus release/artist/label details.

run() fetches the collection and release details; fetch_profiles() (called after matching) fetches
artist/label profiles for the uploaded releases only.

Cache layout (data/cache/discogs.json):
  collection: {instance_id: {release_id, date_added, formats[], folder_id}}
  releases:   {release_id: {...full release fields we use...}}
  artists:    {artist_id: {name, profile}}
  labels:     {label_id: {name, profile}}
  search:     {video_id: {date, release_id|None, candidates[]}}   (see search_unmatched)
Releases/artists/labels are fetched once and cached; only new ones cost API calls.
Progress is saved periodically so an interrupted first run resumes.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

import describe
from common import Http, load_config, load_yaml, read_cache, valid_id, warnings, write_cache

API = "https://api.discogs.com"
SAVE_EVERY = 25


def _clean(text: str | None) -> str:
    # Discogs markup like [a=Name], [l=Label], [url=...]text[/url]
    if not text:
        return ""
    text = re.sub(r"\[url=[^\]]*\](.*?)\[/url\]", r"\1", text, flags=re.S)
    text = re.sub(r"\[[alrmb]=?([^\]]*)\]", r"\1", text)
    return text.strip()


def _make_http(cfg: dict) -> Http:
    token = os.environ.get("DISCOGS_TOKEN")
    headers = {"Authorization": f"Discogs token={token}"} if token else {}
    return Http(cfg["user_agent"], cfg["min_interval_seconds"] if token else 2.6, headers)


def _release_record(rid: str, d: dict) -> dict:
    """The fields we keep from a /releases/{id} response."""
    return {
        "id": rid,
        "title": d.get("title", ""),
        "year": d.get("year") or 0,
        "released": d.get("released", ""),
        "country": d.get("country", ""),
        "genres": d.get("genres", []),
        "styles": d.get("styles", []),
        # release-level formats: used when the release isn't in his collection
        "formats": [{"name": f.get("name", ""), "descriptions": f.get("descriptions", [])}
                    for f in d.get("formats", [])],
        "notes": _clean(d.get("notes")),
        "artists": [{"id": str(a["id"]), "name": re.sub(r"\s\(\d+\)$", "", a["name"])} for a in d.get("artists", [])],
        "labels": [{"id": str(l["id"]), "name": re.sub(r"\s\(\d+\)$", "", l["name"]), "catno": l.get("catno", "")}
                   for l in d.get("labels", [])],
        "videos": [m.group(1) for v in d.get("videos", [])
                   if (m := re.search(r"(?:v=|youtu\.be/)([\w-]{11})", v.get("uri", "")))],
        "cover": next((i["uri"] for i in d.get("images", []) if i.get("type") == "primary"),
                      (d.get("images") or [{}])[0].get("uri", "")),
        "thumb": d.get("thumb", ""),
        "uri": d.get("uri", f"https://www.discogs.com/release/{rid}"),
    }


def run() -> dict:
    cfg = load_config()["discogs"]
    cache = read_cache("discogs.json", {"collection": {}, "releases": {}, "artists": {}, "labels": {}})
    if cfg["username"] == "CHANGE_ME":
        warnings.add("discogs", "discogs.username not set in config.yaml; using cached data")
        return cache
    if not os.environ.get("DISCOGS_TOKEN"):
        warnings.add("discogs", "DISCOGS_TOKEN not set; unauthenticated (25 req/min) and no image URLs")
    http = _make_http(cfg)

    # --- collection (folder 0 = all) ---
    collection: dict[str, dict] = {}
    page = 1
    while True:
        r = http.get(f"{API}/users/{cfg['username']}/collection/folders/0/releases",
                     {"page": page, "per_page": 100, "sort": "added", "sort_order": "desc"})
        r.raise_for_status()
        data = r.json()
        for it in data["releases"]:
            bi = it["basic_information"]
            collection[str(it["instance_id"])] = {
                "release_id": str(it["id"]),
                "date_added": it.get("date_added", ""),
                "folder_id": it.get("folder_id"),
                "formats": bi.get("formats", []),
            }
        if page >= data["pagination"]["pages"]:
            break
        page += 1
    cache["collection"] = collection
    print(f"discogs: {len(collection)} collection items")

    try:
        # --- releases ---
        needed = {c["release_id"] for c in collection.values()}
        # plus releases named in overrides/matches.yaml, which may be outside his collection
        needed |= {str(r) for r in (load_yaml("overrides/matches.yaml") or {}).values() if valid_id(r)}
        todo = sorted(needed - set(cache["releases"]), key=int)
        done = 0
        for rid in todo:
            r = http.get(f"{API}/releases/{rid}")
            if r.status_code == 404:
                warnings.add("discogs", f"release {rid} not found (deleted/merged?)", key=f"discogs404:{rid}")
                cache["releases"][rid] = {"id": rid, "missing": True}
                continue
            r.raise_for_status()
            cache["releases"][rid] = _release_record(rid, r.json())
            done += 1
            if done % SAVE_EVERY == 0:
                write_cache("discogs.json", cache)
                print(f"discogs: fetched {done}/{len(todo)} releases")
    finally:
        # Always keep progress, even if a later step crashes (a first backfill takes hours).
        write_cache("discogs.json", cache)
    print(f"discogs: {len(todo)} new releases fetched")
    return cache


def fetch_profiles(cache: dict, release_ids: set[str]) -> dict:
    """Fetch artist/label profiles (used only for location suggestions) for the given releases.

    Called by run_all after matching, with just the releases that have a YouTube video: the site
    only shows those, so profiles for the rest of the collection would be wasted requests.
    """
    cfg = load_config()["discogs"]
    http = _make_http(cfg)
    done = 0
    try:
        for kind in ("artists", "labels"):
            ids = {x["id"] for rid in release_ids for x in cache["releases"].get(rid, {}).get(kind, [])
                   if valid_id(x["id"]) and x["id"] != "194"}  # 194 = "Various"
            todo = sorted(ids - set(cache[kind]), key=int)
            print(f"discogs: {len(todo)} {kind} profiles to fetch ({len(ids)} relevant)")
            for i in todo:
                r = http.get(f"{API}/{kind}/{i}")
                if r.status_code == 404:
                    cache[kind][i] = {"name": "", "profile": ""}
                    continue
                r.raise_for_status()
                d = r.json()
                cache[kind][i] = {"name": d.get("name", ""), "profile": _clean(d.get("profile"))}
                done += 1
                if done % SAVE_EVERY == 0:
                    write_cache("discogs.json", cache)
    finally:
        write_cache("discogs.json", cache)
    return cache


RESEARCH_DAYS = 30
SEARCH_CANDIDATES = 5


def search_unmatched(yt: dict, cache: dict, vids: list[str], budget: int = 300,
                     http: Http | None = None, today: date | None = None) -> dict:
    """Find Discogs pages for uploads that aren't in BlueRoux's collection.

    Searches Discogs by artist/title and accepts a result ONLY if that release's Discogs page
    already lists this YouTube video (proof, not a guess). Unverified results are kept as
    candidates for the review report. Results go in cache["search"][video_id]:
      {date, release_id (verified) | None, candidates: [{id, title, year, format}]}
    Unresolved videos are searched again after RESEARCH_DAYS, so later Discogs submissions
    get picked up. `budget` caps HTTP requests per run; videos it doesn't reach wait for the
    next run. Newest uploads go first.
    """
    today = today or date.today()
    if http is None:
        if not os.environ.get("DISCOGS_TOKEN"):
            warnings.add("discogs", "DISCOGS_TOKEN not set; skipping Discogs search for uploads outside the collection")
            return {"searched": 0, "verified": 0, "pending": len(vids)}
        http = _make_http(load_config()["discogs"])
    search = cache.setdefault("search", {})

    def due(vid: str) -> bool:
        s = search.get(vid)
        if not s:
            return True
        if s.get("release_id"):
            return False
        return date.fromisoformat(s["date"]) <= today - timedelta(days=RESEARCH_DAYS)

    todo = sorted((v for v in vids if v in yt["videos"] and due(v)),
                  key=lambda v: yt["videos"][v]["published"], reverse=True)
    used = searched = verified = 0

    def get(url, params=None):
        nonlocal used
        used += 1
        return http.get(url, params)

    try:
        for vid in todo:
            if used >= budget:
                break
            artist, title = describe.split_title(yt["videos"][vid]["title"])
            if artist != title:
                params = {"type": "release", "artist": artist, "release_title": title, "per_page": 10}
            else:  # self-titled or no "Artist - Title" separator
                params = {"type": "release", "q": title, "per_page": 10}
            r = get(f"{API}/database/search", params)
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results and artist != title:
                r = get(f"{API}/database/search", {"type": "release", "q": f"{artist} {title}", "per_page": 10})
                r.raise_for_status()
                results = r.json().get("results", [])

            found, complete = None, True
            for h in results[:SEARCH_CANDIDATES]:
                rid = str(h.get("id", ""))
                if not valid_id(rid):
                    continue
                if rid not in cache["releases"]:
                    if used >= budget:
                        complete = False  # ran out mid-check: don't record; retry next run
                        break
                    rr = get(f"{API}/releases/{rid}")
                    if rr.status_code == 404:
                        continue
                    rr.raise_for_status()
                    cache["releases"][rid] = _release_record(rid, rr.json())
                if vid in cache["releases"][rid].get("videos", []):
                    found = rid
                    break
            if not complete and not found:
                break
            searched += 1
            verified += bool(found)
            search[vid] = {
                "date": today.isoformat(),
                "release_id": found,
                "candidates": [] if found else [
                    {"id": str(h["id"]), "title": h.get("title", ""), "year": h.get("year", ""),
                     "format": ", ".join(h.get("format", [])[:3])}
                    for h in results[:SEARCH_CANDIDATES] if valid_id(h.get("id", ""))],
            }
            if searched % SAVE_EVERY == 0:
                write_cache("discogs.json", cache)
    finally:
        write_cache("discogs.json", cache)
    pending = sum(1 for v in vids if v in yt["videos"] and due(v))
    print(f"discogs search: {searched} searched, {verified} verified on Discogs, {pending} still waiting "
          f"({used} requests)")
    return {"searched": searched, "verified": verified, "pending": pending}


if __name__ == "__main__":
    run()
