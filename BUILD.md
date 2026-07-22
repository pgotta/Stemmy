# Stemmy v1.5 Windows build and launcher guide

Stemmy's Windows `.bat` launchers are **intentionally excluded from Git history** and matched by `*.bat` in `.gitignore`. The complete Windows release ZIP contains ready-to-run copies. This guide documents what every launcher does and links to its exact inert plain-text source so a GitHub clone can recreate it locally.

Do not commit recreated `.bat` files. They belong only in local working folders and packaged release assets.

## Installation

### Complete Windows release ZIP

1. Extract the complete Stemmy v1.5 Windows ZIP into a writable folder.
2. Run `install_all.bat`.
3. Launch Stemmy from the desktop shortcut created by the installer.

### GitHub source clone

1. Clone or download the repository.
2. Open the launcher source links below.
3. Save each source using the filename in the first column, removing only the final `.txt` extension.
4. Save with **Windows CRLF** line endings.
5. Run `install_all.bat`.

`setup.bat` is a convenience alias for the same installer.

## Exact launcher sources

The files under `docs/launchers/` are plain-text documentation, not executable BAT files.

| Recreate locally as | Exact source | Purpose |
|---|---|---|
| `install_all.bat` | [`docs/launchers/install_all.bat.txt`](docs/launchers/install_all.bat.txt) | Complete install and dependency repair |
| `setup.bat` | [`docs/launchers/setup.bat.txt`](docs/launchers/setup.bat.txt) | Alias for the complete installer |
| `Repair Stemmy Installation.bat` | [`docs/launchers/Repair Stemmy Installation.bat.txt`](docs/launchers/Repair%20Stemmy%20Installation.bat.txt) | Upgrade and repair entry point |
| `run.bat` | [`docs/launchers/run.bat.txt`](docs/launchers/run.bat.txt) | Hidden server plus maximized app window |
| `stop.bat` | [`docs/launchers/stop.bat.txt`](docs/launchers/stop.bat.txt) | Emergency shutdown |
| `Create Stemmy Shortcut.bat` | [`docs/launchers/Create Stemmy Shortcut.bat.txt`](docs/launchers/Create%20Stemmy%20Shortcut.bat.txt) | Recreates the desktop shortcut |
| `Check Background GPU Fix.bat` | [`docs/launchers/Check Background GPU Fix.bat.txt`](docs/launchers/Check%20Background%20GPU%20Fix.bat.txt) | Verifies high-priority/high-QoS handling |
| `get_msst.bat` | [`docs/launchers/get_msst.bat.txt`](docs/launchers/get_msst.bat.txt) | Downloads optional Extended MSST support |

The PowerShell, VBS, Python, icon, and application files referenced by these launchers remain tracked. Only executable `.bat` files are excluded by policy.

## Upgrade or repair

1. Close Stemmy.
2. Replace the source files with the newer release.
3. Keep `projects/`, `karaoke_jobs/`, and `models_cache/` when preserving work or downloaded models.
4. Run `Repair Stemmy Installation.bat` from the Windows package or recreate it from the documented source above.
5. Start from the refreshed desktop shortcut.

The installer repairs the existing `.venv` whenever possible. Delete `.venv` only when intentionally rebuilding the Python environment.

## What `install_all.bat` verifies

1. Complete Stemmy source exists before installation starts.
2. Python 3.10–3.13 is used, preferring Python 3.12.
3. `.venv` is created or repaired with pip, wheel, and `setuptools<82`.
4. Core Flask, separation, analysis, YouTube, and FFmpeg dependencies install correctly.
5. ShazamIO imports successfully.
6. The tested CUDA stack is present: PyTorch 2.11.0, TorchVision 0.26.0, and TorchAudio 2.11.0 from CUDA 12.8.
7. Only TorchVision is repaired when Torch and TorchAudio are already correct, avoiding another multi-gigabyte Torch download.
8. Basic Pitch uses Stemmy's bundled ONNX model without TensorFlow dependencies or a CPU `onnxruntime` overwrite.
9. The real Flask application startup/import check passes.
10. Background GPU protection is active.
11. The desktop shortcut is created only after fatal core checks pass.

CoreML, TFLite, and TensorFlow warnings are harmless when the final ONNX model test passes.

## Manual tested installation

```bat
py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel "setuptools<82"
python -m pip install -r requirements.txt
python -m pip install shazamio "pretty_midi>=0.2.9" "resampy>=0.4,<0.5" "mir_eval>=0.6" "importlib-resources>=5"
python -m pip install --force-reinstall --no-deps "basic-pitch==0.4.0"
python -m pip install --force-reinstall --no-cache-dir "torch==2.11.0" "torchvision==0.26.0" "torchaudio==2.11.0" --index-url https://download.pytorch.org/whl/cu128
python run_stemmy.py
```

Open `http://127.0.0.1:5002`. Other GPU generations may need a different CUDA package index.

## Runtime and shutdown

The v1.5 launcher starts Python hidden and detached, writes output to `logs/`, applies high-priority/high-QoS handling to Stemmy and relevant Python child processes, and opens a maximized dedicated Edge/Chrome app window.

Normal shutdown options are closing the dedicated app window, choosing **Settings → Close Stemmy**, or using locally recreated `stop.bat` as an emergency fallback.

## Optional Extended/MSST setup

Recreate and run `get_msst.bat` only after the main installer succeeds. It downloads ZFTurbo's MSST inference code and a roughly 2 GB 53-stem checkpoint under `models_cache/`. Quick, Standard, and Deep do not require it.

## Logs

| File | Contents |
|---|---|
| `logs/stemmy.log` | Normal server output |
| `logs/stemmy-error.log` | Python and Flask errors |
| `logs/stemmy-performance.log` | Windows performance-policy activity |
| `logs/stemmy-lyrics.log` | Shazam and lyric-provider details |
| `logs/stemmy-update.log` | Package update and rollback output |

## Troubleshooting

Check `logs/stemmy-error.log` when Stemmy does not open. For CUDA verification:

```bat
call .venv\Scripts\activate.bat
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

For the tested RTX 5060 setup, this should report PyTorch `2.11.0+cu128`, CUDA `True`, and the NVIDIA GPU name.

When GPU use falls after minimizing, launch through the v1.5 shortcut or recreated `run.bat`, review `logs/stemmy-performance.log`, and recreate/run `Check Background GPU Fix.bat`.

When MIDI/Tab is unavailable, recreate/run `Repair Stemmy Installation.bat`. A successful check reports `MIDI / Tab ONNX runtime ready` and lists CUDA among ONNX providers.

For YouTube 403 errors, open **Settings → Updates**, update `yt-dlp`, restart Stemmy, and use **Retry failed** in Karaoke.

Stemmy binds to `127.0.0.1` for local single-user use. Do not expose the Flask development server directly to the public internet.
