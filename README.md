# Stemmy

A local, GPU-accelerated **stem-separation studio** for Windows. Drop in a song or paste a YouTube link, separate it into vocals, bass, drums and sub-drums, guitar, piano, keys, and other stems, then mix, practice, identify songs, display lyrics, generate chords, tune an instrument, and export the results.

Everything runs on your own machine. Audio separation, playback, mixing, analysis, tuner processing, and chord generation stay local.

![Stemmy studio](docs/screenshots/studio.png)

## Current feature set

- **GPU stem separation:** Quick, Standard, Deep, and optional Extended workflows.
- **Deep drum breakdown:** kick, snare, toms, hi-hat, ride, and crash nested beneath the drum stem.
- **Full local mixer:** solo, mute, volume, pan, real waveforms, zoom, scrubbing, pitch shift, tempo change, and per-stem downloads.
- **Karaoke mode:** download a playlist, remove vocals, save sessions, retry failures, play tracks full-screen, auto-advance, and show a queue.
- **Automatic song ID and lyrics:** Shazam identification followed by synced or plain lyric lookup, with detailed diagnostics and manual title/artist fallback.
- **MilkDrop visualizer:** Butterchurn/MilkDrop 2 presets plus independent album-cover backgrounds in Studio and Karaoke.
- **Chromatic tuner:** stable local microphone/audio-interface tuner with Standard tuning selected by default and several alternate guitar tunings.
- **Chord Creator:** local multi-genre progression generation with playback, Roman numerals, transposition, variations, diagrams, capo suggestions, and saved favorites.
- **MIDI and ASCII tab export:** optional Basic Pitch/ONNX transcription per stem.
- **Theme support:** green, blue, and red schemes with theme-matched hover states.
- **Export Save As:** whole-project ZIP export can use the browser's Save As picker where supported.
- **Background dependency checks:** safe helper packages can be checked and updated individually from Settings.
- **Windows app-style launcher:** hidden background server, dedicated maximized browser app window, desktop shortcut/icon, and close-window shutdown.

## Screenshots

**Live separation passes:**

![Separation passes](docs/screenshots/passes.png)

**Mixing studio:**

![Mixing](docs/screenshots/mixing.png)

**Karaoke mode:**

![Karaoke Mode](docs/screenshots/Karaoke1.png)

## Tested configuration

| Component | Tested value |
|---|---|
| OS | Windows 11 |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB VRAM |
| RAM | 16 GB |
| Python | 3.12 |
| PyTorch | CUDA 12.8 build |

Python **3.10-3.13** is supported by the current setup scripts; Python 3.12 is the most thoroughly tested. Python 3.14 remains too new for several optional audio packages.

Budget roughly **15-25 GB free** for the virtual environment, PyTorch, cached models, and uncompressed output stems. Extended separation can require substantially more system RAM than Quick, Standard, or Deep.

## Quick start

### Current Windows package or cumulative overlay

The packaged Windows build includes the local launchers and app-style shortcut tools that are intentionally not all stored in Git.

1. Extract the package over the Stemmy folder and allow Windows to replace files.
2. On a first installation, run `install_all.bat` or `setup.bat`.
3. `install_all.bat` automatically creates or refreshes the Stemmy desktop shortcut and icon.
4. For later source-only overlays, **do not run setup again**.
5. Start Stemmy from the desktop shortcut or with `run.bat`. `Create Stemmy Shortcut.bat` remains available as a repair tool.

Stemmy opens maximized in a dedicated Edge or Chrome app window when available. Closing that window with **X** shuts down the local Python server as well. `stop.bat` remains an emergency fallback.

See [BUILD.md](BUILD.md) for the full Windows launcher workflow and troubleshooting.

### Raw Git clone

The simplest manual installation is:

```bat
py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

rem RTX 50-series / CUDA 12.8 example:
pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128

python run_stemmy.py
```

Open `http://127.0.0.1:5002`.

Install the CUDA PyTorch build **after** `requirements.txt`. Some dependency installers can otherwise replace it with CPU-only PyTorch.

## Separation depths

| Depth | Typical output | Pipeline |
|---|---|---|
| **Quick** | 4 stems | vocals, drums, bass, other |
| **Standard** | 6 stems | adds guitar and piano |
| **Deep** | up to 13 stems | Standard plus the detailed DrumSep pass and analysis |
| **Extended** | many stems | optional ZFTurbo MSST multi-instrument model |

Models run sequentially and free VRAM between passes. Completed output is persisted under `projects/<id>/`, allowing finished projects and interrupted work to be restored.

## Studio

The Studio includes:

- Per-stem solo, mute, pan, level, selection, and download controls.
- Real waveforms and an overview strip with 1x-100x zoom.
- Pitch shifting and playback-tempo controls.
- Detected-track metronome behavior with meter, beat alignment, and feel controls.
- Live chord readout and scrolling chord ribbon.
- A-B loop controls and loop markers.
- Channel sorting and hide-below-peak filtering.
- Recent-session restore and unfinished-project resume.
- Live CPU/GPU status in the lower-left panel.
- Green, blue, and red UI themes.
- Save As behavior for full ZIP export where the browser supports the File System Access API.

