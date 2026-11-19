"""Suggest US-state locations from free text. Suggestions never set the displayed location.

Rules (see plan): full state names with word boundaries; two-letter codes only in
"City, ST" / "City ST 12345" form; ambiguous names ("Washington", "Georgia", "Indiana",
"Virginia", "Jersey"...) get lower confidence; credits like "Pressed at"/"Manufactured by"
lines are ignored.
"""
from __future__ import annotations

import re

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "Washington, D.C.",
}
NAME_TO_CODE = {v: k for k, v in STATES.items() if k != "DC"}
AMBIGUOUS = {"Washington", "Georgia", "Indiana", "Virginia", "Maine", "Mississippi", "Nevada", "Montana"}

_NAME_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(n) for n in NAME_TO_CODE), key=len, reverse=True)) + r")\b")
_CODE_RE = re.compile(r"\b[A-Z][a-zA-Z.]+(?: [A-Z][a-zA-Z.]+)*,? (" + "|".join(k for k in STATES if k != "DC") + r")\b(?=[\s,.;:)\]]|$)")
_IGNORE_LINE = re.compile(r"\b(pressed|pressing|manufactured|printed|mastered|lacquer|distributed|copyright|©|℗|made in)\b", re.I)
_PHRASE_AMBIG = re.compile(r"\b(?:George|Booker T\.?|Denzel|Kerry|Dinah|Grover|Mount)\s+Washington\b|\bGeorgia (?:Satellites|Brown|Gibbs)\b", re.I)


def _snippet(text: str, start: int, end: int, width: int = 60) -> str:
    s = max(0, start - width)
    e = min(len(text), end + width)
    return ("…" if s else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def suggest(sources: dict[str, str]) -> list[dict]:
    """sources: {label: text}. Returns [{state, name, confidence, hits:[{source, snippet}]}], best first."""
    found: dict[str, dict] = {}

    def add(code: str, source: str, snippet: str, conf: str):
        d = found.setdefault(code, {"state": code, "name": STATES[code], "confidence": conf, "hits": []})
        if conf == "high":
            d["confidence"] = "high"
        d["hits"].append({"source": source, "snippet": snippet})

    for label, text in sources.items():
        if not text:
            continue
        clean = "\n".join(ln for ln in text.splitlines() if not _IGNORE_LINE.search(ln))
        for m in _NAME_RE.finditer(clean):
            name = m.group(1)
            ambiguous = name in AMBIGUOUS
            if name == "Washington" and _PHRASE_AMBIG.search(clean[max(0, m.start() - 20): m.end() + 5]):
                continue
            # "Washington, D.C." is not the state
            if name == "Washington" and re.match(r",?\s*D\.?C\b", clean[m.end():m.end() + 6]):
                continue
            # directional words: "west Virginia"-style false positives are fine to keep as low confidence
            add(NAME_TO_CODE[name], label, _snippet(clean, m.start(), m.end()), "low" if ambiguous else "high")
        for m in _CODE_RE.finditer(clean):
            add(m.group(1), label, _snippet(clean, m.start(), m.end()), "high")

    order = {"high": 0, "low": 1}
    return sorted(found.values(), key=lambda d: (order[d["confidence"]], -len(d["hits"])))
