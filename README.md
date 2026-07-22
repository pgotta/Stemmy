# Stemmy

A local, GPU-accelerated **stem-separation studio for Windows**. Drop in a song or paste a YouTube link, separate it into vocals, bass, drums and sub-drums, guitar, piano, keys, and other stems, then mix, practice, identify songs, display lyrics, generate chords, tune an instrument, and export the results.

Audio separation, playback, mixing, analysis, tuner processing, and chord generation run on your machine. Shazam, lyrics, YouTube import, update checks, and model downloads use internet services only when requested.

![Stemmy studio](docs/screenshots/studio.png)

## What is new in v1.5

- Hidden app-style Windows launch with a dedicated maximized window, desktop shortcut, icon, and close-to-exit behavior.
- Background GPU protection so separation does not slow down when Stemmy is minimized or unfocused.
- Matched CUDA 12.8 stack for RTX 50-series systems: PyTorch 2.11.0, TorchVision 0.26.0, and TorchAudio 2.11.0.
- Complete install and repair workflow with source, dependency, CUDA, ONNX, startup, and shortcut verification.
- Local chromatic tuner and multi-genre Chord Creator.
- Basic Pitch ONNX MIDI/ASCII-tab export without TensorFlow.
- Improved Shazam/lyrics flow, persistent Karaoke sessions, retry-failed handling, safe package updates, Save As export, and live system monitoring.

See **[RELEASE_NOTES.md](RELEASE_NOTES.md)** for the full v1.5 change list.

## Features

- **GPU stem separation:** Quick, Standard, Deep, and optional Extended workflows.
- **Deep drum breakdown:** kick, snare, toms, hi-hat, ride, and crash.
- **Full mixer:** solo, mute, level, pan, waveforms, zoom, scrubbing, pitch, tempo, A-B looping, tap tempo, metronome, and per-stem export.
- **Karaoke:** playlist/single-link vocal removal, persistent sessions, retry failures, full-screen playback, synced lyrics, queue controls, album art, visualizers, and auto-advance.
- **Song ID and lyrics:** Shazam identification plus resilient LRCLIB searches, cleaned metadata, manual fallback, and saved-lyrics preservation.
- **Musician tools:** stable chromatic tuner, alternate tunings, local Chord Creator, MIDI transcription, and ASCII tab.
- **Safe updates:** individual update/rollback controls for `yt-dlp`, `shazamio`, and `imageio-ffmpeg` while the GPU/model stack remains protected.

## Screenshots

![Separation passes](docs/screenshots/passes.png)

![Mixing](docs/screenshots/mixing.png)

![Karaoke Mode](docs/screenshots/Karaoke1.png)

## Tested configuration

| Component | Tested value |
|---|---|
| OS | Windows 11 |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM |
| RAM | 16 GB |
| Python | 3.12.10 |
| PyTorch | 2.11.0+cu128 |
| TorchVision | 0.26.0+cu128 |
| TorchAudio | 2.11.0+cu128 |

Python 3.10–3.13 is supported; Python 3.12 is preferred. Budget roughly 15–25 GB free for the environment, model cache, and output stems.

## Windows installation

### Recommended: complete Windows release ZIP

1. Extract the complete Stemmy v1.5 Windows package into an empty writable folder.
2. Run `install_all.bat`.
3. Launch Stemmy from the desktop shortcut created by the installer.

### GitHub source clone

Executable `.bat` launchers are intentionally excluded from Git through `*.bat` in `.gitignore`. This is deliberate: launchers belong in local folders and packaged Windows release assets, not in the source repository.

**[BUILD.md](BUILD.md)** documents every launcher and links to the exact inert `.bat.txt` source under `docs/launchers/`. Save those files locally without the final `.txt` extension and use Windows CRLF line endings. Do not commit the recreated BAT files.

### Upgrade or repair

1. Close Stemmy.
2. Extract the new package over the existing folder and replace source files.
3. Keep `projects/`, `karaoke_jobs/`, and `models_cache/` when preserving work and downloaded models.
4. Run `Repair Stemmy Installation.bat` from the package or recreate it from `BUILD.md`.
5. Launch from the refreshed desktop shortcut.

The repair keeps the existing `.venv` whenever possible and avoids redownloading the large Torch wheel when only TorchVision needs repair.

## Separation depths

| Depth | Typical output |
|---|---|
| **Quick** | vocals, drums, bass, other |
| **Standard** | Quick plus guitar and piano |
| **Deep** | Standard plus detailed DrumSep and analysis |
| **Extended** | optional experimental MSST multi-instrument split |

Quick, Standard, and Deep are part of the normal setup. Extended uses a separate large model and is enabled with locally recreated `get_msst.bat`.

## Windows launcher and background GPU behavior

The desktop shortcut launches Stemmy without a visible PowerShell window. Python runs detached, logs are written under `logs/`, high-priority/high-QoS handling is applied to Stemmy and relevant child processes, and separation continues while the app is minimized or unfocused. Closing the dedicated app window requests a safe local shutdown.

## Honest limitations

- Rhythm versus lead guitar, or clean versus distorted guitar, remains unreliable with current source-separation models.
- Detailed drum splitting is more dependable than same-instrument guitar splitting.
- Extended is experimental and RAM-heavy.
- Shazam, lyrics, YouTube import, update checks, and model downloads need internet access.
- YouTube changes can temporarily break downloads; update `yt-dlp` and retry failed Karaoke tracks.

## Project layout

```text
app/                       Flask app, pipeline, tools, Karaoke, lyrics, and UI
projects/                  separated output, ignored by Git
uploads/                   source audio, ignored by Git
karaoke_jobs/              saved Karaoke sessions, ignored by Git
models_cache/              downloaded models, ignored by Git
logs/                      runtime diagnostics, ignored except .gitkeep
docs/launchers/*.bat.txt   exact inert launcher documentation
*.bat                      local/release launchers, always ignored by Git
```

## License

[MIT](LICENSE). Third-party models and bundled libraries retain their own licenses.
