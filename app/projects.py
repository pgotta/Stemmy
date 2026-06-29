"""
projects.py — on-disk project store with resume support.

Each upload becomes a project folder:

    projects/<id>/
        project.json      # metadata, stem tree, analysis, pass status
        source.<ext>      # the original upload
        stems/
            vocals.wav
            drums/kick.wav ...

project.json is the single source of truth. If separation is interrupted, the
next load resumes from the last completed pass (matches the SeeStory pattern).
"""

import json
import re
import shutil
import time
import uuid
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"
PROJECTS_DIR.mkdir(exist_ok=True)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _slug(name):
    base = Path(name).stem if name else ""
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")
    return base[:40].strip("-")


def new_id(name=None):
    # Folder/URL-safe, human-readable: "<song-slug>_2026-06-26_20-40-15".
    # Falls back to -2, -3 ... if one already exists.
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    slug = _slug(name)
    base = f"{slug}_{stamp}" if slug else stamp
    pid = base
    n = 2
    while (PROJECTS_DIR / pid).exists():
        pid = f"{base}-{n}"
        n += 1
    return pid


def clear_all():
    """Delete every project folder (keeps the .gitkeep). Returns the count."""
    n = 0
    if PROJECTS_DIR.exists():
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                n += 1
    return n


def project_dir(pid: str) -> Path:
    return PROJECTS_DIR / pid


def json_path(pid: str) -> Path:
    return project_dir(pid) / "project.json"


def create(pid: str, source_name: str, source_path: str, sample_rate=None,
           bit_depth=None, duration=None) -> dict:
    d = project_dir(pid)
    (d / "stems").mkdir(parents=True, exist_ok=True)
    data = {
        "id": pid,
        "created": _now(),
        "source_name": source_name,
        "source_path": str(source_path),
        "sample_rate": sample_rate,
        "bit_depth": bit_depth,
        "duration": duration,
        "depth": None,
        "status": "uploaded",          # uploaded | separating | done | error
        "passes": [],                  # [{key,label,status,pct}]
        "stems": [],                   # flat list of {id,parent,...,url}
        "analysis": {},                # {bpm,key,downbeats}
    }
    save(data)
    return data


def save(data: dict) -> None:
    p = json_path(data["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(p)  # atomic-ish write so a crash mid-save can't corrupt the file


def load(pid: str):
    p = json_path(pid)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_all():
    out = []
    for p in sorted(PROJECTS_DIR.glob("*/project.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append({"id": d["id"], "name": d["source_name"],
                        "status": d["status"], "created": d["created"],
                        "depth": d.get("depth"),
                        "cover": ("/api/cover/" + d["id"]) if d.get("cover") else None,
                        "stems": len(d.get("stems") or [])})
        except Exception:
            continue
    return out


def completed_passes(data: dict) -> set:
    return {p["key"] for p in data.get("passes", [])
            if p.get("status") == "done" and not p.get("skipped")}
