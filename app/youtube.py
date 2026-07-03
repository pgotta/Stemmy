"""
youtube.py — pull audio from a YouTube (or any yt-dlp-supported) link and extract
it to a WAV that the normal separation pipeline can consume.

Uses yt-dlp for the download and ffmpeg for the audio extraction. ffmpeg is found
on the system PATH first, then falls back to the pip-installed `imageio-ffmpeg`
binary, so a user doesn't have to install ffmpeg separately — `setup.bat` pulls
both `yt-dlp` and `imageio-ffmpeg` in through requirements.txt.

Nothing here touches the network at import time; everything is lazy so the server
still boots instantly without these deps installed.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path


class YouTubeError(RuntimeError):
    """User-facing problem fetching a link (bad URL, missing dep, unavailable)."""


def looks_like_url(s: str) -> bool:
    return bool(s) and bool(re.match(r"^https?://", s.strip(), re.I))


def is_youtube(url: str) -> bool:
    return bool(re.search(r"(youtube\.com/|youtu\.be/|music\.youtube\.com/)",
                          url or "", re.I))


def _ffmpeg_location() -> str | None:
    """Directory containing an ffmpeg binary, or None if none can be found."""
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    try:                                   # pip-installed, bundled ffmpeg
        import imageio_ffmpeg
        return str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent)
    except Exception:
        return None


def fetch_audio(url: str, dest_dir: Path, prefer: str = "wav") -> tuple[str, Path]:
    """Download the best audio for `url` and extract it to `dest_dir/yt_<id>.wav`.

    Returns (title, path). Raises YouTubeError with a friendly message on failure.
    """
    url = (url or "").strip()
    if not looks_like_url(url):
        raise YouTubeError("That doesn't look like a link — paste a full https:// URL.")

    try:
        import yt_dlp
    except Exception:
        raise YouTubeError("yt-dlp isn't installed. Run setup.bat (or: pip install yt-dlp).")

    ff = _ffmpeg_location()
    if ff is None:
        raise YouTubeError("ffmpeg not found. Run setup.bat (or: pip install imageio-ffmpeg), "
                           "or install ffmpeg and put it on your PATH.")

    dest_dir.mkdir(parents=True, exist_ok=True)
    # Base options. The 403s people hit on a subset of tracks are almost always
    # yt-dlp getting handed a format whose CDN URL rejects the download (stale or
    # PO-token-gated signed URLs). The fixes that actually move the needle:
    #   - ask specific player clients that hand back plain, downloadable formats
    #     (android / ios / tv) instead of the web client's gated ones;
    #   - avoid the storyboard/HLS variants by sorting toward plain https audio;
    #   - let yt-dlp retry fragments and whole requests before giving up.
    base = {
        "outtmpl": str(dest_dir / "yt_%(id)s.%(ext)s"),
        "ffmpeg_location": ff,
        "noplaylist": True,            # a watch?list= link grabs the one video, not the list
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,
        "http_chunk_size": 10 * 1024 * 1024,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": prefer,  # -> wav (lossless into the separator)
            "preferredquality": "0",
        }],
    }

    # Try a sequence of player-client configs; the first that downloads wins.
    # Each entry is (format_selector, player_clients). android/ios rarely 403.
    attempts = [
        ("bestaudio[protocol^=http]/bestaudio/best", ["android", "ios"]),
        ("bestaudio/best", ["ios", "web_safari"]),
        ("bestaudio/best", ["tv"]),
        ("bestaudio/best", None),   # last resort: yt-dlp defaults
    ]

    info = None
    last_err = None
    for fmt, clients in attempts:
        opts = dict(base)
        opts["format"] = fmt
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if info:
                break
        except Exception as e:
            last_err = e
            # clean any partial fragments before the next client attempt
            vid_guess = ""
            try:
                vid_guess = (str(e))  # noop, keeps linters calm
            except Exception:
                pass
            for junk in dest_dir.glob("yt_*.part"):
                try:
                    junk.unlink()
                except Exception:
                    pass
            continue

    if not info:
        first = (str(last_err).splitlines() or ["download failed"])[0] if last_err else "download failed"
        raise YouTubeError("Couldn't fetch that link: " + first[:160])

    vid = info.get("id") or ""
    title = info.get("title") or vid or "youtube-audio"
    thumb = info.get("thumbnail") or ""
    if not thumb:
        thumbs = info.get("thumbnails") or []
        if thumbs:
            thumb = (thumbs[-1] or {}).get("url", "") or ""

    produced = dest_dir / f"yt_{vid}.{prefer}"
    if not produced.exists():
        cands = sorted(dest_dir.glob(f"yt_{vid}.*")) or sorted(dest_dir.glob(f"yt_*.{prefer}"))
        if not cands:
            raise YouTubeError("Audio extraction produced no file — is ffmpeg working?")
        produced = cands[0]
    return title, produced, thumb


def save_thumbnail(url: str, dest_dir: Path, name: str = "cover.jpg") -> str | None:
    """Download a thumbnail image to dest_dir/name. Best-effort: returns the file
    name on success, None on any failure (never raises — a missing cover is fine)."""
    url = (url or "").strip()
    if not url:
        return None
    try:
        import urllib.request
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / name
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
        if not data:
            return None
        out.write_bytes(data)
        return name
    except Exception:
        return None

def list_playlist(url: str, limit: int = 100) -> list[dict]:
    """Enumerate a playlist (or single video) without downloading audio.

    Returns [{id, title, url}]. A single-video link yields one entry. Uses
    yt-dlp's flat extraction so it's fast. Raises YouTubeError on failure.
    """
    url = (url or "").strip()
    if not looks_like_url(url):
        raise YouTubeError("That doesn't look like a link — paste a full https:// URL.")
    try:
        import yt_dlp
    except Exception:
        raise YouTubeError("yt-dlp isn't installed. Run setup.bat (or: pip install yt-dlp).")

    opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": "in_playlist",   # list entries, don't resolve each fully
        "skip_download": True,
        "noplaylist": False,             # DO expand the playlist here
        "playlistend": limit,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        first = (str(e).splitlines() or ["failed"])[0]
        raise YouTubeError("Couldn't read that playlist: " + first[:160])
    if not info:
        raise YouTubeError("Couldn't read that link.")

    entries = info.get("entries")
    out = []
    if entries:  # a real playlist
        for en in entries:
            if not en:
                continue
            vid = en.get("id") or ""
            link = en.get("url") or en.get("webpage_url") or (
                ("https://www.youtube.com/watch?v=" + vid) if vid else "")
            if not link:
                continue
            if link and not link.startswith("http") and vid:
                link = "https://www.youtube.com/watch?v=" + vid
            out.append({"id": vid or link, "title": en.get("title") or vid or "track",
                        "url": link})
    else:        # a single video
        vid = info.get("id") or ""
        out.append({"id": vid or url, "title": info.get("title") or vid or "track",
                    "url": info.get("webpage_url") or url})
    if not out:
        raise YouTubeError("No videos found at that link.")
    return out[:limit]


def playlist_title(url: str) -> str:
    """Best-effort playlist/video title for labelling a saved batch. Never raises."""
    url = (url or "").strip()
    if not looks_like_url(url):
        return ""
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                "skip_download": True, "noplaylist": False, "playlistend": 1}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        # a playlist has its own title; a single video falls back to the video title
        if info.get("entries") is not None:
            return (info.get("title") or "").strip()
        return (info.get("title") or "").strip()
    except Exception:
        return ""
