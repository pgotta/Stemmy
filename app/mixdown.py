"""
mixdown.py — build combined mixes from separated stems and encode MP3.

Used for two things:
  * the "full song" combined file added to stem-export zips (all stems minus
    the click track), as both WAV and MP3;
  * the karaoke instrumental (all stems minus vocals and click), WAV + MP3.

MP3 encoding uses the same ffmpeg the YouTube importer uses (system ffmpeg if
present, otherwise the one bundled with imageio-ffmpeg).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import projects


def ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _leaf_stems(proj: dict):
    """Leaf stems only (a stem that isn't the parent of any other)."""
    stems = proj.get("stems", [])
    parents = {s.get("parent") for s in stems if s.get("parent")}
    return [s for s in stems if s["id"] not in parents]


def sum_stems(proj: dict, drop_ids=frozenset(), drop_types=frozenset()):
    """Sum the wanted leaf stems into one array. Returns (data, sr) or (None, sr)."""
    import numpy as np
    import soundfile as sf

    pdir = projects.project_dir(proj["id"])
    mix = None
    sr = 44100
    for s in _leaf_stems(proj):
        sid = (s.get("id") or "").lower()
        stype = (s.get("type") or "").lower()
        if sid in drop_ids or stype in drop_types:
            continue
        rel = s.get("_rel")
        if not rel:
            continue
        p = pdir / rel
        if not p.exists():
            continue
        data, sr = sf.read(str(p), always_2d=True)
        if mix is None:
            mix = np.zeros_like(data)
        n = min(len(mix), len(data))
        if data.shape[1] != mix.shape[1]:
            data = (data[:, :1] if mix.shape[1] == 1
                    else np.repeat(data[:, :1], mix.shape[1], axis=1))
        mix[:n] += data[:n]
    if mix is None:
        return None, sr
    peak = float(np.max(np.abs(mix)))
    if peak > 1.0:
        mix = mix / peak * 0.98          # gentle normalize to avoid clipping
    return mix, sr


def write_wav(data, sr, out_path: Path) -> Path | None:
    import soundfile as sf
    if data is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), data, sr)
    return out_path


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> Path | None:
    """Encode a WAV to MP3 (V2, ~190kbps). Returns the path or None on failure."""
    exe = ffmpeg_exe()
    if not exe or not Path(wav_path).exists():
        return None
    try:
        r = subprocess.run(
            [exe, "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
             "-q:a", "2", str(mp3_path)],
            capture_output=True, text=True)
        if r.returncode == 0 and Path(mp3_path).exists():
            return mp3_path
    except Exception:
        pass
    return None


def build_combined(proj: dict, drop_ids=frozenset(), drop_types=frozenset(),
                   stem="mix"):
    """Write <stem>.wav and <stem>.mp3 (combined) into the project dir.

    Returns a list of existing Paths (wav first, mp3 if encoding worked)."""
    pdir = projects.project_dir(proj["id"])
    data, sr = sum_stems(proj, drop_ids, drop_types)
    if data is None:
        return []
    wav = write_wav(data, sr, pdir / (stem + ".wav"))
    out = [wav] if wav else []
    if wav:
        mp3 = wav_to_mp3(wav, pdir / (stem + ".mp3"))
        if mp3:
            out.append(mp3)
    return out
