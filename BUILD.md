# Stemmy Windows setup and launch guide

This document describes the **current Windows workflow** used by the packaged/cumulative Stemmy build.

The repository contains the application source. Some Windows convenience launchers are intentionally kept out of normal Git tracking because they are machine-oriented wrappers. They are included in the downloadable Windows package/overlay.

## Recommended workflow

### First installation

Use one of these:

- `install_all.bat` — installs the core environment plus optional song ID, MIDI/tab support, and Extended separation.
- `setup.bat` — installs the core environment only.

Use Python **3.10–3.13**; Python 3.12 is the most thoroughly tested.

After setup completes, run:

```text
run.bat
```

### Applying a source overlay/update

When a ZIP contains updated Stemmy source files:

1. Close Stemmy.
2. Extract the ZIP over the existing Stemmy folder.
3. Choose **Replace files**.
4. Run `run.bat`.

Do **not** run setup again unless the update explicitly says dependencies changed, the `.venv` was deleted, or Stemmy reports a missing package.

### Everyday launch

Run `run.bat` or use the desktop shortcut created by `Create Stemmy Shortcut.bat`.

The launcher:

- Activates `.venv`.
- Starts Python without a visible long-running console.
- Redirects output to `logs/`.
- Applies Windows process priority/high-QoS handling to Stemmy Python processes.
- Waits for the local server to respond.
- Opens `http://127.0.0.1:5002` in an Edge/Chrome app window when possible.
- Monitors that window and stops the server when it closes.

## App-style desktop shortcut

Run this once:

```text
Create Stemmy Shortcut.bat
```

It creates `Stemmy.lnk` on the desktop with `stemmy.ico`.

The shortcut launches `stemmy_launcher.vbs`, which starts `run.bat` without showing a command window. This is the preferred app-like entry point.

A `.bat` file cannot embed a Windows icon directly; the `.lnk` shortcut is the clean Windows-native solution without wrapping Stemmy in a third-party executable packager.

## Closing Stemmy

Normal shutdown options:

1. Close the dedicated Stemmy app window with **X**.
2. Choose **Settings -> Close Stemmy**.

`stop.bat` remains an emergency fallback if the browser or launcher was force-killed and port 5002 is still occupied.

Your projects and finished Karaoke sessions remain saved on disk.

## Current launcher files

| File | Purpose |
|---|---|
| `run.bat` | Main Windows launcher |
| `run_stemmy.py` | Starts the Flask application |
| `stemmy_window.ps1` | Opens and watches the dedicated browser app window |
| `stemmy_windows_performance.py` | Applies priority/high-QoS protection to Stemmy Python processes |
| `sitecustomize.py` | Early Python startup safeguards |
| `stemmy_launcher.vbs` | Hidden entry point used by the desktop shortcut |
| `stemmy.ico` | Multi-resolution Windows icon |
| `Create Stemmy Shortcut.bat` | One-click shortcut creator |
| `create_stemmy_shortcut.ps1` | Creates and configures `Stemmy.lnk` |
| `stop.bat` | Emergency port/process shutdown |

## Background GPU protection

Some Windows laptops reduce GPU work when the process owning a console is minimized or loses focus. Earlier launchers attempted only to raise process priority, which was not enough.

The current launcher instead:

- Detaches Stemmy from the console.
- Marks Stemmy Python processes as high priority/high QoS.
- Re-applies the policy to relevant child Python processes.
- Disables console-specific pause hazards.
- Sends output to log files rather than relying on an interactive terminal.

This means stem separation should continue at full speed while Stemmy is in the background or minimized.

The optional legacy `fix_gpu.bat` power-plan change is generally no longer required for the current packaged launcher, but it can remain useful for unusual OEM/driver power policies.

## Background update checker

On startup, Stemmy performs a quiet update-status check. Open:

```text
Settings -> Updates
```

Safe internet-facing helper packages can be updated individually:

- `yt-dlp`
- `shazamio`
- `imageio-ffmpeg`

Each update:

