# Stemmy v1.5 release notes

Stemmy v1.5 is the first complete Windows release package after v1.1. It combines the recent studio, Karaoke, musician-tool, installer, launcher, dependency, and background-performance fixes into one tested build.

## Highlights

- **App-style Windows launch:** hidden background server, dedicated maximized Edge/Chrome app window, desktop shortcut and icon, and safe shutdown when the app window closes.
- **Background GPU protection:** stem separation keeps using the GPU when Stemmy is minimized or loses focus, with high-priority/high-QoS handling applied to relevant Python child processes.
- **Matched RTX 50-series CUDA stack:** PyTorch 2.11.0, TorchVision 0.26.0, and TorchAudio 2.11.0 on CUDA 12.8, with exact verification and targeted repair.
- **Reliable installation and repair:** complete-source preflight, supported-Python selection, real Flask startup verification, CUDA validation, ONNX model loading, and shortcut creation only after fatal checks pass.
- **Tuner:** local chromatic tuner with Standard tuning by default, alternate tunings, A4 control, input-device selection, smoothing, and note locking.
- **Chord Creator:** local multi-genre progression generation with playback, Roman numerals, transposition, variations, diagrams, capo suggestions, copying, and favorites.
- **MIDI and ASCII tab:** Basic Pitch uses the bundled ONNX model without TensorFlow or a CPU `onnxruntime` overwrite.
- **Song identification and lyrics:** Shazam identification, broader LRCLIB matching, cleaned metadata, plain-text fallback, manual fallback, saved-lyrics preservation, and detailed logs.
- **Karaoke improvements:** persistent sessions, playable-count validation, retry-failed handling, queue controls, synced lyrics, auto-advance, album art, and visualizer/cover backgrounds.
- **Safe updates:** Settings can update `yt-dlp`, `shazamio`, and `imageio-ffmpeg` individually with `--no-deps`, compatibility checks, and rollback. Core GPU/model packages remain protected.
- **Studio refinements:** Save As export where supported, live CPU/GPU status, visualizer preservation, theme fixes, tuner/chord controls, and restored unfinished-session workflow.

## Installer and dependency fixes

- Python 3.10–3.13 is supported, with Python 3.12 preferred.
- `setuptools` stays below version 82 for older optional audio-package compatibility.
- The installer does not place CPU `onnxruntime` over `onnxruntime-gpu`.
- The actual bundled Basic Pitch ONNX model is loaded during verification.
- When Torch and TorchAudio are already correct but TorchVision is mismatched, only TorchVision is repaired, avoiding another multi-gigabyte Torch download.
- The desktop shortcut is created only after source, core app, CUDA, and startup checks pass.

## Upgrade from v1.1

1. Close Stemmy.
2. Back up `projects/` and `karaoke_jobs/` when needed.
3. Extract the v1.5 Windows package over the existing Stemmy folder and replace files.
4. Run `Repair Stemmy Installation.bat`.
5. Launch Stemmy from the refreshed desktop shortcut.

## Repository packaging policy

Executable Windows `.bat` launchers are included in the complete Windows release ZIP but are intentionally excluded from Git through `*.bat` in `.gitignore`.

`BUILD.md` documents every launcher and links to exact inert `.bat.txt` sources under `docs/launchers/`. Those text files can be saved locally without the final `.txt` extension when building from a GitHub clone. Recreated BAT files must remain local and should never be committed.

## Tested configuration

- Windows 11
- Python 3.12.10
- NVIDIA GeForce RTX 5060 Laptop GPU
- PyTorch 2.11.0+cu128
- TorchVision 0.26.0+cu128
- TorchAudio 2.11.0+cu128
- ONNX Runtime providers: TensorRT, CUDA, CPU

Quick, Standard, and Deep are included in the normal installation. Extended remains optional because it downloads a separate large MSST model and can require much more system memory.
