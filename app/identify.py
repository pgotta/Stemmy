"""
identify.py — figure out what a track is, then fetch time-synced lyrics.

- Song ID  : shazamio (reverse-engineered Shazam API). Optional/lazy import;
             enabled via get_lyrics.bat. Needs network.
- Lyrics   : LRCLIB (https://lrclib.net) — free, no API key, returns LRC-format
             synced lyrics. Plain urllib, no extra dependency.

Everything degrades gracefully: if Shazam isn't installed or can't match, the
UI falls back to letting the user type "Artist - Title" and we still fetch
lyrics from LRCLIB.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request


def shazam_available() -> bool:
    try:
        import shazamio  # noqa: F401
        return True
    except Exception:
        return False


def identify_song(path: str) -> dict | None:
    """Recognise a track from an audio file via Shazam. Returns
    {title, artist, album} or None. Requires shazamio + network."""
    try:
        import asyncio
        from shazamio import Shazam
    except Exception:
        return None

    async def _run():
        return await Shazam().recognize(path)

    try:
        out = asyncio.run(_run())
    except Exception:
        return None
    track = (out or {}).get("track") or {}
    if not track:
        return None
    album = None
    for sec in (track.get("sections") or []):
        for md in (sec.get("metadata") or []):
            if (md.get("title") or "").lower() == "album":
                album = md.get("text")
    images = track.get("images") or {}
    image = images.get("coverarthq") or images.get("coverart") or images.get("background")
    return {"title": track.get("title"),
            "artist": track.get("subtitle"),
            "album": album,
            "image": image}


def parse_lrc(text: str) -> list[list]:
    """Parse LRC ('[mm:ss.xx] words') into [[seconds, text], ...] sorted by time."""
    out = []
    if not text:
        return out
    tag = re.compile(r"\[(\d+):(\d+)(?:\.(\d+))?\]")
    for line in text.splitlines():
        stamps = list(tag.finditer(line))
        if not stamps:
            continue
        words = line[stamps[-1].end():].strip()
        for m in stamps:
            mn, se, fr = m.group(1), m.group(2), m.group(3) or "0"
            t = int(mn) * 60 + int(se) + float("0." + fr)
            out.append([round(t, 2), words])
    out.sort(key=lambda x: x[0])
    return out


def _lrclib_get(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Stemmy (https://github.com/pgotta)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_lyrics(title: str, artist: str, album: str | None = None,
                 duration: int | None = None) -> dict | None:
    """Fetch lyrics from LRCLIB. Prefers a signature match (with duration),
    falls back to search. Returns {synced, plain, trackName, artistName} or None."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return None
    base = "https://lrclib.net/api"

    rec = None
    if duration:
        q = {"track_name": title, "artist_name": artist,
             "album_name": album or title, "duration": int(duration)}
        try:
            rec = _lrclib_get(base + "/get?" + urllib.parse.urlencode(q))
        except Exception:
            rec = None
    if not rec:  # fall back to search, pick the best synced hit
        q = {"track_name": title}
        if artist:
            q["artist_name"] = artist
        try:
            results = _lrclib_get(base + "/search?" + urllib.parse.urlencode(q))
        except Exception:
            results = None
        if isinstance(results, list) and results:
            rec = next((r for r in results if r.get("syncedLyrics")), results[0])

    if not rec:
        return None
    synced = parse_lrc(rec.get("syncedLyrics") or "")
    plain = rec.get("plainLyrics") or ""
    if not synced and not plain:
        return None
    return {"synced": synced, "plain": plain,
            "trackName": rec.get("trackName") or title,
            "artistName": rec.get("artistName") or artist}
