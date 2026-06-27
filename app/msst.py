"""Optional ZFTurbo MSST integration (extended multi-instrument separation).

Orchestrates the *optional* Extended depth. Ships no model — the user installs
MSST + a model with get_msst.bat, which drops the repo in models_cache/msst/ and
the model in models_cache/msst_models/ with a manifest.json. We shell out to
MSST's own inference.py.

Memory: a 53-stem model assembles its whole output as one (53, 2, N) float array.
For a full song that's ~5 GB plus several 1+ GB temporaries — so full-length runs
are RAM-heavy (plan on ~12-16 GB free; 32 GB+ comfortable). We run full-length by
default anyway, because these models separate far better with the whole song in
view; chunking smears everything into a few stems. If RAM is tight, set
STEMMY_MSST_FULL=0 to fall back to overlapping ~12 s segments that are stitched
back together (bounded RAM, weaker separation).

Everything degrades gracefully: not installed -> is_installed() False and the pass
skips; a crash mid-run -> separate() raises and the pass skips. Never breaks a run.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
import os
from pathlib import Path


def _avail_ram_gb() -> float | None:
    """Best-effort available system RAM in GB; None if it can't be determined."""
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:
        pass
    try:                                  # Windows without psutil
        import ctypes

        class _M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = _M(); m.dwLength = ctypes.sizeof(_M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1e9
    except Exception:
        pass
    try:                                  # Linux
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1e6
    except Exception:
        pass
    return None


def _root(model_dir: str) -> Path:
    return Path(model_dir) / "msst"


def _models(model_dir: str) -> Path:
    return Path(model_dir) / "msst_models"


def manifest(model_dir: str) -> dict | None:
    f = _models(model_dir) / "manifest.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except Exception:
        return None


def is_installed(model_dir: str) -> bool:
    man = manifest(model_dir)
    if not man:
        return False
    if not (_root(model_dir) / "inference.py").exists():
        return False
    cfg = _models(model_dir) / man.get("config", "")
    ckpt = _models(model_dir) / man.get("checkpoint", "")
    try:
        return (cfg.exists() and ckpt.exists()
                and ckpt.stat().st_size > 50_000_000)
    except Exception:
        return False


def model_label(model_dir: str) -> str:
    man = manifest(model_dir) or {}
    return man.get("checkpoint", "MSST model")


# ---------------------------------------------------------------- audio helpers
def _read_audio(path: str):
    """Return (data float32 shape (samples, channels), samplerate). soundfile
    first (handles wav/flac/ogg and modern mp3); librosa as a fallback."""
    try:
        import soundfile as sf
        data, sr = sf.read(path, always_2d=True, dtype="float32")
        return data, sr
    except Exception:
        import librosa
        import numpy as np
        y, sr = librosa.load(path, sr=None, mono=False)
        if y.ndim == 1:
            y = y[None, :]
        return np.ascontiguousarray(y.T).astype("float32"), sr


def _info(path: str):
    """(n_frames, samplerate) without loading the whole file when possible."""
    try:
        import soundfile as sf
        i = sf.info(path)
        return i.frames, i.samplerate
    except Exception:
        data, sr = _read_audio(path)
        return data.shape[0], sr


def nonsilent(wav_path: str, thresh: float = 0.0025) -> bool:
    """True if the file has audible content. Uses soundfile (reads MSST's float
    WAVs correctly); falls back to the stdlib wave reader for PCM files."""
    try:
        import soundfile as sf
        import numpy as np
        peak = 0.0
        with sf.SoundFile(wav_path) as f:
            for block in f.blocks(blocksize=131072, dtype="float32", always_2d=True):
                if block.size:
                    p = float(np.abs(block).max())
                    if p > peak:
                        peak = p
                if peak >= thresh:
                    return True
        return peak >= thresh
    except Exception:
        pass
    try:
        import wave
        import audioop
        with wave.open(wav_path, "rb") as w:
            n = w.getnframes()
            if n == 0:
                return False
            frames = w.readframes(min(n, w.getframerate() * 30))
            width = w.getsampwidth()
            peak = audioop.max(frames, width)
            return (peak / float(1 << (8 * width - 1))) >= thresh
    except Exception:
        return True


# ---------------------------------------------------------------- MSST runner
def _run_inference(root: Path, mm: Path, man: dict, in_dir: Path, store: Path,
                   template: str, python_exe: str | None, timeout: int | None):
    exe = python_exe or sys.executable
    cmd = [
        exe, str(root / "inference.py"),
        "--model_type", man["model_type"],
        "--config_path", str(mm / man["config"]),
        "--start_check_point", str(mm / man["checkpoint"]),
        "--input_folder", str(in_dir),
        "--store_dir", str(store),
        "--filename_template", template,
        "--pcm_type", "PCM_16",          # half the disk of float, still clean
    ]
    subprocess.run(cmd, check=True, cwd=str(root), timeout=timeout)


def _instr_from_name(name: str, base: str | None = None) -> str:
    if base and name.startswith(base + "_"):
        name = name[len(base) + 1:]
    return name.strip("_- ").lower() or name.lower()


def separate(input_wav: str, out_dir: str, model_dir: str,
             python_exe: str | None = None, timeout: int | None = None,
             chunk_s: float = 12.0, overlap_s: float = 0.75,
             max_full_s: float = 25.0) -> dict:
    """Run MSST and return {instrument: wav_path}. Chunks long inputs into small
    time-segments to keep RAM bounded (the 53-stem output array is what OOMs),
    then crossfade-stitches them. Returns every stem that isn't pure silence;
    the UI decides what to show (hide-inactive toggle)."""
    man = manifest(model_dir)
    if not man or not is_installed(model_dir):
        raise RuntimeError("MSST not installed")

    # env overrides let the user shrink chunks further (run.bat: set
    # STEMMY_MSST_CHUNK_S=20) if 30 s still runs the machine out of RAM.
    import os
    try:
        chunk_s = float(os.environ.get("STEMMY_MSST_CHUNK_S", chunk_s))
        overlap_s = float(os.environ.get("STEMMY_MSST_OVERLAP_S", overlap_s))
    except Exception:
        pass

    root, mm = _root(model_dir).resolve(), _models(model_dir).resolve()
    work = Path(out_dir).resolve()
    in_dir, store = work / "_in", work / "_out"
    for d in (in_dir, store):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)

    try:
        n_frames, sr = _info(input_wav)
    except Exception:
        n_frames, sr = 0, 44100
    duration = n_frames / sr if sr else 0

    # ---- short clip: one straight pass (no chunking needed) ----
    if duration <= 0 or duration <= max_full_s:
        dst = in_dir / (Path(input_wav).stem + ".wav")
        try:
            import soundfile as sf
            data, sr2 = _read_audio(input_wav)
            sf.write(str(dst), data, sr2)
        except Exception:
            shutil.copy(input_wav, in_dir / Path(input_wav).name)
        _run_inference(root, mm, man, in_dir, store, "{instr}", python_exe, timeout)
        produced = {}
        files = list(store.glob("*.wav")) or list(store.rglob("*.wav"))
        base = Path(input_wav).stem
        for f in sorted(files):
            produced[_instr_from_name(f.stem, base)] = str(f)
        return produced

    # ---- whole-song single pass by default (best separation) ----
    # Chunking degrades these big multi-stem models (they need the whole song in
    # view), so it's no longer automatic — it's an explicit low-RAM opt-out via
    # STEMMY_MSST_FULL=0. Default is full-length regardless of available RAM.
    force = os.environ.get("STEMMY_MSST_FULL")   # "0" -> chunk (low RAM); anything else -> full
    do_full = (force != "0")

    if do_full:
        import soundfile as sf
        dst = in_dir / (Path(input_wav).stem + ".wav")
        try:
            data, sr2 = _read_audio(input_wav)
            sf.write(str(dst), data, sr2); del data
        except Exception:
            shutil.copy(input_wav, in_dir / Path(input_wav).name)
        _run_inference(root, mm, man, in_dir, store, "{instr}", python_exe, timeout)
        produced = {}
        base = Path(input_wav).stem
        for f in sorted(list(store.glob("*.wav")) or list(store.rglob("*.wav"))):
            produced[_instr_from_name(f.stem, base)] = str(f)
        shutil.rmtree(in_dir, ignore_errors=True)
        return produced

    # ---- long input + tight RAM: slice -> one MSST call -> crossfade-stitch ----
    import numpy as np
    import soundfile as sf

    data, sr = _read_audio(input_wav)          # input is small (~tens of MB)
    N = data.shape[0]
    chunk = max(1, int(chunk_s * sr))
    ov = max(0, int(overlap_s * sr))
    step = max(1, chunk - ov)

    starts = list(range(0, N, step))
    starts = [s for s in starts if s == 0 or s < N - ov]
    seg_bounds = []
    for s in starts:
        seg_bounds.append((s, min(s + chunk, N)))
    # merge a too-short final tail into the previous segment — a 2-3 s clip can
    # make MSST emit a partial/empty output folder, which used to drop stems.
    min_seg = int(max(4.0, chunk_s * 0.34) * sr)
    if len(seg_bounds) >= 2 and (seg_bounds[-1][1] - seg_bounds[-1][0]) < min_seg:
        s_prev = seg_bounds[-2][0]
        seg_bounds[-2] = (s_prev, seg_bounds[-1][1])
        seg_bounds.pop()
    for i, (s, e) in enumerate(seg_bounds):
        sf.write(str(in_dir / f"seg_{i:03d}.wav"), data[s:e], sr, subtype="PCM_16")
    del data

    _run_inference(root, mm, man, in_dir, store, "{file_name}/{instr}",
                   python_exe, timeout)
    import gc
    gc.collect()

    # map each segment index -> its output folder + sample length (for zero-fill)
    seg_info = []  # (dir_or_None, length)
    for i, (s, e) in enumerate(seg_bounds):
        d = store / f"seg_{i:03d}"
        seg_info.append((d if d.is_dir() else None, e - s))
    if not any(d for d, _ in seg_info):
        # template ignored / nothing nested -> return whatever got written flat
        produced = {}
        for f in sorted(store.rglob("*.wav")):
            produced[_instr_from_name(f.stem)] = str(f)
        return produced
    # instruments = union across all segments (don't trust just the first)
    instruments = sorted({f.stem for d, _ in seg_info if d for f in d.glob("*.wav")})

    KEEP = 1e-4   # keep anything that isn't pure digital silence; UI slider hides quiet ones
    produced: dict[str, str] = {}

    def _read_seg(d, instr, length):
        """Read one segment's stem, or return zeros of the right length if the
        file is missing/unreadable — so one bad segment never drops a stem."""
        if d is not None:
            p = d / f"{instr}.wav"
            if p.exists():
                try:
                    seg, _ = sf.read(str(p), always_2d=True, dtype="float32")
                    return seg
                except Exception:
                    pass
        return np.zeros((length, 2), dtype="float32")

    for instr in instruments:
        out = None
        for d, length in seg_info:
            seg = _read_seg(d, instr, length)
            if out is None:
                out = seg
                continue
            if out.shape[1] != seg.shape[1]:      # guard mono/stereo mismatch
                ch = max(out.shape[1], seg.shape[1])
                if out.shape[1] < ch: out = np.repeat(out, ch, axis=1)
                if seg.shape[1] < ch: seg = np.repeat(seg, ch, axis=1)
            if ov > 0 and out.shape[0] >= ov and seg.shape[0] >= ov:
                k = min(ov, out.shape[0], seg.shape[0])
                f2 = np.linspace(0, 1, k, dtype="float32")[:, None]
                out[-k:] = out[-k:] * (1.0 - f2) + seg[:k] * f2
                out = np.concatenate([out, seg[k:]], axis=0)
            else:
                out = np.concatenate([out, seg], axis=0)
        if out is None:
            continue
        peak = float(np.abs(out).max()) if out.size else 0.0
        if peak < KEEP:
            del out
            continue
        dest = store / f"{instr}.wav"
        sf.write(str(dest), out, sr, subtype="PCM_16")
        produced[_instr_from_name(instr)] = str(dest)
        del out
        gc.collect()

    for d, _ in seg_info:
        if d:
            shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(in_dir, ignore_errors=True)
    return produced
