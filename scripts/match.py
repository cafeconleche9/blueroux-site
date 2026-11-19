"""Link YouTube videos to Discogs releases.

Priority: overrides/matches.yaml  >  a collection release's videos contain the video id  >  fuzzy
title match within the collection  >  verified Discogs search result outside the collection
>  likely Discogs search result (artist and title agree; see likely_match).
Many videos may map to one release. Videos that can't be matched are returned with candidates.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz, process

import describe

LIKELY = 85   # name similarity (0-100) for a "likely" Discogs search match

_NOISE = re.compile(
    r"\(?\b(full album|full lp|full ep|lp|ep|album|remastered|\d{4}|hq|hd|\[.*?\])\b\)?", re.I)


def _norm(s: str) -> str:
    s = s.lower()
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[\W_]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _release_key(rel: dict) -> str:
    artists = " ".join(a["name"] for a in rel.get("artists", []))
    return _norm(f"{artists} {rel.get('title', '')}")


def run(youtube: dict, discogs: dict, overrides: dict, cfg: dict, searched: dict | None = None) -> dict:
    """`searched` = discogs cache["search"]: Discogs search results for videos outside the
    collection. A verified one (the release's page lists the video) matches as "discogs-search";
    unverified results are attached to the unmatched entry as `search_candidates`."""
    searched = searched or {}
    accept, review = cfg["fuzzy_threshold"], cfg["review_threshold"]
    in_collection = {c["release_id"] for c in discogs["collection"].values()}
    releases = {rid: r for rid, r in discogs["releases"].items()
                if rid in in_collection and not r.get("missing")}

    by_video_field: dict[str, str] = {}
    for rid, rel in releases.items():
        for v in rel.get("videos", []):
            by_video_field.setdefault(v, rid)

    keys = {rid: _release_key(r) for rid, r in releases.items()}
    key_items = list(keys.items())

    matched: dict[str, dict] = {}      # video_id -> {release_id, how, score}
    unmatched: list[dict] = []
    for vid, v in youtube["videos"].items():
        if vid in overrides:
            target = overrides[vid]
            if target is None:
                matched[vid] = {"release_id": None, "how": "override-none", "score": 100}
            else:
                matched[vid] = {"release_id": str(target), "how": "override", "score": 100}
            continue
        if vid in by_video_field:
            matched[vid] = {"release_id": by_video_field[vid], "how": "discogs-video", "score": 100}
            continue
        title = _norm(v["title"])
        cands = process.extract(title, {rid: k for rid, k in key_items}, scorer=fuzz.token_set_ratio, limit=3) \
            if key_items else []
        top = [{"release_id": rid, "score": round(score, 1), "label": _label(releases[rid])}
               for _k, score, rid in cands]
        s = searched.get(vid) or {}
        if top and top[0]["score"] >= accept and (len(top) < 2 or top[0]["score"] - top[1]["score"] >= 3):
            matched[vid] = {"release_id": top[0]["release_id"], "how": "fuzzy", "score": top[0]["score"]}
        elif s.get("release_id") and not discogs["releases"].get(s["release_id"], {}).get("missing"):
            matched[vid] = {"release_id": s["release_id"], "how": "discogs-search", "score": 100}
        elif (likely := likely_match(v, s.get("candidates", []), discogs["releases"])):
            matched[vid] = {"release_id": likely, "how": "discogs-likely", "score": 90}
        else:
            unmatched.append({"video": v, "candidates": [c for c in top if c["score"] >= review],
                              "search_candidates": s.get("candidates", []), "searched": s.get("date")})
    return {"matched": matched, "unmatched": unmatched}


def _plain(s: str) -> str:
    """Loose form for comparing names: no accents, case, punctuation, leading "The", "&" = "and"."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s\(\d+\)", "", s).replace("*", "").replace("&", " and ")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"^the\s+", "", re.sub(r"\s+", " ", s).strip())
    return s.replace(" ", "")


def _close(a: str, b: str, need: float = LIKELY) -> bool:
    return fuzz.ratio(_plain(a), _plain(b)) >= need


def likely_match(video: dict, candidates: list[dict], releases: dict) -> str | None:
    """Pick a Discogs search result that is very likely this upload, even though its page doesn't
    list the video. "Artist - Title" uploads: both artist and title must agree. Title-only uploads
    (common for demos: "Splash (Full Demo)") are riskier, since many bands share a name, so the
    release must also be self-titled and on the format he ripped from, with no year conflict."""
    artist, title = describe.split_title(video["title"])
    p = describe.parse(video.get("description", ""))
    has_artist = artist != title or " - " in video["title"]
    best = None
    for c in candidates:
        r = releases.get(str(c["id"]))
        if not r or r.get("missing"):
            continue
        r_artist = ", ".join(a["name"] for a in r.get("artists", []))
        # the search title ("Artist - Title") uses the name as printed on the release, which can
        # differ from the artist's main Discogs name ("The Cut 4th Family" vs "The Cutforth Family")
        printed = c.get("title", "").split(" - ", 1)[0]
        fmt = (r.get("formats") or [{}])[0].get("name", "")
        fmt_ok = bool(p["fmt"]) and fmt == p["fmt"]
        years = p["year"] and r.get("year")
        year_gap = abs(int(p["year"]) - int(r["year"])) if years else 0
        if has_artist:
            ok = ((_close(artist, r_artist) or _close(artist, printed)) and _close(title, r["title"])
                  and not (year_gap > 2 and not fmt_ok))
        else:
            ok = _close(title, r_artist, 90) and _close(title, r["title"], 90) and fmt_ok and year_gap <= 1
        if ok:
            rank = (fmt_ok, -year_gap)
            if best is None or rank > best[0]:
                best = (rank, str(c["id"]))
    return best[1] if best else None


def _label(rel: dict) -> str:
    return f"{', '.join(a['name'] for a in rel.get('artists', []))} – {rel.get('title', '')} ({rel.get('year') or '?'})"
