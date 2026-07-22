"""
identify.py — Shazam song recognition plus resilient lyric retrieval.

The song-identification and lyric providers are independent:
  * Shazam identifies the original audio.
  * LRCLIB supplies synchronized/plain lyrics.
  * Shazam's own lyric text and lyrics.ovh are plain-text fallbacks.

Failures are logged to logs/stemmy-lyrics.log instead of being silently converted
to "no lyrics", which makes provider/API changes diagnosable.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "stemmy-lyrics.log"
CLIENT_ID = "Stemmy/1.5 (https://github.com/pgotta/Stemmy)"
LRCLIB_BASE = "https://lrclib.net/api"
LYRICS_OVH_BASE = "https://api.lyrics.ovh/v1"

# Shazam sometimes supplies plain lyric text in its detailed track response.
# Keep that result available to fetch_lyrics() for the just-identified song.
_SHAZAM_PLAIN: dict[tuple[str, str], str] = {}


def _log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def shazam_available() -> bool:
    try:
        import shazamio  # noqa: F401
        return True
    except Exception as exc:
        _log(f"Shazam unavailable: {type(exc).__name__}: {exc}")
        return False


def _normalise(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"\b(feat(?:uring)?|ft)\.?\s+.*$", "", text, flags=re.I)
    text = re.sub(
        r"[\[(](official|music video|video|visuali[sz]er|audio|lyrics?|"
        r"remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|album version|"
        r"single version|explicit|clean)[^\])]*[\])]",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _clean_title(value: str | None) -> str:
    text = str(value or "").strip()
    text = re.sub(
        r"[\[(](official|music video|video|visuali[sz]er|audio|lyrics?|"
        r"remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|album version|"
        r"single version|explicit|clean)[^\])]*[\])]",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s*[-–—]\s*(official|music video|video|visuali[sz]er|audio|lyrics?|"
        r"remaster(?:ed)?(?:\s+\d{4})?|live|radio edit|album version|"
        r"single version|explicit|clean).*$",
        "",
        text,
        flags=re.I,
    )
    return " ".join(text.strip(" -–—").split())


def _primary_artist(value: str | None) -> str:
    text = str(value or "").strip()
    parts = re.split(
        r"\s*(?:,|;|&|\band\b|\bfeat(?:uring)?\.?|\bft\.?)\s*",
        text,
        maxsplit=1,
        flags=re.I,
    )
    return (parts[0] if parts else text).strip()


def _extract_shazam_plain(track: dict[str, Any]) -> str:
    for section in track.get("sections") or []:
        section_type = str(section.get("type") or "").upper()
        text = section.get("text")
        if section_type == "LYRICS" and isinstance(text, list):
            lines = [str(line).strip() for line in text if str(line).strip()]
            if lines:
                return "\n".join(lines)
        if section_type == "LYRICS" and isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def identify_song(path: str) -> dict | None:
    """Recognise a song and return title/artist/album/art plus optional plain lyrics."""
    try:
        from shazamio import Shazam
    except Exception as exc:
        _log(f"Shazam import failed: {type(exc).__name__}: {exc}")
        return None

    async def _run():
        shazam = Shazam()
        result = await shazam.recognize(path)
        track = (result or {}).get("track") or {}

        # recognize() can omit lyric sections that track_about() includes. Enrich
        # the same matched track when possible, but never let this extra call turn
        # a successful identification into a failure.
        track_id = track.get("key")
        if track_id and not _extract_shazam_plain(track):
            try:
                detail = await shazam.track_about(track_id=int(track_id))
                detail_track = (detail or {}).get("track") or detail or {}
                if isinstance(detail_track, dict):
                    merged = dict(track)
                    for key, value in detail_track.items():
                        if value not in (None, "", [], {}):
                            merged[key] = value
                    track = merged
            except Exception as exc:
                _log(f"Shazam detail lookup skipped for {track_id}: "
                     f"{type(exc).__name__}: {exc}")
        return track

    try:
        track = asyncio.run(_run())
    except RuntimeError:
        # Defensive fallback for an unexpected already-running event loop.
        loop = asyncio.new_event_loop()
        try:
            track = loop.run_until_complete(_run())
        finally:
            loop.close()
    except Exception as exc:
        _log(f"Shazam recognition failed for {path!r}: "
             f"{type(exc).__name__}: {exc}")
        return None

    if not track or not track.get("title"):
        _log(f"Shazam returned no track for {path!r}")
        return None

    album = None
    for section in track.get("sections") or []:
        for metadata in section.get("metadata") or []:
            if str(metadata.get("title") or "").casefold() == "album":
                album = metadata.get("text")
                break
        if album:
            break

    images = track.get("images") or {}
    title = str(track.get("title") or "").strip()
    artist = str(track.get("subtitle") or "").strip()
    plain = _extract_shazam_plain(track)
    if plain:
        _SHAZAM_PLAIN[(_normalise(title), _normalise(artist))] = plain

    result = {
        "title": title,
        "artist": artist,
        "album": album,
        "image": (
            images.get("coverarthq")
            or images.get("coverart")
            or images.get("background")
        ),
        "track_id": track.get("key"),
        "isrc": track.get("isrc"),
        "plain_lyrics": plain,
    }
    _log(f"Shazam identified {artist!r} - {title!r}; album={album!r}; "
         f"plain_lyrics={'yes' if plain else 'no'}")
    return result


def parse_lrc(text: str) -> list[list]:
    """Parse LRC ('[mm:ss.xx] words') into [[seconds, text], ...]."""
    output: list[list] = []
    if not text:
        return output
    tag = re.compile(r"\[(\d+):(\d+)(?:\.(\d+))?\]")
    for line in text.splitlines():
        stamps = list(tag.finditer(line))
        if not stamps:
            continue
        words = line[stamps[-1].end():].strip()
        for match in stamps:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or "0"
            output.append([
                round(minutes * 60 + seconds + float("0." + fraction), 2),
                words,
            ])
    output.sort(key=lambda item: item[0])
    return output


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _request_json(url: str, provider: str, attempts: int = 3) -> Any:
    headers = {
        "User-Agent": CLIENT_ID,
        "Lrclib-Client": CLIENT_ID,
        "X-User-Agent": CLIENT_ID,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    last_error: Exception | None = None

    # requests generally behaves better with modern HTTPS/CDN stacks on Windows.
    try:
        import requests
    except Exception:
        requests = None

    for attempt in range(1, attempts + 1):
        try:
            if requests is not None:
                response = requests.get(url, headers=headers, timeout=(8, 22))
                if response.status_code == 404:
                    _log(f"{provider} 404: {url}")
                    return None
                response.raise_for_status()
                return response.json()

            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(
                request, timeout=22, context=_ssl_context()
            ) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            if exc.code == 404:
                _log(f"{provider} 404: {url}")
                return None
            last_error = exc
            _log(f"{provider} HTTP {exc.code} attempt {attempt}/{attempts}: "
                 f"{url} body={body!r}")
        except Exception as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            body = ""
            try:
                body = (getattr(exc.response, "text", "") or "")[:300]
            except Exception:
                pass
            _log(f"{provider} request attempt {attempt}/{attempts} failed"
                 f"{' HTTP '+str(status) if status else ''}: {url}; "
                 f"{type(exc).__name__}: {exc}; body={body!r}")
        if attempt < attempts:
            time.sleep(0.6 * attempt)

    _log(f"{provider} exhausted retries: {type(last_error).__name__ if last_error else 'error'}: "
         f"{last_error}")
    return None


def _to_result(record: dict[str, Any], source: str) -> dict | None:
    synced = parse_lrc(str(record.get("syncedLyrics") or ""))
    plain = str(record.get("plainLyrics") or "").strip()
    if not synced and not plain:
        return None
    return {
        "synced": synced,
        "plain": plain,
        "trackName": record.get("trackName") or "",
        "artistName": record.get("artistName") or "",
        "source": source,
    }


def _candidate_score(
    record: dict[str, Any],
    title: str,
    artist: str,
    duration: int | None,
) -> float:
    wanted_title = _normalise(title)
    wanted_artist = _normalise(artist)
    got_title = _normalise(record.get("trackName"))
    got_artist = _normalise(record.get("artistName"))
    if not wanted_title or not got_title:
        return -1.0

    title_ratio = difflib.SequenceMatcher(None, wanted_title, got_title).ratio()
    artist_ratio = (
        difflib.SequenceMatcher(None, wanted_artist, got_artist).ratio()
        if wanted_artist and got_artist else 0.55
    )
    score = title_ratio * 70.0 + artist_ratio * 24.0
    if wanted_title == got_title:
        score += 14.0
    if wanted_artist and wanted_artist == got_artist:
        score += 8.0
    if duration:
        try:
            delta = abs(float(record.get("duration") or 0) - float(duration))
            score += max(0.0, 10.0 - min(delta, 10.0))
        except Exception:
            pass
    if record.get("syncedLyrics"):
        score += 5.0
    elif record.get("plainLyrics"):
        score += 1.0
    if record.get("instrumental"):
        score -= 40.0
    return score


def _search_variants(title: str, artist: str, album: str | None):
    clean_title = _clean_title(title) or title
    primary_artist = _primary_artist(artist) or artist
    variants: list[dict[str, str]] = []

    for query in (
        {"track_name": title, "artist_name": artist},
        {"q": " ".join(x for x in (artist, title) if x)},
        {"track_name": clean_title, "artist_name": primary_artist},
        {"q": " ".join(x for x in (primary_artist, clean_title) if x)},
        {"track_name": clean_title},
        {"track_name": title},
    ):
        cleaned = {key: str(value).strip() for key, value in query.items()
                   if str(value or "").strip()}
        if cleaned and cleaned not in variants:
            variants.append(cleaned)

    if album:
        enriched = {
            "track_name": clean_title,
            "artist_name": primary_artist,
            "album_name": str(album).strip(),
        }
        if enriched not in variants:
            variants.insert(1, enriched)
    return variants


def _lrclib_lookup(
    title: str,
    artist: str,
    album: str | None,
    duration: int | None,
) -> dict | None:
    # The exact signature endpoint is useful when all metadata really matches.
    # Do not invent an album name: LRCLIB documents album and duration as exact
    # signature fields, and a fake album causes predictable misses.
    if title and artist and album and duration:
        query = {
            "track_name": title,
            "artist_name": artist,
            "album_name": album,
            "duration": int(duration),
        }
        url = LRCLIB_BASE + "/get?" + urllib.parse.urlencode(query)
        payload = _request_json(url, "LRCLIB exact")
        if isinstance(payload, dict):
            result = _to_result(payload, "LRCLIB exact")
            if result:
                _log(f"LRCLIB exact match: {artist!r} - {title!r}")
                return result

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for query in _search_variants(title, artist, album):
        url = LRCLIB_BASE + "/search?" + urllib.parse.urlencode(query)
        payload = _request_json(url, "LRCLIB search")
        count = len(payload) if isinstance(payload, list) else 0
        _log(f"LRCLIB search {query!r} returned {count} record(s)")
        if not isinstance(payload, list):
            continue
        for record in payload:
            if not isinstance(record, dict):
                continue
            key = str(record.get("id") or (
                _normalise(record.get("trackName")),
                _normalise(record.get("artistName")),
                record.get("duration"),
            ))
            if key not in seen_ids:
                seen_ids.add(key)
                records.append(record)

    if not records:
        return None

    ranked = sorted(
        records,
        key=lambda record: _candidate_score(record, title, artist, duration),
        reverse=True,
    )
    for record in ranked:
        score = _candidate_score(record, title, artist, duration)
        _log("LRCLIB candidate "
             f"score={score:.1f} artist={record.get('artistName')!r} "
             f"title={record.get('trackName')!r} duration={record.get('duration')!r}")
        if score < 48.0:
            continue
        result = _to_result(record, "LRCLIB search")
        if result:
            return result
        record_id = record.get("id")
        if record_id is not None:
            detail = _request_json(
                LRCLIB_BASE + "/get/" + urllib.parse.quote(str(record_id)),
                "LRCLIB record",
            )
            if isinstance(detail, dict):
                result = _to_result(detail, "LRCLIB record")
                if result:
                    return result
    return None


def _plain_fallback(title: str, artist: str) -> dict | None:
    shazam_plain = _SHAZAM_PLAIN.get((_normalise(title), _normalise(artist)), "")
    if shazam_plain:
        _log(f"Using plain lyrics returned by Shazam for {artist!r} - {title!r}")
        return {
            "synced": [],
            "plain": shazam_plain,
            "trackName": title,
            "artistName": artist,
            "source": "Shazam",
        }

    if not title or not artist:
        return None
    url = (
        LYRICS_OVH_BASE + "/"
        + urllib.parse.quote(artist, safe="") + "/"
        + urllib.parse.quote(title, safe="")
    )
    payload = _request_json(url, "lyrics.ovh", attempts=2)
    if isinstance(payload, dict):
        plain = str(payload.get("lyrics") or "").strip()
        if plain:
            _log(f"Using lyrics.ovh plain fallback for {artist!r} - {title!r}")
            return {
                "synced": [],
                "plain": plain,
                "trackName": title,
                "artistName": artist,
                "source": "lyrics.ovh",
            }
    return None


def fetch_lyrics(
    title: str,
    artist: str,
    album: str | None = None,
    duration: int | None = None,
) -> dict | None:
    """Fetch lyrics, preferring synchronized LRCLIB records."""
    title = str(title or "").strip()
    artist = str(artist or "").strip()
    album = str(album or "").strip() or None
    try:
        duration = int(round(float(duration))) if duration else None
    except Exception:
        duration = None

    if not title:
        _log("Lyrics lookup skipped: empty title")
        return None

    _log(f"Lyrics lookup started: artist={artist!r}, title={title!r}, "
         f"album={album!r}, duration={duration!r}")
    result = _lrclib_lookup(title, artist, album, duration)
    if result:
        _log(f"Lyrics found via {result.get('source')}: "
             f"synced={len(result.get('synced') or [])}, "
             f"plain_chars={len(result.get('plain') or '')}")
        return result

    result = _plain_fallback(title, artist)
    if result:
        _log(f"Plain lyrics found via {result.get('source')}")
        return result

    _log(f"No lyrics found after all providers for {artist!r} - {title!r}")
    return None
