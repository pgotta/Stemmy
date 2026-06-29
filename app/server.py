"""
server.py — Stemmy's local Flask backend (default http://127.0.0.1:5002).

Routes
  GET  /                       studio UI (latest project injected, else design mock)
  GET  /studio/<id>            studio UI for a specific project
  GET  /api/projects           list known projects
  POST /api/upload             save an audio file, create a project
  GET  /api/separate/<id>      run the pipeline, stream progress as SSE
  GET  /api/project/<id>       project JSON
  GET  /stems/<id>/<path:sub>  stream a separated stem (range-enabled for seeking)
  GET  /api/download/<id>      zip selected stems (?stems=a,b,c) or all

Heavy deps (audio-separator, librosa, soundfile) are imported lazily inside the
pipeline/analysis modules, so the server boots and serves the UI instantly even
before the model stack is installed.
"""

import io
import json
import queue
import shutil
import threading
import zipfile
from pathlib import Path

from flask import (Flask, Response, request, jsonify, send_file,
                   stream_with_context, abort)

from . import projects, models
from .pipeline import Pipeline

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
UPLOADS = ROOT / "uploads"
MODEL_DIR = ROOT / "models_cache"
UPLOADS.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)

ALLOWED = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff", ".aif"}
TEMPLATE = APP_DIR / "templates" / "index.html"


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024  # 512 MB uploads

    # ---- UI -----------------------------------------------------------
    def render(project=None, view="home"):
        html = TEMPLATE.read_text(encoding="utf-8")
        payload = "null"
        if project is not None:
            payload = json.dumps(_public(project))
        inject = f"window.__PROJECT__={payload};window.__VIEW__={json.dumps(view)};"
        html = html.replace("/*__PROJECT_INJECT__*/", inject, 1)
        return Response(html, content_type="text/html; charset=utf-8")

    @app.get("/")
    def index():
        latest = projects.list_all()
        proj = projects.load(latest[0]["id"]) if latest else None
        # only inject a project that actually has stems (for the resume button)
        if not (proj and proj.get("stems")):
            proj = None
        return render(proj, view="home")

    @app.get("/studio/<pid>")
    def studio(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        return render(proj, view="studio")

    # ---- project management ------------------------------------------
    @app.get("/api/projects")
    def api_projects():
        return jsonify(projects.list_all())

    @app.post("/api/projects/clear")
    def api_projects_clear():
        return jsonify({"cleared": projects.clear_all()})

    @app.get("/api/capabilities")
    def api_capabilities():
        from . import msst
        return jsonify({
            "msst": msst.is_installed(str(MODEL_DIR)),
            "msst_model": msst.model_label(str(MODEL_DIR)),
        })

    @app.get("/api/project/<pid>")
    def api_project(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        return jsonify(_public(proj))

    @app.post("/api/upload")
    def api_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"error": "no file"}), 400
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED:
            return jsonify({"error": f"unsupported format {ext}"}), 400

        pid = projects.new_id(f.filename)
        dest = projects.project_dir(pid)
        dest.mkdir(parents=True, exist_ok=True)
        src_path = dest / ("source" + ext)
        f.save(src_path)

        sr, bits, dur = _probe(src_path)
        proj = projects.create(pid, f.filename, str(src_path),
                               sample_rate=sr, bit_depth=bits, duration=dur)
        return jsonify({"id": pid, "project": _public(proj)})

    @app.post("/api/youtube")
    def api_youtube():
        """Fetch audio from a YouTube (or other yt-dlp-supported) link and create
        a project from it, exactly like an uploaded file."""
        from . import youtube
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "no link"}), 400
        try:
            title, audio_path, thumb_url = youtube.fetch_audio(url, UPLOADS)
        except youtube.YouTubeError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:  # unexpected — still report cleanly
            first = (str(e).splitlines() or ["error"])[0]
            return jsonify({"error": "fetch failed: " + first[:160]}), 500

        ext = audio_path.suffix.lower()
        if ext not in ALLOWED:
            ext = ".wav"
        fname = (title or "youtube-audio") + ext
        pid = projects.new_id(fname)
        dest = projects.project_dir(pid)
        dest.mkdir(parents=True, exist_ok=True)
        src_path = dest / ("source" + ext)
        shutil.move(str(audio_path), str(src_path))

        sr, bits, dur = _probe(src_path)
        proj = projects.create(pid, fname, str(src_path),
                               sample_rate=sr, bit_depth=bits, duration=dur)
        proj["source_kind"] = "youtube"
        proj["source_url"] = url
        cover = youtube.save_thumbnail(thumb_url, dest)   # best-effort
        if cover:
            proj["cover"] = cover
        projects.save(proj)
        return jsonify({"id": pid, "project": _public(proj), "title": title})

    # ---- separation (SSE) --------------------------------------------
    @app.get("/api/separate/<pid>")
    def api_separate(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        depth = request.args.get("depth", "deep")
        if depth not in models.DEPTH_PRESETS:
            return jsonify({"error": "bad depth"}), 400

        q: "queue.Queue" = queue.Queue()

        def emit(ev):
            q.put(ev)

        def work():
            try:
                Pipeline(str(MODEL_DIR)).run(proj, depth, emit)
            except Exception as e:  # never leave the stream hanging
                emit({"type": "error", "message": str(e)})
            finally:
                emit({"type": "_end"})

        threading.Thread(target=work, daemon=True).start()

        @stream_with_context
        def gen():
            # let the client render the pass list immediately
            yield _sse({"type": "init", "depth": depth,
                        "passes": [{"key": p.key, "label": p.label,
                                    "detail": p.detail,
                                    "experimental": p.experimental}
                                   for p in models.DEPTH_PRESETS[depth]["passes"]]})
            while True:
                ev = q.get()
                if ev.get("type") == "_end":
                    break
                yield _sse(ev)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # ---- stem + download serving -------------------------------------
    @app.get("/stems/<pid>/<path:sub>")
    def stems(pid, sub):
        base = (projects.project_dir(pid) / "stems").resolve()
        target = (base / sub).resolve()
        if base not in target.parents and target != base:
            abort(403)  # path-traversal guard
        if not target.exists():
            abort(404)
        return send_file(target, conditional=True)  # range support for seeking

    @app.get("/api/cover/<pid>")
    def cover(pid):
        proj = projects.load(pid)
        cov = proj.get("cover") if proj else None
        if not isinstance(cov, str) or not cov:
            abort(404)
        pdir = projects.project_dir(pid).resolve()
        target = (pdir / cov).resolve()
        if pdir not in target.parents or not target.exists():
            abort(404)
        return send_file(target, conditional=True)

    @app.get("/api/download/<pid>")
    def download(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        wanted = request.args.get("stems")
        want = set(wanted.split(",")) if wanted else None
        stems_dir = projects.project_dir(pid) / "stems"

        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            for s in proj.get("stems", []):
                if want is not None and s["id"] not in want:
                    continue
                rel = s.get("_rel", f"stems/{s['id']}.wav")
                fp = projects.project_dir(pid) / rel
                if fp.exists():
                    z.write(fp, arcname=Path(rel).name)
        mem.seek(0)
        name = Path(proj["source_name"]).stem + "_stems.zip"
        return send_file(mem, mimetype="application/zip",
                         as_attachment=True, download_name=name)

    # ---- live GPU meter ----------------------------------------------
    @app.get("/api/gpu")
    def api_gpu():
        return jsonify(_gpu_info())

    # ---- tempo map (downloadable click track) ------------------------
    @app.get("/api/tempomap/<pid>")
    def tempomap(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        a = proj.get("analysis") or {}
        bpm = a.get("bpm")
        dur = a.get("duration") or proj.get("duration")
        downbeats = a.get("downbeats") or []
        beats = a.get("beats") or []
        if not bpm:  # nothing stored — analyze the source on demand
            try:
                from . import analysis as anz
                res = anz.analyze(proj.get("source_path", ""))
                bpm = res.get("bpm"); dur = res.get("duration") or dur
                downbeats = res.get("downbeats") or []
                beats = res.get("beats") or []
            except Exception:
                pass
        if not bpm or not dur:
            return jsonify({"error": "no tempo could be determined"}), 400
        try:
            data = _click_track(float(bpm), float(dur), downbeats, beats)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        name = Path(proj["source_name"]).stem + "_tempo.wav"
        return send_file(io.BytesIO(data), mimetype="audio/wav",
                         as_attachment=True, download_name=name)

    return app


# ---- helpers ----------------------------------------------------------
def _gpu_info() -> dict:
    """Best-effort live GPU memory + utilisation and CPU %. Safe without deps."""
    info = {"available": False, "cpu": _cpu_percent()}
    try:
        import torch
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            total = p.total_memory
            try:
                free, total = torch.cuda.mem_get_info(0)   # device-wide
                used = total - free
            except Exception:
                used = torch.cuda.memory_reserved(0)
            info.update({
                "available": True, "name": p.name, "cuda": torch.version.cuda,
                "total_gb": round(total / 1073741824, 1),
                "used_gb": round(used / 1073741824, 2),
                "util": _gpu_util(),
            })
    except Exception:
        pass
    return info


def _cpu_percent():
    # Preferred: psutil (cross-platform, accurate).
    try:
        import psutil
        return round(psutil.cpu_percent(interval=None))
    except Exception:
        pass
    # Fallback without psutil (Windows): wmic, then PowerShell.
    import subprocess
    try:
        out = subprocess.run(["wmic", "cpu", "get", "loadpercentage", "/value"],
                             capture_output=True, text=True, timeout=2)
        for line in out.stdout.splitlines():
            if "LoadPercentage=" in line:
                return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
            capture_output=True, text=True, timeout=3)
        v = out.stdout.strip()
        if v:
            return int(float(v))
    except Exception:
        pass
    return None


def _gpu_util():
    """GPU core utilisation % via nvidia-smi (None if unavailable)."""
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2)
        if out.returncode == 0:
            return int(out.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _click_track(bpm: float, dur: float, downbeats=None, beats=None) -> bytes:
    """Synthesize a mono 44.1k click track. If `beats` (detected onsets) are given,
    click on those (phase-correct, tempo-following); otherwise fall back to a fixed
    grid from bpm. Downbeats are accented (higher + louder). Returns WAV bytes."""
    import math, struct, wave
    sr = 44100
    n = int(dur * sr)
    buf = bytearray(2 * n)  # 16-bit mono, zero-filled
    down = set(round(float(d), 2) for d in (downbeats or []))

    def blip(at_sec, freq, amp):
        start = int(at_sec * sr)
        length = int(0.045 * sr)
        for i in range(length):
            idx = start + i
            if idx >= n or idx < 0:
                break
            env = math.exp(-i / (0.012 * sr))
            s = int(amp * env * math.sin(2 * math.pi * freq * i / sr) * 32767)
            struct.pack_into("<h", buf, idx * 2, max(-32768, min(32767, s)))

    if beats:
        for bt in beats:
            accent = round(float(bt), 2) in down
            blip(float(bt), 1500 if accent else 1000, 0.9 if accent else 0.55)
    else:
        beat = 60.0 / bpm
        t = 0.0
        k = 0
        while t < dur:
            blip(t, 1500 if k % 4 == 0 else 1000, 0.9 if k % 4 == 0 else 0.55)
            t += beat
            k += 1

    with io.BytesIO() as mem:
        with wave.open(mem, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(bytes(buf))
        return mem.getvalue()


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _public(data: dict) -> dict:
    clean = dict(data)
    clean["stems"] = [{k: v for k, v in s.items() if not k.startswith("_")}
                      for s in data.get("stems", [])]
    return clean


def _probe(path: Path):
    """Best-effort sample rate / bit depth / duration via soundfile."""
    try:
        import soundfile as sf
        info = sf.info(str(path))
        sr = info.samplerate
        dur = round(info.frames / sr, 2) if sr else None
        bits = {"PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
                "FLOAT": 32}.get(info.subtype, None)
        return sr, bits, dur
    except Exception:
        return None, None, None


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5002, debug=True, threaded=True)