1. Changes only the selected package.
2. Uses `--no-deps` so shared numerical/GPU dependencies are not replaced.
3. Runs a compatibility/import test.
4. Rolls back to the previous version when the compatibility test fails.

Protected/report-only packages include:

- PyTorch and CUDA runtime packages
- `audio-separator`
- ONNX runtime/model-stack components
- NumPy and other numerical packages

Update protected packages manually and deliberately. A newer version is not automatically safer for the installed CUDA/model combination.

## Manual installation from a raw clone

The package launchers are optional. Stemmy can run directly from a terminal.

```bat
py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

rem Example for RTX 50-series / CUDA 12.8:
pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128

python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
python run_stemmy.py
```

Then open:

```text
http://127.0.0.1:5002
```

Install the PyTorch CUDA build **after** `requirements.txt`. `audio-separator` or another dependency may otherwise replace it with a CPU-only wheel.

## Optional components

### Song ID

```bat
call .venv\Scripts\activate.bat
pip install shazamio
```

Python 3.13 may also require:

```bat
pip install audioop-lts
```

Lyrics themselves are fetched over HTTPS; ShazamIO is used for audio identification.

### MIDI/tab export

Use `get_tabs.bat`, or install Basic Pitch and the ONNX dependencies described by that script. Basic Pitch dependency metadata can attempt to pull an unsuitable TensorFlow build, so the packaged installer intentionally installs only the runtime pieces Stemmy uses.

### Extended separation

Use `get_msst.bat` to install the optional ZFTurbo MSST code, configuration, and checkpoint. The model is large and much more demanding on system RAM than Quick, Standard, or Deep.

## Logs

| File | Contents |
|---|---|
| `logs/stemmy.log` | Normal server output |
| `logs/stemmy-error.log` | Python/server errors |
| `logs/stemmy-performance.log` | Windows performance-policy activity |
| `logs/stemmy-lyrics.log` | Shazam/LRCLIB lookup paths and failures |
| `logs/stemmy-update.log` | Package update and rollback output |

When reporting a startup, lyrics, update, or performance problem, include the relevant log rather than only a screenshot.

## Troubleshooting

### Stemmy does not open a browser

Check `logs/stemmy-error.log`.

A previous launcher could crash before browser startup when Windows selected a legacy `cp1252` output encoding and Python printed a Unicode arrow. The current `run_stemmy.py` configures UTF-8-safe output and uses an ASCII startup line.

Also check whether another process is already listening on port 5002:

```bat
netstat -ano | findstr :5002
```

Use `stop.bat` to clear an abandoned Stemmy process.

### GPU is detected but utilization drops in the background

Confirm you launched with the current `run.bat` or desktop shortcut, not directly with an old PowerShell/Python command.

Review:

```text
logs/stemmy-performance.log
```

Then confirm CUDA:

```bat
call .venv\Scripts\activate.bat
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```

### Song identifies but lyrics do not appear

Review:

```text
logs/stemmy-lyrics.log
```

The current lyric client records exact lookup, broad search, cleaned metadata variants, provider errors, and fallback attempts.

Confirm ShazamIO imports:

```bat
call .venv\Scripts\activate.bat
python -c "import shazamio; print('ShazamIO OK')"
```

Manual title/artist entry remains available when no provider has a matching lyric record.

### YouTube downloads fail or return 403

Update only `yt-dlp` under **Settings -> Updates**, or run:

```bat
call .venv\Scripts\activate.bat
python -m pip install --upgrade yt-dlp
```

Restart Stemmy and use **Retry failed** in Karaoke so successful tracks are not repeated.

### Closing the browser does not stop Stemmy

The automatic shutdown behavior depends on the dedicated app window opened by the current launcher. A normal browser tab, a browser crash, or a manually opened URL may not give the launcher a reliable close event.

Use **Settings -> Close Stemmy** or `stop.bat`.

## Security and scope

Stemmy binds to `127.0.0.1` for local single-user use. Do not expose the Flask development server directly to the public internet.

Audio separation and model inference run locally. YouTube downloads, Shazam identification, lyrics, and dependency checks contact their respective internet services.
