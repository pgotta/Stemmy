"""Background maintenance and lifecycle helpers for Stemmy.

This module intentionally stays isolated from the audio pipeline. It checks the
small set of online-facing dependencies that commonly stop working when remote
services change, reports core/GPU updates without touching them, and provides a
local-only shutdown/session API used by Stemmy's dedicated browser window.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
CACHE_FILE = LOG_DIR / "stemmy-updates.json"
UPDATE_LOG = LOG_DIR / "stemmy-update.log"

# These packages interact with services/formats that change often. They are the
# only packages Stemmy updates automatically; upgrading them does not replace the
# CUDA/PyTorch stack or separation models.
SAFE_PACKAGES = {
    "yt-dlp": "YouTube downloader",
    "shazamio": "Shazam song identification",
    "imageio-ffmpeg": "FFmpeg helper",
}

# Report these, but never update them automatically. A blind upgrade can replace
# CUDA-enabled Torch with a CPU wheel or break model compatibility.
PROTECTED_PACKAGES = {
    "torch": "PyTorch CUDA runtime",
    "torchaudio": "Torch audio runtime",
    "audio-separator": "Stem separation engine",
    "onnxruntime-gpu": "ONNX GPU runtime",
    "numpy": "Numerical runtime",
    "librosa": "Audio analysis",
    "soundfile": "Audio file I/O",
    "flask": "Local web server",
    "psutil": "System monitoring",
}


def _canon(name: str) -> str:
    return (name or "").strip().lower().replace("_", "-").replace(".", "-")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _local_request() -> bool:
    return request.remote_addr in (None, "127.0.0.1", "::1")


def _json_body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


class MaintenanceManager:
    def __init__(self, root: Path):
        self.root = root
        self.log_dir = root / "logs"
        self.cache_file = self.log_dir / "stemmy-updates.json"
        self.update_log = self.log_dir / "stemmy-update.log"
        self.lock = threading.RLock()
        self.state: dict[str, Any] = {
            "state": "idle",
            "checked_at": None,
            "updates": [],
            "git_updates": [],
            "other_outdated_count": 0,
            "safe_count": 0,
            "protected_count": 0,
            "restart_required": False,
            "message": "Update check has not run yet.",
            "error": None,
        }
        self.sessions: dict[str, dict[str, float | bool]] = {}
        self._shutdown_started = False
        self._load_cache()

    # ------------------------------------------------------------------ status
    def _load_cache(self) -> None:
        try:
            cached = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                self.state.update(cached)
                self.state["state"] = "idle"
                self.state["message"] = "Showing the previous check while Stemmy checks again."
        except Exception:
            pass

    def _save_cache(self) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            tmp.replace(self.cache_file)
        except Exception:
            pass

    def public_status(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.state))

    # -------------------------------------------------------------- update check
    def start_check(self, force: bool = False) -> bool:
        with self.lock:
            if self.state.get("state") in ("checking", "updating"):
                return False
            self.state["state"] = "checking"
            self.state["message"] = "Checking Python and optional Git dependencies in the background…"
            self.state["error"] = None
        threading.Thread(target=self._check_worker, args=(force,), daemon=True).start()
        return True

    def _pip_outdated(self) -> list[dict[str, Any]]:
        env = os.environ.copy()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PYTHONUTF8"] = "1"
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "list",
            "--outdated",
            "--format=json",
            "--disable-pip-version-check",
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(self.root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "pip update check failed").strip()
            raise RuntimeError(detail.splitlines()[-1][:300])
        data = json.loads(proc.stdout or "[]")
        return data if isinstance(data, list) else []

    @staticmethod
    def _installed(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None
        except Exception:
            return None

    def _git_status(self) -> list[dict[str, Any]]:
        git = shutil.which("git")
        models = self.root / "models_cache"
        if not git or not models.exists():
            return []

        repos: list[Path] = []
        for pattern in ("*/.git", "*/*/.git"):
            for git_dir in models.glob(pattern):
                if git_dir.is_dir():
                    repo = git_dir.parent
                    if repo not in repos:
                        repos.append(repo)

        results = []
        for repo in repos[:12]:
            item: dict[str, Any] = {
                "name": repo.name,
                "path": str(repo.relative_to(self.root)),
                "behind": 0,
                "status": "current",
            }
            try:
                origin = subprocess.run(
                    [git, "-C", str(repo), "config", "--get", "remote.origin.url"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                ).stdout.strip()
                item["origin"] = origin
                fetch = subprocess.run(
                    [git, "-C", str(repo), "fetch", "--quiet", "--prune", "origin"],
                    capture_output=True,
                    text=True,
                    timeout=35,
                )
                if fetch.returncode != 0:
                    item["status"] = "check_failed"
                    item["message"] = (fetch.stderr or "Git fetch failed").strip().splitlines()[-1][:160]
                else:
                    upstream = subprocess.run(
                        [git, "-C", str(repo), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                        capture_output=True,
                        text=True,
                        timeout=8,
                    )
                    if upstream.returncode == 0:
                        count = subprocess.run(
                            [git, "-C", str(repo), "rev-list", "--count", "HEAD..@{u}"],
                            capture_output=True,
                            text=True,
                            timeout=8,
                        )
                        behind = int((count.stdout or "0").strip() or 0) if count.returncode == 0 else 0
                        item["behind"] = behind
                        item["status"] = "update_available" if behind else "current"
                    else:
                        item["status"] = "no_upstream"
                        item["message"] = "No tracked upstream branch."
            except Exception as exc:
                item["status"] = "check_failed"
                item["message"] = f"{type(exc).__name__}: {exc}"[:180]
            results.append(item)
        return results

    def _check_worker(self, force: bool) -> None:
        try:
            raw = self._pip_outdated()
            outdated = {_canon(p.get("name", "")): p for p in raw if p.get("name")}
            updates: list[dict[str, Any]] = []

            for name, label in SAFE_PACKAGES.items():
                current = self._installed(name)
                info = outdated.get(_canon(name))
                missing = current is None
                updates.append({
                    "name": name,
                    "label": label,
                    "current": current or "not installed",
                    "latest": (info or {}).get("latest_version") or ("available" if missing else current),
                    "needs_update": bool(info or missing),
                    "safe": True,
                    "missing": missing,
                    "note": "Safe automatic update",
                })

            for name, label in PROTECTED_PACKAGES.items():
                current = self._installed(name)
                info = outdated.get(_canon(name))
                if current is None and not info:
                    continue
                updates.append({
                    "name": name,
                    "label": label,
                    "current": current or "not installed",
                    "latest": (info or {}).get("latest_version") or current,
                    "needs_update": bool(info),
                    "safe": False,
                    "missing": current is None,
                    "note": "Reported only — protected to preserve CUDA/model compatibility",
                })

            tracked = {_canon(x) for x in SAFE_PACKAGES} | {_canon(x) for x in PROTECTED_PACKAGES}
            other_count = sum(1 for p in raw if _canon(p.get("name", "")) not in tracked)
            git_updates = self._git_status()
            safe_count = sum(1 for u in updates if u["safe"] and u["needs_update"])
            protected_count = sum(1 for u in updates if not u["safe"] and u["needs_update"])
            git_count = sum(1 for g in git_updates if g.get("status") == "update_available")

            with self.lock:
                restart_required = bool(self.state.get("restart_required"))
                self.state.update({
                    "state": "ready",
                    "checked_at": _utc_now(),
                    "updates": updates,
                    "git_updates": git_updates,
                    "other_outdated_count": other_count,
                    "safe_count": safe_count,
                    "protected_count": protected_count,
                    "git_count": git_count,
                    "restart_required": restart_required,
                    "message": (
                        f"{safe_count} recommended update(s) available."
                        if safe_count
                        else "Recommended online dependencies are current."
                    ),
                    "error": None,
                })
                self._save_cache()
        except Exception as exc:
            with self.lock:
                self.state["state"] = "error"
                self.state["checked_at"] = _utc_now()
                self.state["error"] = f"{type(exc).__name__}: {exc}"
                self.state["message"] = "Could not complete the update check. Stemmy will still run normally."
                self._save_cache()

    # -------------------------------------------------------------- apply update
    def start_update(self, package: str | None = None) -> bool:
        with self.lock:
            if self.state.get("state") in ("checking", "updating"):
                return False

            requested = _canon(package or "")
            available = {
                _canon(u.get("name", "")): u
                for u in self.state.get("updates", [])
                if u.get("safe") and u.get("needs_update")
            }
            if requested:
                if requested not in {_canon(name) for name in SAFE_PACKAGES}:
                    return False
                item = available.get(requested)
                wanted = [item["name"]] if item else []
            else:
                wanted = [u["name"] for u in available.values()]

            if not wanted:
                return False
            self.state["state"] = "updating"
            self.state["updating_packages"] = wanted
            self.state["message"] = (
                f"Updating {SAFE_PACKAGES.get(wanted[0], wanted[0])}…"
                if len(wanted) == 1
                else "Updating selected recommended dependencies one at a time…"
            )
            self.state["error"] = None
            self.state["last_update_results"] = []
        threading.Thread(target=self._update_worker, args=(wanted,), daemon=True).start()
        return True

    @staticmethod
    def _smoke_command(package: str) -> list[str]:
        tests = {
            "yt-dlp": "import yt_dlp; print(yt_dlp.version.__version__)",
            "shazamio": "from shazamio import Shazam; print('shazamio import ok')",
            "imageio-ffmpeg": (
                "import imageio_ffmpeg; "
                "p=imageio_ffmpeg.get_ffmpeg_exe(); "
                "assert p; print(p)"
            ),
        }
        return [sys.executable, "-c", tests[package]]

    def _update_worker(self, packages: list[str]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PYTHONUTF8"] = "1"
        logs: list[str] = []
        results: list[dict[str, Any]] = []
        any_success = False

        for package in packages:
            previous = self._installed(package)
            label = SAFE_PACKAGES.get(package, package)
            result = {
                "name": package,
                "label": label,
                "previous": previous,
                "status": "failed",
                "message": "",
            }
            try:
                # --no-deps is intentional: these maintenance updates must never
                # silently replace NumPy, Torch, ONNX, aiohttp, or other shared
                # packages. setup.bat remains the place for environment changes.
                cmd = [
                    sys.executable, "-m", "pip", "install",
                    "--upgrade", "--no-deps", "--disable-pip-version-check", package,
                ]
                proc = subprocess.run(
                    cmd, cwd=str(self.root), env=env,
                    capture_output=True, text=True, timeout=900,
                )
                logs.append(f"\n===== {package} update =====\n"
                            + (proc.stdout or "")
                            + ("\n" + proc.stderr if proc.stderr else ""))
                if proc.returncode != 0:
                    tail = (proc.stderr or proc.stdout or "update failed").strip().splitlines()
                    raise RuntimeError((tail[-1] if tail else "update failed")[:300])

                smoke = subprocess.run(
                    self._smoke_command(package),
                    cwd=str(self.root), env=env,
                    capture_output=True, text=True, timeout=45,
                )
                logs.append(f"\n----- {package} compatibility check -----\n"
                            + (smoke.stdout or "")
                            + ("\n" + smoke.stderr if smoke.stderr else ""))
                if smoke.returncode != 0:
                    raise RuntimeError(
                        "compatibility check failed: "
                        + ((smoke.stderr or smoke.stdout or "import failed")
                           .strip().splitlines()[-1][:220])
                    )

                current = self._installed(package)
                result.update({
                    "status": "updated",
                    "current": current,
                    "message": "Installed and passed its compatibility check.",
                })
                any_success = True
            except Exception as exc:
                result["message"] = str(exc)[:300]
                # Roll back only the package itself. Dependencies were never
                # touched because updates use --no-deps.
                if previous:
                    rollback = subprocess.run(
                        [
                            sys.executable, "-m", "pip", "install",
                            "--force-reinstall", "--no-deps",
                            "--disable-pip-version-check",
                            f"{package}=={previous}",
                        ],
                        cwd=str(self.root), env=env,
                        capture_output=True, text=True, timeout=900,
                    )
                    logs.append(f"\n----- {package} rollback to {previous} -----\n"
                                + (rollback.stdout or "")
                                + ("\n" + rollback.stderr if rollback.stderr else ""))
                    if rollback.returncode == 0:
                        result["status"] = "rolled_back"
                        result["message"] += " Previous version restored."
                else:
                    # The package was newly installed. Remove it again if the
                    # compatibility check fails so Stemmy is left unchanged.
                    rollback = subprocess.run(
                        [
                            sys.executable, "-m", "pip", "uninstall", "-y",
                            "--disable-pip-version-check", package,
                        ],
                        cwd=str(self.root), env=env,
                        capture_output=True, text=True, timeout=300,
                    )
                    logs.append(f"\n----- {package} remove failed new install -----\n"
                                + (rollback.stdout or "")
                                + ("\n" + rollback.stderr if rollback.stderr else ""))
                    if rollback.returncode == 0:
                        result["status"] = "rolled_back"
                        result["message"] += " Failed new install removed."
            results.append(result)

        self.update_log.write_text(
            "".join(logs)[-300_000:], encoding="utf-8", errors="replace"
        )
        failures = [r for r in results if r["status"] != "updated"]
        with self.lock:
            self.state["last_update_results"] = results
            self.state["updating_packages"] = []
            self.state["restart_required"] = bool(
                self.state.get("restart_required") or any_success
            )
            self.state["state"] = "ready"
            self.state["error"] = (
                f"{len(failures)} update(s) failed or were rolled back."
                if failures else None
            )
            if failures and any_success:
                self.state["message"] = (
                    "Some updates installed; others were safely rolled back. "
                    "See logs/stemmy-update.log."
                )
            elif failures:
                self.state["message"] = (
                    "No changes were kept because the compatibility check failed. "
                    "See logs/stemmy-update.log."
                )
            else:
                self.state["message"] = (
                    "Selected update(s) installed and passed compatibility checks. "
                    "Close and reopen Stemmy to load them."
                )
            self._save_cache()

        time.sleep(1)
        self.start_check(force=True)

    # --------------------------------------------------------------- lifecycle
    def session_open(self, session_id: str) -> None:
        if not session_id:
            return
        now = time.monotonic()
        with self.lock:
            self.sessions[session_id] = {"last_seen": now, "closing": False, "intent": 0.0}

    def session_heartbeat(self, session_id: str) -> None:
        if not session_id:
            return
        now = time.monotonic()
        with self.lock:
            entry = self.sessions.setdefault(session_id, {"last_seen": now, "closing": False, "intent": 0.0})
            entry["last_seen"] = now
            entry["closing"] = False

    def session_close_intent(self, session_id: str) -> None:
        if not session_id:
            return
        now = time.monotonic()
        with self.lock:
            entry = self.sessions.setdefault(session_id, {"last_seen": now, "closing": True, "intent": now})
            entry["closing"] = True
            entry["intent"] = now
        threading.Timer(4.0, self._finish_close_intent, args=(session_id, now)).start()

    def _finish_close_intent(self, session_id: str, intent: float) -> None:
        with self.lock:
            entry = self.sessions.get(session_id)
            if not entry or not entry.get("closing") or float(entry.get("intent", 0)) != intent:
                return  # page reloaded/navigated and re-opened
            self.sessions.pop(session_id, None)
            now = time.monotonic()
            active = [s for s in self.sessions.values() if now - float(s.get("last_seen", 0)) < 20]
        if not active:
            self.shutdown("last Stemmy window closed")

    def shutdown_if_idle(self) -> bool:
        now = time.monotonic()
        with self.lock:
            active = [s for s in self.sessions.values() if now - float(s.get("last_seen", 0)) < 5]
        if active:
            return False
        self.shutdown("dedicated Stemmy window closed")
        return True

    def shutdown(self, reason: str = "requested") -> None:
        with self.lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with (self.log_dir / "stemmy.log").open("a", encoding="utf-8") as fh:
                fh.write(f"\n[Stemmy] shutting down: {reason}\n")
        except Exception:
            pass

        def _exit() -> None:
            time.sleep(0.75)
            os._exit(0)

        threading.Thread(target=_exit, daemon=True).start()


def register_maintenance(app: Flask) -> MaintenanceManager:
    """Register local maintenance/lifecycle routes and start a background check."""
    manager = MaintenanceManager(ROOT)

    def local_only():
        if not _local_request():
            return jsonify({"error": "local requests only"}), 403
        return None

    @app.get("/api/maintenance/status")
    def maintenance_status():
        denied = local_only()
        return denied or jsonify(manager.public_status())

    @app.post("/api/maintenance/check")
    def maintenance_check():
        denied = local_only()
        if denied:
            return denied
        started = manager.start_check(force=True)
        return jsonify({"started": started, **manager.public_status()})

    @app.post("/api/maintenance/update")
    def maintenance_update():
        denied = local_only()
        if denied:
            return denied
        package = str(_json_body().get("package") or "").strip() or None
        started = manager.start_update(package)
        return jsonify({"started": started, "package": package,
                        **manager.public_status()})

    @app.post("/api/stemmy/session/open")
    def stemmy_session_open():
        denied = local_only()
        if denied:
            return denied
        manager.session_open(str(_json_body().get("session_id") or ""))
        return jsonify({"ok": True})

    @app.post("/api/stemmy/session/heartbeat")
    def stemmy_session_heartbeat():
        denied = local_only()
        if denied:
            return denied
        manager.session_heartbeat(str(_json_body().get("session_id") or ""))
        return jsonify({"ok": True})

    @app.post("/api/stemmy/session/close-intent")
    def stemmy_session_close_intent():
        denied = local_only()
        if denied:
            return denied
        manager.session_close_intent(str(_json_body().get("session_id") or ""))
        return jsonify({"ok": True})

    @app.post("/api/stemmy/shutdown")
    def stemmy_shutdown():
        denied = local_only()
        if denied:
            return denied
        body = _json_body()
        if body.get("only_if_idle"):
            stopped = manager.shutdown_if_idle()
            return jsonify({"ok": True, "shutdown": stopped})
        manager.shutdown("Close Stemmy requested")
        return jsonify({"ok": True, "shutdown": True})

    # Delay slightly so server startup and browser launch are never blocked.
    threading.Timer(2.0, manager.start_check).start()
    return manager
