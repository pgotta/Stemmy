"""Compatibility layer for resilient LRCLIB lyric lookup.

Stemmy still identifies each track with Shazam first. This layer only broadens
the lyric lookup when the exact LRCLIB signature/search misses because Shazam,
YouTube, and LRCLIB use slightly different title/artist metadata.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Any


_INSTALLED = False
_ORIGINAL = None
_CLIENT = "Stemmy/1.5 (https://github.com/pgotta/Stemmy)"


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"\b(feat(?:uring)?|ft)\.?\s+.+$", "", text, flags=re.I)
    text = re.sub(r"[\[\(](official|music video|video|visuali[sz]er|audio|lyrics?|"
                  r"remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|album version|"
                  r"single version|explicit|clean)[^\]\)]*[\]\)]", " ", text, flags=re.I)
    text = re.sub(r"\s*[-–—]\s*(official|remaster(?:ed)?(?:\s+\d{4})?|live|"
                  r"radio edit|album version|single version|audio|video|lyrics?).*$",
                  " ", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _variants(title: str, artist: str) -> list[tuple[str, str]]:
    raw_title = (title or "").strip()
    raw_artist = (artist or "").strip()
    candidates: list[tuple[str, str]] = [(raw_title, raw_artist)]

    cleaned_title = re.sub(
        r"[\[\(](official|music video|video|visuali[sz]er|audio|lyrics?|"
        r"remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|album version|"
        r"single version|explicit|clean)[^\]\)]*[\]\)]",
        "",
        raw_title,
        flags=re.I,
    ).strip(" -–—")
    cleaned_title = re.sub(
        r"\s*[-–—]\s*(official|remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|"
        r"album version|single version|audio|video|lyrics?).*$",
        "",
        cleaned_title,
        flags=re.I,
    ).strip(" -–—")
    no_feat_title = re.sub(r"\s*[\(\[]?\s*(feat(?:uring)?|ft)\.?\s+.+$", "",
                           cleaned_title, flags=re.I).strip(" -–—")
    primary_artist = re.split(r"\s*(?:,|;|&|\band\b|\bfeat(?:uring)?\.?|\bft\.?)\s*",
                              raw_artist, maxsplit=1, flags=re.I)[0].strip()

    for pair in (
        (cleaned_title, raw_artist),
        (no_feat_title, raw_artist),
        (cleaned_title, primary_artist),
        (no_feat_title, primary_artist),
        (raw_title, primary_artist),
    ):
        if pair[0] and pair not in candidates:
            candidates.append(pair)
    return candidates


def _get_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _CLIENT,
            "Lrclib-Client": _CLIENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=18) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _score(record: dict[str, Any], title: str, artist: str,
           duration: int | None) -> float:
    wanted_title = _norm(title)
    wanted_artist = _norm(artist)
    got_title = _norm(record.get("trackName"))
    got_artist = _norm(record.get("artistName"))

    title_score = difflib.SequenceMatcher(None, wanted_title, got_title).ratio()
    artist_score = (
        difflib.SequenceMatcher(None, wanted_artist, got_artist).ratio()
        if wanted_artist and got_artist else 0.55
    )
    score = title_score * 70 + artist_score * 24

    if duration:
        try:
            delta = abs(float(record.get("duration") or 0) - float(duration))
            score += max(0.0, 10.0 - min(delta, 10.0))
        except Exception:
            pass
    if record.get("syncedLyrics"):
        score += 5
    elif record.get("plainLyrics"):
        score += 1
    if record.get("instrumental"):
        score -= 30
    return score


def _record_to_result(record: dict[str, Any], identify_module) -> dict[str, Any] | None:
    synced_text = record.get("syncedLyrics") or ""
    plain = record.get("plainLyrics") or ""
    synced = identify_module.parse_lrc(synced_text)
    if not synced and not plain:
        return None
    return {
        "synced": synced,
        "plain": plain,
        "trackName": record.get("trackName") or "",
        "artistName": record.get("artistName") or "",
    }


def _broad_search(title: str, artist: str, duration: int | None,
                  identify_module) -> dict[str, Any] | None:
    seen_urls: set[str] = set()
    records: list[dict[str, Any]] = []

    for candidate_title, candidate_artist in _variants(title, artist):
        queries = [
            {"track_name": candidate_title, "artist_name": candidate_artist},
            {"track_name": candidate_title},
            {"q": " ".join(x for x in (candidate_artist, candidate_title) if x)},
        ]
        for query in queries:
            query = {k: v for k, v in query.items() if v}
            if not query:
                continue
            url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(query)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                payload = _get_json(url)
            except Exception:
                continue
            if isinstance(payload, list):
                records.extend(x for x in payload if isinstance(x, dict))
            # Keep network traffic bounded. Three distinct successful searches are
            # enough to cover exact, cleaned, and broad metadata variants.
            if len(seen_urls) >= 7:
                break
        if len(seen_urls) >= 7:
            break

    if not records:
        return None

    # Deduplicate LRCLIB records before scoring.
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("id") or (
            _norm(record.get("trackName")),
            _norm(record.get("artistName")),
            record.get("duration"),
        ))
        unique[key] = record

    ranked = sorted(
        unique.values(),
        key=lambda item: _score(item, title, artist, duration),
        reverse=True,
    )
    for record in ranked:
        # Avoid returning a completely unrelated broad-search result.
        if _score(record, title, artist, duration) < 47:
            continue
        result = _record_to_result(record, identify_module)
        if result:
            return result
    return None


def install_lyrics_compat() -> None:
    """Patch only identify.fetch_lyrics, once, preserving all other behavior."""
    global _INSTALLED, _ORIGINAL
    if _INSTALLED:
        return

    from . import identify

    original = identify.fetch_lyrics
    _ORIGINAL = original

    def resilient_fetch_lyrics(title: str, artist: str, album: str | None = None,
                               duration: int | None = None):
        # Preserve Stemmy's original exact-signature + field search first.
        try:
            result = original(title, artist, album, duration)
        except Exception:
            result = None
        if result:
            return result

        # LRCLIB's exact /api/get endpoint requires an exact album and a duration
        # within roughly two seconds. Shazam metadata often differs, so use the
        # documented broad search endpoint as a compatibility fallback.
        try:
            return _broad_search(title, artist, duration, identify)
        except Exception:
            return None

    identify.fetch_lyrics = resilient_fetch_lyrics
    _INSTALLED = True
