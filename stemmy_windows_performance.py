"""Windows performance policy for Stemmy's long-running model jobs.

The module deliberately uses only the Python standard library.  It is imported
through ``sitecustomize.py`` so the policy is applied not only to Stemmy's Flask
server, but also to Python subprocesses used by optional separation models.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_APPLIED = False
_LAST_STATUS: dict[str, bool | str] | None = None


def _write_status(lines: list[str]) -> None:
    """Append a tiny diagnostic record without ever blocking app startup."""
    try:
        root = Path(__file__).resolve().parent
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "stemmy-performance.log"
        # Keep this diagnostic from growing forever.
        if log_path.exists() and log_path.stat().st_size > 256_000:
            log_path.write_text("", encoding="utf-8")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] pid={os.getpid()} exe={sys.executable}\n")
            for line in lines:
                fh.write(f"  {line}\n")
    except Exception:
        pass


def apply_windows_performance_policy() -> dict[str, bool | str]:
    """Opt this process out of Windows background throttling.

    Returns a status dictionary and never raises.  On non-Windows systems this
    is a harmless no-op.
    """
    global _APPLIED, _LAST_STATUS
    if _APPLIED:
        if _LAST_STATUS is not None:
            return dict(_LAST_STATUS)
        return {"applied": True, "note": "already applied"}
    _APPLIED = True

    if os.name != "nt":
        _LAST_STATUS = {"applied": False, "note": "not Windows"}
        return dict(_LAST_STATUS)

    status: dict[str, bool | str] = {}
    notes: list[str] = []

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        process = get_current_process()

        # Keep CPU-side decoding, model preparation, and GPU feeding at a stable
        # priority whether or not any console/browser window has focus.
        HIGH_PRIORITY_CLASS = 0x00000080
        set_priority_class = kernel32.SetPriorityClass
        set_priority_class.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        set_priority_class.restype = wintypes.BOOL
        priority_ok = bool(set_priority_class(process, HIGH_PRIORITY_CLASS))
        status["high_priority"] = priority_ok
        notes.append(
            "priority=HIGH" if priority_ok
            else f"priority failed error={ctypes.get_last_error()}"
        )

        # Explicit HighQoS: take control of execution-speed throttling and turn
        # it OFF.  This prevents Windows' foreground/background heuristics from
        # classifying a minimized or hidden Stemmy process as EcoQoS.
        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.DWORD),
                ("ControlMask", wintypes.DWORD),
                ("StateMask", wintypes.DWORD),
            ]

        ProcessPowerThrottling = 4
        PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        qos = PROCESS_POWER_THROTTLING_STATE(
            PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            0,  # StateMask=0 means execution-speed throttling is OFF (HighQoS).
        )

        set_process_information = getattr(kernel32, "SetProcessInformation", None)
        if set_process_information is not None:
            set_process_information.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            set_process_information.restype = wintypes.BOOL
            qos_ok = bool(
                set_process_information(
                    process,
                    ProcessPowerThrottling,
                    ctypes.byref(qos),
                    ctypes.sizeof(qos),
                )
            )
            status["high_qos"] = qos_ok
            notes.append(
                "execution throttling=OFF (HighQoS)" if qos_ok
                else f"HighQoS failed error={ctypes.get_last_error()}"
            )
        else:
            status["high_qos"] = False
            notes.append("SetProcessInformation unavailable")

        # A click inside a legacy console can enter QuickEdit selection mode and
        # suspend the attached program.  The new launcher is hidden, but clearing
        # QuickEdit here also protects users who run Stemmy visibly/manually.
        STD_INPUT_HANDLE = -10
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        get_std_handle = kernel32.GetStdHandle
        get_std_handle.argtypes = [wintypes.DWORD]
        get_std_handle.restype = wintypes.HANDLE
        get_console_mode = kernel32.GetConsoleMode
        get_console_mode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_console_mode.restype = wintypes.BOOL
        set_console_mode = kernel32.SetConsoleMode
        set_console_mode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        set_console_mode.restype = wintypes.BOOL

        console_in = get_std_handle(STD_INPUT_HANDLE & 0xFFFFFFFF)
        mode = wintypes.DWORD()
        quickedit_ok = False
        if console_in and get_console_mode(console_in, ctypes.byref(mode)):
            new_mode = (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
            quickedit_ok = bool(set_console_mode(console_in, new_mode))
        status["quickedit_disabled"] = quickedit_ok
        notes.append(
            "QuickEdit=OFF" if quickedit_ok
            else "QuickEdit not applicable (detached/no console)"
        )

        status["applied"] = bool(priority_ok or status.get("high_qos"))
    except Exception as exc:
        status["applied"] = False
        status["error"] = f"{type(exc).__name__}: {exc}"
        notes.append(status["error"])

    _LAST_STATUS = dict(status)
    _write_status(notes)
    return dict(_LAST_STATUS)
