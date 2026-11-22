"""Join cached data into albums.json and render the static site into dist/."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone

import frontmatter
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

import describe
import locate
import match
from common import DIST, ROOT, load_config, load_yaml, read_cache, valid_id

SIZE_TAGS = ['7"', '10"', '12"', "LP"]


def normalize_formats(fmts: list[dict]) -> list[str]:
    out: list[str] = []
    for f in fmts:
        name, desc = f.get("name", ""), f.get("descriptions", []) or []
        if name == "Vinyl":
            size = next((s for s in SIZE_TAGS if s in desc), None)
            out.append(size or "Vinyl")
            if "45 RPM" in desc:
                out.append("45")
        elif name in ("Cassette", "CD"):
            out.append(name)
        elif name == "File":
            out.append("Digital")
        else:
            out.append(name or "Other")
    return out


def _ov_lookup(ov: dict, key) -> dict | None:
    """Override keys may be YAML ints (Discogs ids) or strings (YouTube ids, quoted ids)."""
    key = str(key)
    if key in ov:
        return ov[key] or {}
    if key.isdigit() and int(key) in ov:
        return ov[int(key)] or {}
    return None


def resolve_location(ov: dict, keys: list, descriptions: list[str]) -> dict:
    """Precedence: override (first matching key) > BlueRoux's description line > none.

    Returns {state (2-letter or ""), country (override or None), source, checked}.
    `checked` is True when an override explicitly blanked the state (state: none) — the
    album then stays off the needs-location report.
    """
    for k in keys:
        o = _ov_lookup(ov, k)
        if o is None:
            continue
        if "state" in o:
            s = o["state"]
            blank = s is None or str(s).strip().lower() in ("", "none", "null")
            return {"state": "" if blank else str(s).upper(), "country": o.get("country"),
                    "source": "override", "checked": True}
        if "country" in o:  # country-only override: still try the description for a state
            d = _desc_state(descriptions)
            return {"state": d or "", "country": o["country"], "source": "description" if d else "override",
                    "checked": True}
    d = _desc_state(descriptions)
    return {"state": d or "", "country": None, "source": "description" if d else "", "checked": False}


def _desc_state(descriptions: list[str]) -> str | None:
    found = {s for s in (describe.state_from(describe.parse(t)) for t in descriptions) if s}
    return found.pop() if len(found) == 1 else None  # several videos disagreeing -> no auto state


def _merge_formats(fmt_lists) -> list[str]:
    out: list[str] = []
    for fl in fmt_lists:
        for f in normalize_formats(fl):
            if f not in out:
                out.append(f)
    return out


def build_albums(yt: dict, dc: dict, matches: dict, overrides_loc: dict) -> tuple[list[dict], dict]:
    by_release: dict[str, list[dict]] = {}
    for inst in dc["collection"].values():
        by_release.setdefault(inst["release_id"], []).append(inst)

    videos_for: dict[str, list[str]] = {}
    for vid, m in matches["matched"].items():
        if m["release_id"]:
            videos_for.setdefault(m["release_id"], []).append(vid)

    albums, needs_location = [], []
    no_discogs_vids = [u["video"]["id"] for u in matches["unmatched"]]

    for rid, vids in videos_for.items():
        rel = dc["releases"].get(rid)
        if not rel or rel.get("missing"):
            # e.g. a matches.yaml target that hasn't been fetched yet: don't let the video vanish
            no_discogs_vids.extend(vids)
            continue
        insts = by_release.get(rid, [])   # empty = outside his collection (Discogs search or matches.yaml)
        vids.sort(key=lambda v: yt["videos"][v]["published"])
        artist_ids = [a["id"] for a in rel["artists"] if valid_id(a["id"])]
        descs = [yt["videos"][v]["description"] for v in vids]
        if insts:
            fmts = _merge_formats(i["formats"] for i in insts)
        else:
            # Not his collection copy: prefer what he says he ripped from (the Discogs page may be
            # another version, e.g. an 8-track entry for a vinyl rip), else the release's formats.
            ripped = next((f for f in (describe.parse(t)["fmt"] for t in descs) if f), None)
            fmts = [ripped] if ripped else _merge_formats([rel.get("formats", [])])
        loc = resolve_location(overrides_loc, [rid, *vids, *artist_ids], descs)
        first_vid = yt["videos"][vids[0]]
        album = {
            "id": rid,
            "title": rel["title"],
            "artists": [a["name"] for a in rel["artists"]],
            "labels": sorted({l["name"] for l in rel["labels"]}),
            "genres": rel["genres"],
            "styles": rel["styles"],
            "formats": fmts,
            "year": rel["year"] or None,
            "added": min(i["date_added"] for i in insts)[:10] if insts else "",
            "country": loc["country"] or rel["country"],
            "state": locate.STATES.get(loc["state"], loc["state"]),
            "ls": loc["source"],
            "cover": rel["cover"] or rel["thumb"] or first_vid["thumb"],
            "videos": vids,
            "uploaded": first_vid["published"][:10],
            "discogs": rel["uri"],
            "src": "collection" if insts else "discogs",
            "match": matches["matched"][vids[0]]["how"],
        }
        albums.append(album)
        if not loc["state"] and not loc["checked"]:
            sources = {"YouTube description": "\n".join(descs), "Release notes": rel["notes"]}
            for a in rel["artists"]:
                sources[f"Artist bio: {a['name']}"] = dc["artists"].get(a["id"], {}).get("profile", "")
            for l in rel["labels"]:
                sources[f"Label profile: {l['name']}"] = dc["labels"].get(l["id"], {}).get("profile", "")
            needs_location.append({"album": album, "key": rid, "artist_ids": artist_ids,
                                   "suggestions": locate.suggest(sources),
                                   "sources": {k: v for k, v in sources.items() if v}})

    # Videos with no Discogs release: shown with what BlueRoux's title/description give us.
    for vid in no_discogs_vids:
        v = yt["videos"][vid]
        p = describe.parse(v["description"])
        artist, title = describe.split_title(v["title"])
        loc = resolve_location(overrides_loc, [vid], [v["description"]])
        album = {
            "id": f"yt:{vid}",
            "title": title,
            "artists": [artist],
            "labels": [describe.NA],
            "genres": [describe.NA],
            "styles": [describe.NA],
            "formats": [p["fmt"]] if p["fmt"] else [describe.NA],
            "year": p["year"],
            "added": "",
            "country": loc["country"] or ("US" if loc["state"] else describe.NA),
            "state": locate.STATES.get(loc["state"], loc["state"]),
            "ls": loc["source"],
            "cover": v["thumb"],
            "videos": [vid],
            "uploaded": v["published"][:10],
            "discogs": None,
            "src": "none",
            "nd": True,
            "gt": p["genre_text"],
            "match": "none",
        }
        albums.append(album)
        if not loc["state"] and not loc["checked"]:
            needs_location.append({"album": album, "key": vid, "artist_ids": [],
                                   "suggestions": locate.suggest({"YouTube description": v["description"]}),
                                   "sources": {"YouTube description": v["description"]} if v["description"] else {}})
    albums.sort(key=lambda a: a["uploaded"], reverse=True)
    # surface Idaho/Utah/Oregon first in the review report
    pri = {"ID": 0, "UT": 1, "OR": 2}
    needs_location.sort(key=lambda n: (min([pri.get(s["state"], 9) for s in n["suggestions"]] or [10]),
                                       n["album"]["title"]))
    return albums, {"needs_location": needs_location}


def render_md(text: str, base: str) -> str:
    """Markdown → HTML. Links and images written from the site root ("/images/x.jpg", "/about/")
    get the site's base path added, so they work both locally and on GitHub Pages."""
    html = markdown.markdown(text, extensions=["extra", "sane_lists", "toc"])
    return re.sub(r'(src|href)="/(?!/)', lambda m: f'{m.group(1)}="{base}/', html)


