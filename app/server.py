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

    # Bring any persisted karaoke batches back into memory so a session that was
    # interrupted by a restart is still restorable (finished instrumentals live
    # on disk in their project folders).
    try:
        from . import karaoke
        karaoke.load_all()
    except Exception:
        pass

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
        from . import msst, tabs, identify
        return jsonify({
            "msst": msst.is_installed(str(MODEL_DIR)),
            "msst_model": msst.model_label(str(MODEL_DIR)),
            "tabs": tabs.is_available(),
            "identify": identify.shazam_available(),
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

    @app.post("/api/identify/<pid>")
    def api_identify(pid):
        """Identify the song (Shazam) and fetch synced lyrics (LRCLIB). Accepts an
        optional JSON body {title, artist} to skip ID and fetch lyrics directly."""
        from . import identify
        proj = projects.load(pid)
        if not proj:
            abort(404)
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        artist = (data.get("artist") or "").strip()
        identified = False

        if not title:  # try to recognise from the original audio
            if not identify.shazam_available():
                return jsonify({"error": "no_shazam",
                                "message": "Song ID isn't installed (run get_lyrics.bat). "
                                           "You can type the artist and title instead."}), 200
            src = proj.get("source_path")
            info = identify.identify_song(src) if src else None
            if not info or not info.get("title"):
                return jsonify({"error": "no_match",
                                "message": "Couldn't identify the song. "
                                           "Type the artist and title to fetch lyrics."}), 200
            title, artist = info["title"], info.get("artist") or ""
            identified = True
            # rename the project to "Artist - Title" and pull the album art
            new_name = (f"{artist} - {title}" if artist else title)
            proj["source_name"] = new_name
            img = info.get("image")
            if img:
                from . import youtube
                cover = youtube.save_thumbnail(img, projects.project_dir(pid), "cover.jpg")
                if cover:
                    proj["cover"] = cover

        dur = proj.get("duration")
        try:
            dur = int(round(float(dur))) if dur else None
        except Exception:
            dur = None
        lyr = identify.fetch_lyrics(title, artist, proj.get("album"), dur)

        proj["song"] = {"title": title, "artist": artist, "identified": identified}
        cover_url = ("/api/cover/" + pid) if proj.get("cover") else None
        song_name = proj.get("source_name")
        if lyr:
            proj["lyrics"] = {"synced": lyr["synced"], "plain": lyr["plain"]}
            projects.save(proj)
            return jsonify({"title": lyr.get("trackName") or title,
                            "artist": lyr.get("artistName") or artist,
                            "identified": identified, "song_name": song_name, "cover": cover_url,
                            "synced": lyr["synced"], "plain": lyr["plain"],
                            "has_synced": bool(lyr["synced"])})
        projects.save(proj)
        return jsonify({"title": title, "artist": artist, "identified": identified,
                        "song_name": song_name, "cover": cover_url,
                        "synced": [], "plain": "",
                        "error": "no_lyrics",
                        "message": "Found the song but no lyrics on LRCLIB."}), 200

    # ---- karaoke playlist batch --------------------------------------
    @app.post("/api/karaoke")
    def api_karaoke_start():
        from . import youtube, karaoke
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        depth = data.get("depth") or "quick"
        if not url:
            return jsonify({"error": "no link"}), 400
        try:
            job = karaoke.start(url, depth, str(MODEL_DIR), UPLOADS)
        except youtube.YouTubeError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            first = (str(e).splitlines() or ["error"])[0]
            return jsonify({"error": "couldn't start batch: " + first[:160]}), 500
        return jsonify(karaoke.public(job))

    @app.get("/api/karaoke/saved")
    def api_karaoke_saved():
        """List persisted batches (newest first) for the restore picker."""
        from . import karaoke
        return jsonify(karaoke.list_saved())

    @app.post("/api/karaoke/<job_id>/retry")
    def api_karaoke_retry(job_id):
        """Re-run every errored / interrupted track in a batch (e.g. after a
        transient YouTube 403). Returns the job so the UI can re-attach to the
        events stream."""
        from . import karaoke
        job = karaoke.retry(job_id, str(MODEL_DIR), UPLOADS)
        if not job:
            return jsonify({"error": "nothing to retry"}), 400
        return jsonify(karaoke.public(job))

    @app.get("/api/karaoke/<job_id>")
    def api_karaoke_get(job_id):
        """Return one batch's full state — used to reopen a saved session.
        Verifies each done track's instrumental still exists on disk (healing
        stale paths from the project folder); missing files are downgraded so
        the UI never claims a track is playable when it isn't."""
        from . import karaoke
        job = karaoke.get(job_id)
        if not job:
            abort(404)
        changed = False
        for it in job["items"]:
            if it.get("status") != "done":
                continue
            p = Path(it["instrumental"]) if it.get("instrumental") else None
            if p is None or not p.exists():
                healed = False
                if it.get("pid"):
                    pdir = projects.project_dir(it["pid"])
                    for cand in (pdir / "instrumental.wav", pdir / "instrumental.mp3"):
                        if cand.exists():
                            it["instrumental"] = str(cand)
                            healed = changed = True
                            break
                if not healed:
                    it["status"] = "missing"
                    it["error"] = "instrumental file not found — re-run this track"
                    changed = True
        if changed:
            karaoke._persist(job)
        return jsonify(karaoke.public(job))

    @app.post("/api/karaoke/<job_id>/delete")
    def api_karaoke_delete(job_id):
        from . import karaoke
        return jsonify({"deleted": karaoke.delete(job_id)})

    @app.get("/api/karaoke/<job_id>/events")
    def api_karaoke_events(job_id):
        from . import karaoke
        job = karaoke.get(job_id)
        if not job:
            abort(404)

        @stream_with_context
        def gen():
            yield _sse({"type": "init", **karaoke.public(job)})
            # if the job already finished before the client connected, flush state
            if job["status"] == "done":
                yield _sse({"type": "done",
                            "completed": sum(1 for i in job["items"] if i["status"] == "done"),
                            "total": len(job["items"])})
                return
            while True:
                ev = job["_q"].get()
                yield _sse(ev)
                if ev.get("type") == "done":
                    break

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/lyrics/<pid>")
    def api_lyrics(pid):
        """Return stored lyrics (+ cover url) for a project, e.g. a karaoke track."""
        proj = projects.load(pid)
        if not proj:
            abort(404)
        lyr = proj.get("lyrics") or {}
        return jsonify({"synced": lyr.get("synced") or [],
                        "plain": lyr.get("plain") or "",
                        "title": proj.get("source_name"),
                        "cover": ("/api/cover/" + pid) if proj.get("cover") else None})

    @app.get("/api/karaoke/<job_id>/track/<int:n>")
    def api_karaoke_track(job_id, n):
        from . import karaoke
        job = karaoke.get(job_id)
        if not job:
            abort(404)
        it = next((i for i in job["items"] if i["n"] == n), None)
        if not it:
            abort(404)
        # 1) the path recorded when the batch ran
        p = Path(it["instrumental"]) if it.get("instrumental") else None
        # 2) fallback: the track's own project folder — covers a moved install
        #    or a restored session whose absolute path no longer resolves
        if (p is None or not p.exists()) and it.get("pid"):
            pdir = projects.project_dir(it["pid"])
            for cand in (pdir / "instrumental.wav", pdir / "instrumental.mp3"):
                if cand.exists():
                    p = cand
                    it["instrumental"] = str(cand)   # heal the stored path
                    karaoke._persist(job)
                    break
        if p is None or not p.exists():
            abort(404)
        return send_file(str(p), conditional=True)

    @app.get("/api/karaoke/<job_id>/download")
    def api_karaoke_download(job_id):
        from . import karaoke
        job = karaoke.get(job_id)
        if not job:
            abort(404)
        done = [it for it in job["items"] if it["status"] == "done" and it.get("instrumental")]
        if not done:
            return jsonify({"error": "no finished instrumentals yet"}), 400
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for it in done:
                wav = Path(it["instrumental"])
                safe = "".join(c for c in (it.get("title") or "track")
                               if c.isalnum() or c in " -_").strip() or "track"
                base = f"{it['n']+1:02d} - {safe} (instrumental)"
                if wav.exists():
                    z.write(str(wav), arcname=base + ".wav")
                mp3 = wav.with_suffix(".mp3")
                if mp3.exists():
                    z.write(str(mp3), arcname=base + ".mp3")
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name="karaoke_instrumentals.zip")

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

    @app.post("/api/tab/<pid>/<stem_id>")
    def api_tab(pid, stem_id):
        """Transcribe one isolated stem to MIDI + a beta ASCII tab (on demand)."""
        from . import tabs
        if not tabs.is_available():
            return jsonify({"error": "Tab/MIDI export isn't installed. Run get_tabs.bat "
                                     "to enable audio-to-MIDI transcription."}), 400
        proj = projects.load(pid)
        if not proj:
            abort(404)
        stem = next((s for s in proj.get("stems", []) if s.get("id") == stem_id), None)
        if not stem:
            return jsonify({"error": "unknown stem"}), 404

        pdir = projects.project_dir(pid).resolve()
        rel = stem.get("_rel") or ("stems/" + stem_id + ".wav")
        wav = (pdir / rel).resolve()
        if pdir not in wav.parents or not wav.exists():
            return jsonify({"error": "stem audio not found"}), 404

        sid = "".join(c for c in stem_id if c.isalnum() or c in "-_") or "stem"
        stype = (stem.get("type") or "").lower()
        instrument = "bass" if ("bass" in stem_id.lower() or stype == "bass") else "guitar"
        is_drum = stype in ("drums", "kit", "percussion") or stem_id.lower() in (
            "drums", "kick", "snare", "hihat", "hh", "toms", "ride", "crash", "cymbals")

        midi_rel = "stems/" + sid + ".mid"
        midi_path = pdir / midi_rel
        try:
            n = tabs.stem_to_midi(str(wav), str(midi_path))
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            first = (str(e).splitlines() or ["error"])[0]
            return jsonify({"error": "transcription failed: " + first[:160]}), 500

        if is_drum:
            tab_text = ("# Drum stems don't map to string tab (they're unpitched).\n"
                        "# The MIDI export above captures the hits — open it in a DAW "
                        "with a drum map.\n")
        else:
            try:
                tab_text = tabs.midi_to_tab(str(midi_path), instrument)
            except Exception as e:
                tab_text = "(tab render failed: " + str(e)[:120] + ")"

        return jsonify({
            "stem": stem_id, "instrument": instrument, "notes": n,
            "midi_url": "/stems/" + pid + "/" + sid + ".mid",
            "tab": tab_text,
        })

    @app.get("/api/download/<pid>")
    def download(pid):
        proj = projects.load(pid)
        if not proj:
            abort(404)
        wanted = request.args.get("stems")
        want = set(wanted.split(",")) if wanted else None
        stems_dir = projects.project_dir(pid) / "stems"

        mem = io.BytesIO()
        added_mid = 0
        with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
            for s in proj.get("stems", []):
                if want is not None and s["id"] not in want:
                    continue
                rel = s.get("_rel", f"stems/{s['id']}.wav")
                fp = projects.project_dir(pid) / rel
                if fp.exists():
                    z.write(fp, arcname=Path(rel).name)
                # include a previously-transcribed MIDI for this stem, if present
                sid = "".join(c for c in s["id"] if c.isalnum() or c in "-_")
                mid = stems_dir / (sid + ".mid")
                if mid.exists():
                    z.write(str(mid), arcname=sid + ".mid")
                    added_mid += 1
            # add a combined full mix (all stems minus the click) as WAV + MP3,
            # unless the user asked for a specific subset of stems
            if want is None:
                try:
                    from . import mixdown
                    base = Path(proj["source_name"]).stem or "mix"
                    for f in mixdown.build_combined(proj, drop_ids={"metronome"},
                                                    drop_types={"click"}, stem="full_mix"):
                        z.write(str(f), arcname=base + " (full mix)" + f.suffix)
                except Exception:
                    pass
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
