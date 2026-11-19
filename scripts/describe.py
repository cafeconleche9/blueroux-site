"""Parse BlueRoux's YouTube description formula:

    "<Genre> from <City, State> (<year>). Ripped from <format>."

e.g. "Indie rock from Boise, Idaho (1999). Ripped from CD."
     "Heavy metal/hard rock EP likely from San Marcos, Texas (1997). Ripped directly from CD."

Measured on the real channel: ~90% of videos follow it, and its state agrees with the
Discogs artist bio 214/226 times (the misses were bios of a different, same-named artist).
"""
from __future__ import annotations

import re

import locate

NA = "N/A (No Discogs Page)"

_LINE = re.compile(
    r"^(?P<genre>[^\n]{2,80}?)\s+(?P<hedge>(?:likely|probably|possibly|maybe)\s+)?from\s+"
    r"(?P<place>[^\n(]{2,60}?)\s*(?:\((?P<year>[^)\n]{1,20})\)|,\s*(?P<year2>date unknown|\d{4}s?))?\s*\.",
    re.I)
_DOUBT = re.compile(r"\?|\b(?:i assume|assumed?|presumably|probably|possibly|maybe|likely|i think|i believe|unsure|not sure)\b", re.I)
_RIP = re.compile(r"ripped\s+(?:directly\s+)?from\s+(?:an?\s+|the\s+)?(?P<fmt>[\w\" -]{2,20}?)\s*(?:[\.\n,!]|$)", re.I)
_FMT = {"vinyl": "Vinyl", "cassette": "Cassette", "cassette tape": "Cassette", "cd": "CD",
        "cdr": "CDr", "cd-r": "CDr", "hand-labeled cdr": "CDr", "acetate": "Acetate",
        "acetate record": "Acetate", "flexi-disc": "Flexi-disc", "dvdr": "DVDr"}


def parse(description: str) -> dict:
    """Returns {place, hedged, year, fmt, genre_text}; missing parts are None/""."""
    out = {"place": "", "hedged": False, "year": None, "fmt": None, "genre_text": ""}
    first = (description or "").strip().split("\n", 1)[0]
    m = _LINE.match(first)
    if m:
        out["place"] = m["place"].strip()
        # hedged: "likely from X", or doubt inside the place itself ("Washington state, I assume", "Boise?")
        out["hedged"] = bool(m["hedge"]) or bool(_DOUBT.search(out["place"]))
        out["genre_text"] = m["genre"].strip()
        y = (m["year"] or m["year2"] or "").strip()
        if re.fullmatch(r"(19|20)\d\d", y):
            out["year"] = int(y)
    r = _RIP.search(description or "")
    if r:
        f = r["fmt"].strip().lower()
        out["fmt"] = _FMT.get(f)  # unknown phrases ("my copy") -> None rather than a junk facet value
    return out


def state_from(parsed: dict) -> str | None:
    """Two-letter state, only when the line names exactly one US state and isn't hedged."""
    if not parsed["place"] or parsed["hedged"]:
        return None
    states = {s["state"] for s in locate.suggest({"d": parsed["place"]})}
    return states.pop() if len(states) == 1 else None


_MARKER = re.compile(r"\s*[\(\[](?:full|complete)\s+(?:album|ep|lp|demo|tape|cassette|single|record)[^\)\]]*[\)\]]\s*$", re.I)
_SEP = re.compile(r"\s+[-–—]\s+")


def split_title(title: str) -> tuple[str, str]:
    """'Artist - Album (Full Album)' -> ('Artist', 'Album'); no separator -> (t, t)."""
    t = _MARKER.sub("", title).strip()
    parts = _SEP.split(t, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0].strip(), parts[1].strip()
    return t, t
