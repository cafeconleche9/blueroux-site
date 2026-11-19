"""Radio shows: Mixcloud (episode list + embed key) and Spinitron (playlist scrape).

Cache (data/cache/radio.json): {shows: {"YYYY-MM-DD": {date, mixcloud: {...}|None, spinitron: {url, spins[]}|None}}}
A show's Spinitron tracklist is stored once scraped; later scrape failures never erase it.
Failure of either source is a warning, not an error: the show page falls back to links.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import Http, load_config, read_cache, warnings, write_cache

MIXCLOUD_API = "https://api.mixcloud.com"
SPIN_BASE = "https://spinitron.com"
UA = "Mozilla/5.0 (compatible; BlueRouxArchive/0.1)"


def _title_date(title: str, rx: re.Pattern) -> date | None:
    m = rx.match(title.strip())
    if not m:
        return None
    mo, d, y = (int(x) for x in m.groups())
    y += 2000 if y < 100 else 0
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def fetch_mixcloud(cfg: dict, http: Http) -> dict[str, dict]:
    rx = re.compile(cfg["mixcloud"]["show_title_regex"], re.I)
    first = date.fromisoformat(cfg["mixcloud"]["first_show"])
    out: dict[str, dict] = {}
    url = f"{MIXCLOUD_API}/{cfg['mixcloud']['user']}/cloudcasts/?limit=100"
    while url:
        r = http.get(url)
        r.raise_for_status()
        data = r.json()
        for cc in data.get("data", []):
            d = _title_date(cc["name"], rx)
            if d and d >= first:
                out[d.isoformat()] = {
                    "name": cc["name"],
                    "url": cc["url"],
                    "key": cc["key"],  # used by the embed widget: /widget/iframe/?feed=<key>
                    "picture": cc.get("pictures", {}).get("large", ""),
                    "created": cc.get("created_time", ""),
                    "tags": [t["name"] for t in cc.get("tags", [])],
                }
        url = data.get("paging", {}).get("next")
    return out


def _parse_playlist(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    head = soup.select_one(".head.playlist")
    when = None
    if head:
        m = re.search(r"([A-Z][a-z]{2,8}) (\d{1,2}), (\d{4})", head.get_text(" ", strip=True))
        if m:
            try:
                when = datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
            except ValueError:
                pass
    spins = []
    for row in soup.select("tr.spin-item"):
        meta: dict = {}
        try:
            meta = json.loads(row.get("data-spin", "{}"))
        except json.JSONDecodeError:
            pass

        def txt(sel: str) -> str:
            el = row.select_one(sel)
            return el.get_text(" ", strip=True) if el else ""

        spins.append({
            "time": txt(".spin-time"),
            "artist": txt(".spin .artist") or meta.get("a", ""),
            "song": txt(".spin .song") or meta.get("s", ""),
            "release": txt(".info .release") or meta.get("r", ""),
            "label": txt(".info .label"),
            "year": txt(".info .released"),
        })
    return {"date": when.isoformat() if when else None, "spins": spins}


def fetch_spinitron(cfg: dict, http: Http, cached_shows: dict) -> dict[str, dict]:
    r = http.get(cfg["spinitron"]["dj_url"])
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=re.compile(r"/pl/\d+/")):
        href = urljoin(SPIN_BASE, a["href"].split("?")[0])
        if href not in links:
            links.append(href)
    known = {u: d for d, s in cached_shows.items() if s.get("spinitron")
             for u in [s["spinitron"]["url"], *s["spinitron"].get("other_urls", [])]}
    out: dict[str, dict] = {}
    for href in links:
        # Re-scrape only playlists we don't have, plus the most recent show (still being edited).
        if href in known and known[href] != max(known.values()):
            continue
        try:
            pr = http.get(href)
            pr.raise_for_status()
            parsed = _parse_playlist(pr.text)
        except Exception as e:  # one bad playlist must not stop the rest
            warnings.add("spinitron", f"could not read {href}: {e}", key=f"spin:{href}")
            continue
        if not parsed["date"]:
            warnings.add("spinitron", f"no date found on {href} (page layout changed?)", key=f"spindate:{href}")
            continue
        if not parsed["spins"]:
            warnings.add("spinitron", f"0 tracks parsed from {href}", key=f"spin0:{href}")
        # Several playlists can share a date (e.g. the messy first show). Keep the fullest one
        # as the main tracklist and remember the others as extra links.
        cur = out.get(parsed["date"])
        new = {"url": href, "spins": parsed["spins"], "other_urls": []}
        if cur is None:
            out[parsed["date"]] = new
        elif len(new["spins"]) > len(cur["spins"]):
            new["other_urls"] = [cur["url"], *cur["other_urls"]]
            out[parsed["date"]] = new
        else:
            cur["other_urls"].append(href)
    return out


def run() -> dict:
    cfg = load_config()
    cache = read_cache("radio.json", {"shows": {}})
    shows = cache["shows"]
    http = Http(UA, 0.5)

    try:
        for d, mc in fetch_mixcloud(cfg, http).items():
            shows.setdefault(d, {"date": d, "mixcloud": None, "spinitron": None})["mixcloud"] = mc
    except Exception as e:
        warnings.add("mixcloud", f"fetch failed, using cached shows: {e}")

    try:
        first = cfg["mixcloud"]["first_show"]
        for d, sp in fetch_spinitron(cfg, http, shows).items():
            if d < first:
                continue
            show = shows.setdefault(d, {"date": d, "mixcloud": None, "spinitron": None})
            # never replace a good tracklist with a smaller/empty one (e.g. a stub playlist)
            old = show.get("spinitron")
            if not old or len(sp["spins"]) >= len(old["spins"]):
                show["spinitron"] = sp
            elif sp["url"] not in [old["url"], *old.get("other_urls", [])]:
                old.setdefault("other_urls", []).append(sp["url"])
    except Exception as e:
        warnings.add("spinitron", f"fetch failed, using cached playlists: {e}")

    cache["shows"] = dict(sorted(shows.items()))
    write_cache("radio.json", cache)
    print(f"radio: {len(shows)} shows")
    return cache


if __name__ == "__main__":
    run()
