"""
karaoke.py — batch "remove vocals from a whole playlist" jobs.

Flow per track: fetch audio (yt-dlp) -> create a project -> run the normal
separation pipeline at a light depth -> mix every non-vocal stem back down to a
single `instrumental.wav`. Progress is pushed to a per-job queue so the server
can stream it over SSE, and the finished instrumentals are zipped on demand.

Jobs live in memory (single local user); they clear when the server restarts.
Heavy deps (the separator, soundfile) are only touched inside the worker thread.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from . import projects, models, youtube
from .pipeline import Pipeline

# job_id -> job dict
JOBS: dict[str, dict] = {}

# Batches are persisted here so a session survives a server restart (issue: a
# batch was lost on restart and had to be redone). Only serializable fields are
# written; the live queue/thread are never persisted.
JOBS_DIR = projects.PROJECTS_DIR.parent / "karaoke_jobs"
JOBS_DIR.mkdir(exist_ok=True)

_JUNK = re.compile(r"[\(\[][^\)\]]*(official|video|visualizer|visualiser|lyric|lyrics|audio|hd|4k|remaster)[^\)\]]*[\)\]]", re.I)


def _job_file(job_id: str) -> Path:
    return JOBS_DIR / (job_id + ".json")


def _persist(job: dict) -> None:
    """Write the serializable slice of a job to disk (atomic-ish)."""
    try:
        data = {"id": job["id"], "status": job["status"], "depth": job["depth"],
                "name": job.get("name") or "",
                "url": job.get("url") or "",
                "created": job.get("created") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "items": [{k: v for k, v in it.items() if not k.startswith("_")}
                          for it in job["items"]]}
        p = _job_file(job["id"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)
    except Exception:
        pass


def load_all() -> None:
    """Rehydrate saved batches into memory on startup so tracks stay playable.

    A restored job keeps its finished instrumentals (they live in project
    folders on disk). Any track left mid-run is marked so the UI can show it as
    unfinished. Restored jobs are not auto-resumed; the user restarts if wanted.
    """
    for f in sorted(JOBS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        jid = data.get("id") or f.stem
        if jid in JOBS:
            continue
        items = data.get("items") or []
        for it in items:
            # a track that never finished can't be resumed from memory; flag it
            if it.get("status") not in ("done", "error"):
                it["status"] = "interrupted"
        JOBS[jid] = {"id": jid, "status": "done" if data.get("status") == "running" else data.get("status", "done"),
                     "depth": data.get("depth") or "quick",
                     "name": data.get("name") or "", "url": data.get("url") or "",
                     "created": data.get("created") or "",
                     "items": items, "_q": queue.Queue(), "_restored": True}


def track_file(it: dict):
    """Resolve a track's instrumental file on disk, or None.

    Mirrors the serving route: try the recorded absolute path, then fall back to
    the track's own project folder (covers a moved install or a restored session
    whose absolute path no longer resolves).
    """
    p = it.get("instrumental")
    if p:
        pp = Path(p)
        if pp.exists():
            return pp
    pid = it.get("pid")
    if pid:
        pdir = projects.project_dir(pid)
        for cand in (pdir / "instrumental.wav", pdir / "instrumental.mp3"):
            if cand.exists():
                return cand
    return None


def list_saved() -> list:
    """Summaries of every persisted batch, newest first (for a restore list).

    `done` counts tracks marked done; `playable` counts tracks whose instrumental
    file is actually present on disk right now, so the UI can tell the user the
    truth even if a folder was deleted or moved.
    """
    out = []
    for jid, job in sorted(JOBS.items(),
                           key=lambda kv: kv[1].get("created") or "", reverse=True):
        done = sum(1 for i in job["items"] if i.get("status") == "done")
        playable = sum(1 for i in job["items"] if track_file(i) is not None)
        out.append({"id": jid, "name": job.get("name") or (job["items"][0]["title"] if job["items"] else "batch"),
                    "created": job.get("created") or "", "depth": job.get("depth"),
                    "total": len(job["items"]), "done": done, "playable": playable,
                    "status": job.get("status")})
    return out


def _clean_title(raw: str):
    """Turn a YouTube title into (track, artist) for lyric lookup.

    'Dayseeker - Neon Grave (Official Visualizer)' -> ('Neon Grave', 'Dayseeker').
    """
    s = _JUNK.sub("", raw or "").strip(" -–|")
    if " - " in s:
        artist, track = s.split(" - ", 1)
        return track.strip(), artist.strip()
    return s, ""


def _emit(job, ev):
    job["_q"].put(ev)


def start(url: str, depth: str, model_dir: str, uploads_dir: Path) -> dict:
    """Enumerate the playlist and kick off the background worker.

    Returns the job dict (without the internal queue). Raises youtube.YouTubeError
    if the playlist can't be read.
    """
    if depth not in models.DEPTH_PRESETS:
        depth = "quick"
    entries = youtube.list_playlist(url)      # may raise YouTubeError

    job_id = uuid.uuid4().hex[:12]
    items = [{"n": i, "id": e["id"], "title": e["title"], "url": e["url"],
              "status": "queued", "pid": None, "instrumental": None, "error": None}
             for i, e in enumerate(entries)]
    # a friendly name for the restore list: playlist title if we have one, else
    # the first track, else the raw link.
    name = ""
    try:
        name = youtube.playlist_title(url)  # optional helper; ignored if absent
    except Exception:
        name = ""
    if not name:
        name = (items[0]["title"] if items else "") or url
    job = {"id": job_id, "status": "running", "depth": depth,
           "name": name, "url": url,
           "created": time.strftime("%Y-%m-%d %H:%M:%S"),
           "items": items, "_q": queue.Queue()}
    JOBS[job_id] = job
    _persist(job)

    t = threading.Thread(target=_worker, args=(job, model_dir, Path(uploads_dir)),
                         daemon=True)
    t.start()
    return job


def _worker(job, model_dir: str, uploads_dir: Path, items=None):
    """Process items (default: all). `items` lets retry target only failures."""
    todo = items if items is not None else job["items"]
    for item in todo:
        _process_item(job, item, model_dir, uploads_dir)

    done = sum(1 for i in job["items"] if i["status"] == "done")
    job["status"] = "done"
    _persist(job)
    _emit(job, {"type": "done", "completed": done, "total": len(job["items"])})


def _process_item(job, item, model_dir: str, uploads_dir: Path):
    try:
        item["status"] = "downloading"
        item["error"] = None
        _emit(job, {"type": "item", "n": item["n"], "status": "downloading"})
        title, audio_path, thumb = youtube.fetch_audio(item["url"], uploads_dir)

        ext = audio_path.suffix.lower() or ".wav"
        fname = (title or item["title"] or "track") + ext
        pid = projects.new_id(fname)
        dest = projects.project_dir(pid)
        dest.mkdir(parents=True, exist_ok=True)
        src = dest / ("source" + ext)
        import shutil
        shutil.move(str(audio_path), str(src))
        proj = projects.create(pid, fname, str(src))
        proj["source_kind"] = "youtube"
        cover = youtube.save_thumbnail(thumb, dest)
        if cover:
            proj["cover"] = cover
        projects.save(proj)
        item["pid"] = pid
        if title:
            item["title"] = title

        # identify the song (Shazam on the ORIGINAL audio, pre vocal-removal)
        # and fetch lyrics now, so the karaoke player has them ready.
        try:
            from . import identify
            info = identify.identify_song(str(src)) if identify.shazam_available() else None
            lyr = None
            if info and info.get("title"):
                nice = ((info.get("artist") or "") + " - " + info["title"]).strip(" -")
                item["title"] = nice
                proj["source_name"] = nice
                img = info.get("image")
                if img:
                    cov = youtube.save_thumbnail(img, dest, "cover.jpg")
                    if cov:
                        proj["cover"] = cov
                lyr = identify.fetch_lyrics(info["title"], info.get("artist") or "",
                                            info.get("album"), proj.get("duration"))
            if not lyr:
                # no shazam / no match: try lyrics from the (cleaned) video title
                ct, ca = _clean_title(item["title"])
                lyr = identify.fetch_lyrics(ct, ca, None, proj.get("duration"))
            if lyr:
                proj["lyrics"] = {"synced": lyr["synced"], "plain": lyr["plain"]}
            projects.save(proj)
            item["has_lyrics"] = bool(lyr)
            _emit(job, {"type": "item", "n": item["n"], "status": item["status"],
                        "title": item["title"], "pid": pid,
                        "has_lyrics": item["has_lyrics"]})
        except Exception:
            item["has_lyrics"] = False

        item["status"] = "separating"
        _emit(job, {"type": "item", "n": item["n"], "status": "separating",
                    "title": item["title"], "pid": pid})
        Pipeline(model_dir).run(proj, job["depth"], lambda ev: None)
        proj = projects.load(pid)          # reload with stems

        item["status"] = "mixing"
        _emit(job, {"type": "item", "n": item["n"], "status": "mixing"})
        inst = build_instrumental(proj)
        item["instrumental"] = str(inst) if inst else None
        item["status"] = "done" if inst else "error"
        if not inst:
            item["error"] = "no instrumental produced"
        _emit(job, {"type": "item", "n": item["n"],
                    "status": item["status"], "error": item["error"]})
        _persist(job)
    except Exception as e:
        item["status"] = "error"
        raw = (str(e).splitlines() or ["error"])[0]
        if "403" in raw or "Forbidden" in raw:
            item["error"] = "YouTube blocked this download (403). Run update_ytdlp.bat, then Retry failed."
        else:
            item["error"] = raw[:180]
        _emit(job, {"type": "item", "n": item["n"], "status": "error",
                    "error": item["error"]})
        _persist(job)


def retry(job_id: str, model_dir: str, uploads_dir: Path):
    """Re-run every errored / interrupted track in a batch.

    Returns the job dict if a retry started, or None (unknown job / already
    running / nothing to retry). Downloads can fail transiently (e.g. YouTube
    403s), so failed tracks are re-queued from scratch through the same worker.
    """
    job = JOBS.get(job_id)
    if not job or job.get("status") == "running":
        return None
    failed = [it for it in job["items"] if it.get("status") in ("error", "interrupted")]
    if not failed:
        return None
    for it in failed:
        it["status"] = "queued"
        it["error"] = None
    job["status"] = "running"
    job["_q"] = queue.Queue()               # fresh stream for the new run
    job.pop("_restored", None)
    _persist(job)
    t = threading.Thread(target=_worker, args=(job, model_dir, Path(uploads_dir), failed),
                         daemon=True)
    t.start()
    return job


def build_instrumental(proj: dict):
    """Write <project>/instrumental.wav (+ .mp3) with vocals removed.

    Returns the WAV Path (primary), or None if there are no usable stems.
    """
    from . import mixdown
    outs = mixdown.build_combined(proj, drop_ids={"vocals", "metronome"},
                                  drop_types={"vocal", "click"}, stem="instrumental")
    wav = next((p for p in outs if p.suffix == ".wav"), None)
    return wav


def get(job_id: str):
    return JOBS.get(job_id)


def delete(job_id: str) -> bool:
    """Forget a batch and remove its persisted file. Project folders are kept."""
    JOBS.pop(job_id, None)
    try:
        f = _job_file(job_id)
        if f.exists():
            f.unlink()
        return True
    except Exception:
        return False


def public(job: dict) -> dict:
    """Job dict without the internal queue, safe to jsonify.

    Each item gets a `playable` flag reflecting whether its instrumental file is
    actually on disk right now, so the player only queues tracks it can play.
    """
    items = []
    for it in job["items"]:
        d = {k: v for k, v in it.items() if not k.startswith("_")}
        d["playable"] = track_file(it) is not None
        items.append(d)
    return {"id": job["id"], "status": job["status"], "depth": job["depth"],
            "name": job.get("name") or "", "created": job.get("created") or "",
            "restored": bool(job.get("_restored")), "items": items}
