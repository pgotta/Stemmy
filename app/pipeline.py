"""
pipeline.py — runs a depth preset as a sequence of model passes.

Design goals:
  * Sequential passes (load one model, run it, free VRAM, next) — friendly to 8 GB.
  * Resume: completed passes recorded in project.json are skipped on re-run.
  * Optional passes (drumsep/keys/guitar) skip gracefully if a weight is missing,
    so the pipeline degrades to fewer stems instead of crashing.
  * Progress streamed out via an `emit(event)` callback (the server turns these
    into SSE messages for the processing screen).

The heavy import (`audio_separator`) is lazy so this module — and the web UI —
load fine on a machine that hasn't installed the models yet.
"""

import shutil
from pathlib import Path

from . import models, projects, analysis, msst


class ModelUnavailable(Exception):
    pass


class Pipeline:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self._sep = None
        self._loaded = None  # currently loaded model filename

    def _have_external(self, model_file: str) -> bool:
        """True if a user-supplied (non-catalog) weight is present in models_cache/.
        Matches the exact filename or the stem before its extension, so e.g.
        'drumsep.ckpt' also matches a 'drumsep_xxx.ckpt' the user dropped in."""
        from pathlib import Path as _P
        d = _P(self.model_dir)
        if not d.exists():
            return False
        if (d / model_file).exists():
            return True
        stem = _P(model_file).stem.split("_")[0].lower()  # 'drumsep', 'keys'
        for f in d.iterdir():
            if f.is_file() and stem in f.name.lower():
                return True
        return False

    def _make_metronome_stem(self, data, pdir, stem_index, sources):
        """Bake a click track aligned to the detected beats and add it as a stem
        (so it plays sample-locked with the mix and has its own solo/mute/level)."""
        a = data.get("analysis") or {}
        beats = a.get("beats") or []
        dur = a.get("duration") or data.get("duration")
        if not beats or not dur:
            return
        try:
            rel = "stems/metronome.wav"
            dest = pdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            analysis.write_click_wav(dest, dur, beats, a.get("downbeats"))
            meta = dict(models.STEM_META.get("metronome", {"name": "Metronome"}))
            stem_index["metronome"] = {
                "id": "metronome", "parent": None,
                "name": meta.get("name", "Metronome"), "type": meta.get("type", "click"),
                "clr": meta.get("clr"), "beta": True,
                "size": dest.stat().st_size,
                "url": "/stems/" + data["id"] + "/metronome.wav",
                "_rel": rel, "muted_default": True,
            }
            sources["metronome"] = str(dest)
            data["stems"] = list(stem_index.values())
            projects.save(data)
        except Exception as e:
            print("metronome stem skipped:", e)

    # ---- low level: run one separator model -------------------------------
    def _separator(self, output_dir: str):
        if self._sep is None:
            try:
                from audio_separator.separator import Separator
            except Exception as e:  # package not installed yet
                raise ModelUnavailable(f"audio-separator not installed: {e}")
            self._sep = Separator(
                output_dir=output_dir,
                model_file_dir=self.model_dir,
                use_autocast=True,           # fp16 where possible — saves VRAM
            )
        else:
            self._sep.output_dir = output_dir
        return self._sep

    def _separate(self, model_file: str, input_path: str, output_dir: str) -> list:
        """Run `model_file` on `input_path`; return list of produced file paths."""
        sep = self._separator(output_dir)
        if self._loaded != model_file:
            try:
                sep.load_model(model_filename=model_file)
            except Exception as e:
                raise ModelUnavailable(f"could not load {model_file}: {e}")
            self._loaded = model_file
        names = sep.separate(input_path)  # basenames in output_dir
        return [str(Path(output_dir) / n) for n in names]

    # ---- map a model's raw outputs onto our clean stem ids ----------------
    @staticmethod
    def _match(produced: list, raw_label: str):
        """Find the produced file whose name contains the model's stem label."""
        lab = raw_label.lower()
        for f in produced:
            if lab in Path(f).name.lower():
                return f
        return None

    # ---- the run loop -----------------------------------------------------
    def run(self, data: dict, depth: str, emit):
        preset = models.DEPTH_PRESETS[depth]
        data["depth"] = depth
        data["status"] = "separating"
        pdir = projects.project_dir(data["id"])
        stems_dir = pdir / "stems"
        work = pdir / ".work"
        work.mkdir(exist_ok=True)

        # seed pass list (preserve any completed status for resume)
        done = projects.completed_passes(data)
        data["passes"] = [{"key": p.key, "label": p.label,
                           "status": "done" if p.key in done else "queued",
                           "pct": 100 if p.key in done else 0}
                          for p in preset["passes"]]
        projects.save(data)

        # a map of available source stems on disk (id -> path)
        sources = {"mix": data["source_path"]}
        for s in data.get("stems", []):
            sources[s["id"]] = str(pdir / s["_rel"]) if s.get("_rel") else None

        stem_index = {s["id"]: s for s in data.get("stems", [])}

        for p in preset["passes"]:
            if p.key in done:
                continue
            self._set(data, p.key, "run", 5, emit)

            # analysis pass is special (tempo + beats only; key detection was
            # removed because it couldn't be made reliably accurate)
            if p.key == "analysis":
                drum_path = sources.get("drums")   # clean transients beat better
                data["analysis"] = analysis.analyze(
                    data["source_path"], beat_path=drum_path, key_path=None)
                self._make_metronome_stem(data, pdir, stem_index, sources)
                self._set(data, p.key, "done", 100, emit)
                continue

            # optional ZFTurbo MSST multi-instrument pass (Extended depth)
            if getattr(p, "msst", False):
                if not msst.is_installed(self.model_dir):
                    self._set(data, p.key, "done", 100, emit,
                              note="skipped — MSST not installed "
                                   "(see README · search 'ZFTurbo MSST install')")
                    continue
                src = sources.get(p.source)
                if not src or not Path(src).exists():
                    self._set(data, p.key, "done", 100, emit,
                              note=f"skipped — no {p.source} input")
                    continue
                self._set(data, p.key, "run", 20, emit,
                          note="running MSST full-length (slow · RAM-heavy)")
                try:
                    produced = msst.separate(src, str(work / "msst"), self.model_dir)
                except Exception as e:
                    self._set(data, p.key, "done", 100, emit,
                              note="skipped — MSST failed (likely out of RAM; "
                                   "needs ~12–16 GB free. Close apps or set "
                                   "STEMMY_MSST_FULL=0): "
                                   + str(e).splitlines()[0][:60])
                    continue
                kept = 0
                for stem_id, path in produced.items():
                    # keep anything that isn't pure silence; the studio's
                    # hide-inactive toggle decides what to show
                    if not msst.nonsilent(path, thresh=1e-4):
                        continue
                    rel = f"stems/{stem_id}.wav"
                    dest = pdir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(path, dest)
                    meta = dict(models.STEM_META.get(
                        stem_id, {"name": stem_id.replace("-", " ").replace("_", " ").title(),
                                  "type": "keys", "clr": "#5eead4"}))
                    stem_index[stem_id] = {
                        "id": stem_id, "parent": None,
                        "name": meta.get("name", stem_id),
                        "type": meta.get("type", "keys"),
                        "clr": meta.get("clr", "#5eead4"),
                        "beta": True,
                        "size": dest.stat().st_size,
                        "url": f"/stems/{data['id']}/{stem_id}.wav",
                        "_rel": rel,
                    }
                    sources[stem_id] = str(dest)
                    kept += 1
                data["stems"] = list(stem_index.values())
                self._set(data, p.key, "done", 100, emit,
                          note=f"{kept} instrument stems")
                continue

            # no model wired (e.g. experimental guitar split) -> skip cleanly
            if not p.model:
                self._set(data, p.key, "done", 100, emit, note="skipped (no model)")
                continue

            # passes whose model isn't in audio-separator's catalog (e.g. keys
            # split) skip cleanly with a clear note.
            if getattr(p, "external", False):
                self._set(data, p.key, "done", 100, emit,
                          note="skipped — no model available")
                continue

            src = sources.get(p.source)
            if not src or not Path(src).exists():
                self._set(data, p.key, "done", 100, emit, note=f"no {p.source} input")
                continue

            try:
                produced = self._separate(p.model, src, str(work))
            except ModelUnavailable as e:
                if p.optional:
                    self._set(data, p.key, "done", 100, emit, note=f"skipped: {e}")
                    continue
                data["status"] = "error"
                projects.save(data)
                emit({"type": "error", "key": p.key, "message": str(e)})
                return

            # reorganise produced files into clean stem ids
            for raw_label, stem_id in p.outputs.items():
                hit = self._match(produced, raw_label)
                if not hit:
                    continue
                rel = (f"stems/{p.parent}/{stem_id}.wav" if p.parent
                       else f"stems/{stem_id}.wav")
                dest = pdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(hit, dest)
                meta = dict(models.STEM_META.get(stem_id, {"name": stem_id}))
                entry = {
                    "id": stem_id,
                    "parent": p.parent or None,
                    "name": meta.get("name", stem_id),
                    "type": meta.get("type", "keys"),
                    "clr": meta.get("clr"),
                    "beta": meta.get("beta", False) or p.experimental,
                    "size": dest.stat().st_size,
                    "url": f"/stems/{data['id']}/{stem_id}.wav" if not p.parent
                           else f"/stems/{data['id']}/{p.parent}/{stem_id}.wav",
                    "_rel": rel,
                }
                stem_index[stem_id] = entry
                sources[stem_id] = str(dest)

            data["stems"] = list(stem_index.values())
            self._set(data, p.key, "done", 100, emit)

        # clean scratch, finalise
        shutil.rmtree(work, ignore_errors=True)
        data["status"] = "done"
        projects.save(data)
        emit({"type": "done", "project": _public(data)})

    def _set(self, data, key, status, pct, emit, note=""):
        skipped = bool(note) and note.lower().startswith("skipped")
        for p in data["passes"]:
            if p["key"] == key:
                p["status"] = status
                p["pct"] = pct
                p["skipped"] = skipped      # so a retry doesn't treat it as done
                if note:
                    p["note"] = note
        projects.save(data)
        emit({"type": "pass", "key": key, "status": status, "pct": pct, "note": note})


def _public(data: dict) -> dict:
    """Strip internal fields (_rel) before sending to the browser."""
    clean = dict(data)
    clean["stems"] = [{k: v for k, v in s.items() if not k.startswith("_")}
                      for s in data.get("stems", [])]
    return clean
