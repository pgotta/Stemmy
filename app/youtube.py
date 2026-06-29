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
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "yt_%(id)s.%(ext)s"),
        "ffmpeg_location": ff,
        "noplaylist": True,            # a watch?list= link grabs the one video, not the list
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": prefer,  # -> wav (lossless into the separator)
            "preferredquality": "0",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        first = (str(e).splitlines() or ["download failed"])[0]
        raise YouTubeError("Couldn't fetch that link: " + first[:160])

    if not info:
        raise YouTubeError("Couldn't read that link.")

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