## Tuner

The **Tuner** button opens a local chromatic tuner using a microphone or connected audio interface.

- Standard tuning is selected by default.
- Alternate presets include half-step down, Drop D, D Standard, Drop C sharp, Drop C, Open G, and Open D.
- A4 reference is adjustable.
- Input-device selection is supported.
- Pitch smoothing and note-locking reduce unstable note changes.
- Stemmy/Karaoke audio stops before microphone listening begins, and the input is released when the tuner closes.

## Chord Creator

The **Chord Creator** generates progressions locally without an AI or cloud API.

Genres can be selected individually or combined, including pop, classic rock, alternative rock, post-hardcore, metalcore, punk/pop-punk, indie, blues, folk/country, funk/R&B, jazz, and cinematic/synthwave.

Choose a starting chord and length, then generate progression options with:

- Roman-numeral analysis.
- Genre/key context.
- Preview playback.
- Per-chord replacement.
- Semitone transposition.
- Variation generation.
- Chord diagrams.
- Easy-shape and capo suggestions.
- Copying and local favorites.

## Karaoke

Karaoke mode accepts a YouTube playlist or single link, processes one track at a time, removes vocals, and creates instrumental WAV/MP3 files.

The player includes:

- Full-screen synced lyrics.
- Previous, play/pause, and next controls.
- Auto-advance.
- A navigable queue.
- Per-track album art.
- Independent MilkDrop and cover-art backgrounds.
- Persistent saved sessions.
- Retry Failed for transient YouTube or separation errors.

Only download material you have the right to use.

## Lyrics and song identification

Studio and Karaoke automatically attempt to identify each loaded track using ShazamIO, then fetch lyrics.

The current lyric flow:

1. Identifies the song from the original audio.
2. Tries exact lyric metadata.
3. Tries broad and cleaned title/artist searches.
4. Accepts synced or plain lyric results.
5. Preserves previously saved lyrics when a temporary provider request fails.
6. Falls back to manual title/artist entry when no provider has a match.

Detailed lyric activity is written to `logs/stemmy-lyrics.log`.

## Visualizer

The Studio and Karaoke player use locally bundled Butterchurn/MilkDrop 2 presets.

MilkDrop and album-cover backgrounds are independent: either can be enabled alone, both can be layered, or both can remain off. Preset and opacity preferences are retained while the visualizer and cover layers start disabled on a new launch.

## Updates

Stemmy performs a quiet dependency-status check in the background. Open **Settings -> Updates** to review it.

Safe helper packages can be updated individually:

- `yt-dlp`
- `shazamio`
- `imageio-ffmpeg`

Each update is isolated with `--no-deps`, followed by a compatibility check and automatic rollback if that check fails.

GPU/model-stack packages such as PyTorch, CUDA-related packages, `audio-separator`, ONNX components, and NumPy remain protected/report-only. Do not blindly update those packages from the UI.

## Windows launcher and background GPU behavior

The current Windows launcher opens Stemmy in a dedicated maximized Edge/Chrome app window and does not depend on a focused PowerShell console:

- Python runs detached and hidden.
- Output goes to `logs/stemmy.log` and `logs/stemmy-error.log`.
- Stemmy and relevant Python child processes receive high-priority/high-QoS treatment.
- The policy is re-applied to model subprocesses.
- GPU separation continues when the app loses focus or is minimized.
- Closing the dedicated app window requests a safe local server shutdown.

Performance-policy events are written to `logs/stemmy-performance.log`.

## Honest limitations

- Separating two performances of the same instrument, such as rhythm vs lead guitar or clean vs distorted guitar, remains unreliable with current source-separation models.
- The detailed drum split is much more dependable than same-instrument guitar splitting.
- Extended separation is experimental and RAM-heavy.
- Shazam, lyrics, YouTube import, and update checking require internet access even though model inference and audio processing remain local.
- Browser autoplay rules may require pressing Play once in the Karaoke player.
- YouTube changes can temporarily break downloads; update `yt-dlp` individually and use Retry Failed.

## Project layout

```text
app/
  server.py                 Flask routes and separation stream
  pipeline.py               model-pass orchestration
  models.py                 depth/model configuration
  analysis.py               tempo and beat analysis
  projects.py               persistent project state
  karaoke.py                Karaoke jobs and saved sessions
  identify.py               Shazam and lyric providers
  tools_ui.py               isolated Tuner/Chord Creator integration
  maintenance.py            update checker and shutdown support
  static/stemmy-tools/      modular Tuner/Chord Creator/maintenance JS
  templates/index.html      main application UI
projects/        separated project output, gitignored
uploads/         source audio, gitignored
karaoke_jobs/    saved Karaoke sessions, gitignored
models_cache/    downloaded model files, gitignored
logs/            launcher, performance, update, and lyric diagnostics
```

## License

[MIT](LICENSE). Third-party models and bundled libraries retain their respective licenses.