def load_pages(base: str) -> list[dict]:
    pages = []
    d = ROOT / "pages"
    for p in sorted(d.glob("*.md")):
        post = frontmatter.load(p)
        pages.append({
            "slug": p.stem,
            "title": post.get("title", p.stem.replace("-", " ").title()),
            "order": post.get("nav_order", 100),
            "nav": post.get("nav", True),
            "html": render_md(post.content, base),
        })
    pages.sort(key=lambda p: (p["order"], p["title"]))
    return pages


def load_radio_notes(base: str) -> dict:
    """radio-notes/intro.md → top of the radio page; radio-notes/YYYY-MM-DD.md → that show's page."""
    notes = {}
    d = ROOT / "radio-notes"
    for p in sorted(d.glob("*.md")) if d.exists() else []:
        if p.stem == "intro" or re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem):
            notes[p.stem] = render_md(frontmatter.load(p).content, base)
    return notes


def run(yt: dict, dc: dict, radio: dict, warn_items: list[dict]) -> None:
    cfg = load_config()
    # SITE_BASE_URL (set by the GitHub workflow to "/<repo-name>") wins over config.yaml, so the
    # same config builds both the local site (served at "/") and the GitHub Pages one.
    base = os.environ.get("SITE_BASE_URL", cfg["site"]["base_url"]).rstrip("/")
    ov_matches = load_yaml("overrides/matches.yaml")
    ov_loc = load_yaml("overrides/locations.yaml")

    matches = match.run(yt, dc, ov_matches, cfg["matching"], dc.get("search"))
    albums, reports = build_albums(yt, dc, matches, ov_loc)
    pages = load_pages(base)
    notes = load_radio_notes(base)
    shows = sorted(radio["shows"].values(), key=lambda s: s["date"], reverse=True)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copytree(ROOT / "static", DIST / "static")
    if (ROOT / "images").exists():            # pictures for pages and radio notes
        shutil.copytree(ROOT / "images", DIST / "images")

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["ytlink"] = lambda v: f"https://www.youtube.com/watch?v={v}"
    # YAML key for overrides: Discogs ids bare; YouTube ids always quoted (an id starting
    # with "-" would otherwise be read as a list item and break the file)
    env.filters["yamlkey"] = lambda k: str(k) if str(k).isdigit() else f'"{k}"'

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Cache-busting: static files are cached by browsers for a day, so link them with a hash of
    # their contents (?v=…). A changed script/stylesheet then gets a new URL and loads at once.
    h = hashlib.sha1()
    for f in sorted((ROOT / "static").rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    ctx = {"site": cfg["site"], "base": base, "nav_pages": [p for p in pages if p["nav"]], "updated": updated,
           "v": h.hexdigest()[:10]}

    def write(rel: str, template: str, **kw):
        out = DIST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(env.get_template(template).render(**ctx, **kw))

    # albums.json: compact; the front end does all filtering
    (DIST / "albums.json").write_text(json.dumps(
        {"albums": albums, "videos": {v: {"t": yt["videos"][v]["title"]} for a in albums for v in a["videos"]},
         "updated": updated}, ensure_ascii=False, separators=(",", ":")))

    write("index.html", "index.html", count=len(albums))
    write("radio/index.html", "radio_index.html", shows=shows, intro=notes.get("intro"))
    for s in shows:
        write(f"radio/{s['date']}/index.html", "show.html", show=s, note=notes.get(s["date"]),
              nice_date=datetime.fromisoformat(s["date"]).strftime("%A, %B %-d, %Y"))
    for p in pages:
        write(f"{p['slug']}/index.html", "page.html", page=p)

    # status pages (unlinked, noindex)
    n_nd = sum(1 for a in albums if a.get("nd"))
    src_counts = {s: sum(1 for a in albums if a["src"] == s) for s in ("collection", "discogs", "none")}
    srch = dc.get("search", {})
    unm_ids = {u["video"]["id"] for u in matches["unmatched"]}
    search_info = {"searched": sum(1 for v in unm_ids if v in srch),
                   "not_yet": sum(1 for v in unm_ids if v not in srch),
                   "verified": sum(1 for m in matches["matched"].values() if m["how"] == "discogs-search"),
                   "likely": sum(1 for m in matches["matched"].values() if m["how"] == "discogs-likely")}
    loc_counts = {"description": 0, "override": 0, "none": 0}
    for a in albums:
        loc_counts["none" if not a["state"] else a["ls"] or "override"] += 1
    write("status/index.html", "status.html", warnings=warn_items, n_albums=len(albums), n_nd=n_nd,
          n_videos=len(yt["videos"]), n_unmatched=len(matches["unmatched"]), loc_counts=loc_counts,
          src_counts=src_counts, search_info=search_info,
          n_needs_loc=len(reports["needs_location"]), n_collection=len(dc["collection"]))
    write("status/unmatched.html", "report_unmatched.html", rows=matches["unmatched"])
    write("status/needs-location.html", "report_location.html", rows=reports["needs_location"])
    (DIST / ".nojekyll").write_text("")
    print(f"build: {len(albums)} albums ({src_counts['collection']} in collection, {src_counts['discogs']} on Discogs "
          f"outside it, {n_nd} without a Discogs page), {len(shows)} shows, {len(pages)} pages; "
          f"locations: {loc_counts['description']} from descriptions, {loc_counts['override']} from overrides, "
          f"{loc_counts['none']} none; {len(reports['needs_location'])} on the needs-location report")

