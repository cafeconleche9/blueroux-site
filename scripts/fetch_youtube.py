"""Fetch every public upload on the channel into data/cache/youtube.json."""
from __future__ import annotations

import os

from common import Http, load_config, read_cache, warnings, write_cache

API = "https://www.googleapis.com/youtube/v3"


def run() -> dict:
    key = os.environ.get("YOUTUBE_API_KEY")
    cached = read_cache("youtube.json", {"videos": {}})
    if not key:
        warnings.add("youtube", "YOUTUBE_API_KEY not set; using cached data")
        return cached
    cfg = load_config()["youtube"]
    # Key goes in a header, never the URL: request errors quote the URL, which would leak the key.
    http = Http("BlueRouxArchive/0.1", headers={"X-Goog-Api-Key": key})

    ch = http.get(f"{API}/channels", {"part": "contentDetails", "forHandle": cfg["handle"]})
    ch.raise_for_status()
    items = ch.json().get("items") or []
    if not items:
        raise RuntimeError(f"YouTube channel @{cfg['handle']} not found")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = cached["videos"]
    seen_ids: set[str] = set()
    token = None
    new = 0
    while True:
        params = {"part": "snippet", "playlistId": uploads, "maxResults": 50}
        if token:
            params["pageToken"] = token
        r = http.get(f"{API}/playlistItems", params)
        r.raise_for_status()
        data = r.json()
        for it in data.get("items", []):
            sn = it["snippet"]
            vid = sn["resourceId"]["videoId"]
            seen_ids.add(vid)
            if sn["title"] in ("Private video", "Deleted video"):
                continue
            if vid not in videos:
                new += 1
            thumbs = sn.get("thumbnails", {})
            best = (thumbs.get("maxres") or thumbs.get("standard") or thumbs.get("high")
                    or thumbs.get("medium") or thumbs.get("default") or {})
            videos[vid] = {
                "id": vid,
                "title": sn["title"],
                "description": sn.get("description", ""),
                "published": sn.get("publishedAt", ""),
                "thumb": best.get("url", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
            }
        token = data.get("nextPageToken")
        if not token:
            break

    # drop videos that disappeared from the channel
    for gone in set(videos) - seen_ids:
        del videos[gone]
    out = {"videos": videos}
    write_cache("youtube.json", out)
    print(f"youtube: {len(videos)} videos ({new} new)")
    return out


if __name__ == "__main__":
    run()
