# Stemmy — launchers (BUILD.md)

The `.bat` launchers make Stemmy a double-click app on Windows. They're **gitignored**
(kept out of the repo), so this file documents what each one does and includes its **full
contents** — paste them back into files of the same name in the project root if you cloned
from GitHub.

## Install everything at once

**`install_all.bat`** is the one-shot installer: double-click it and it installs everything in one
self-contained script — it does **not** shell out to the other `.bat` files, so it works even if
they're missing. In order it sets up the `.venv` + app deps + CUDA 12.8 torch, updates yt-dlp, then
installs song ID (shazamio), MIDI/Tab export (Basic Pitch + ONNX), and the Extended 53-stem MSST
model (~2 GB). Every step is skip-if-present and self-healing, the run continues past any failure,
and it prints a summary of anything to re-run at the end. It intentionally **does not** run
`fix_gpu.bat` (that needs admin and changes your Windows power plan — run it yourself if needed).
After it finishes, start Stemmy with `run.bat`.

## Table of contents

- [Install everything at once](#install-everything-at-once)
- [One-time setup, then run](#one-time-setup-then-run)
- [What each launcher does](#what-each-launcher-does)
- [Encoding notes (CRLF / SmartScreen)](#encoding-notes-crlf--smartscreen)
- [Full contents](#full-contents)
  - [install_all.bat](#install_allbat)
  - [setup.bat](#setupbat)
  - [run.bat](#runbat)
  - [stop.bat](#stopbat)
  - [check_gpu.bat](#check_gpubat)
  - [check_models.bat](#check_modelsbat)
  - [fix_gpu.bat](#fix_gpubat)
  - [get_msst.bat](#get_msstbat)
  - [get_tabs.bat](#get_tabsbat)
  - [get_lyrics.bat](#get_lyricsbat)
  - [update_ytdlp.bat](#update_ytdlpbat)

## One-time setup, then run

> **Python version matters.** Use **Python 3.10 – 3.13** (3.12 or 3.13 recommended). Python **3.14 is
> too new** — several audio dependencies (`diffq`, `numba`/`llvmlite`, `basic-pitch`) have no wheels for
> it yet and will fail to build. `setup.bat` and `install_all.bat` now auto-pick a supported version via
> the `py` launcher and stop with a clear message if only 3.14+ is found. Get 3.12/3.13 from
> [python.org/downloads](https://www.python.org/downloads/).

0. **`install_all.bat`** *(shortcut)* — runs steps 1 + 4–7 below in one go (everything except `run.bat` and `fix_gpu.bat`).
1. **`setup.bat`** — creates `.venv`, installs dependencies, then force-installs the CUDA 12.8
   PyTorch build last so nothing overwrites it. Skips anything already installed.
2. **`run.bat`** — starts the server (HIGH priority, to limit laptop GPU throttling) and opens
   the studio at `http://127.0.0.1:5002`.
3. *(optional)* **`fix_gpu.bat`** — once, as admin, if the GPU throttles when the window loses focus.
4. *(optional)* **`get_msst.bat`** — once, to enable the experimental **Extended** depth.
5. *(optional)* **`get_tabs.bat`** — once, to enable **MIDI + Tab export** (beta) on each stem.
6. *(optional)* **`get_lyrics.bat`** — once, to enable **song ID** (lyrics work without it via manual entry).
7. *(as needed)* **`update_ytdlp.bat`** — when YouTube imports start returning **403 Forbidden**, to pull the latest yt-dlp.

## What each launcher does

| Launcher | What it does | When to run |
|----------|--------------|-------------|
| `install_all.bat` | Self-contained one-shot install: `.venv` + deps + CUDA torch, yt-dlp, song ID, tabs, and MSST — inlined (doesn't call the other bats). Skips `fix_gpu`. | First install, to do everything at once |
| `setup.bat` | Build `.venv`, install deps, force CUDA `cu128` torch last. Idempotent. | First, and after dependency changes |
| `run.bat` | Activate `.venv`, launch the server in a HIGH-priority window, open the browser. | Every time you use Stemmy |
| `stop.bat` | Kill whatever is listening on port 5002. | To shut the server down |
| `check_gpu.bat` | `nvidia-smi`, whether torch sees CUDA + VRAM, and Windows power state. | Diagnosing GPU issues |
| `check_models.bat` | List every model `audio-separator` can auto-download, plus Stemmy's mapping. | Picking / verifying model names |
| `fix_gpu.bat` | (admin) High Performance power plan + EcoQoS opt-out for the model's `python.exe`. | If the GPU throttles on a laptop |
| `get_msst.bat` | Install ZFTurbo MSST + the 53-stem checkpoint for **Extended** (optional, ~2 GB). | Once, to try Extended |
| `get_tabs.bat` | Install Basic Pitch (audio->MIDI, ONNX) for per-stem **MIDI + Tab** export (optional). | Once, to enable tabs |
| `get_lyrics.bat` | Install shazamio for **song identification** (lyrics themselves need no install). | Once, to enable song ID |
| `update_ytdlp.bat` | Update yt-dlp to the latest release. | When YouTube imports start hitting **403 Forbidden** |

## Encoding notes (CRLF / SmartScreen)

- All launchers use **Windows CRLF** line endings. If you recreate them, save with CRLF (Notepad,
  VS Code "CRLF", or run `unix2dos`), or `cmd.exe` may mis-parse multi-line blocks.
- First launch may trigger **SmartScreen** ("Windows protected your PC"): *More info → Run anyway*.
  These are plain scripts you can read in full below.
- `setup.bat` / `get_msst.bat` / `get_tabs.bat` / `get_lyrics.bat` need normal user rights; **`fix_gpu.bat` self-elevates to admin**
  (it changes the power plan and per-process power-throttling).

## Full contents

### install_all.bat

One-shot, **self-contained** installer — it inlines every install step instead of calling the
other `.bat` files, so it works even if they were never created. In order: `.venv` + app deps +
CUDA 12.8 torch, then yt-dlp, song ID (shazamio), MIDI/Tab export (Basic Pitch + ONNX), and the
Extended 53-stem MSST model (~2 GB). Every step is skip-if-present and self-healing; the run
continues past any failure and prints a summary at the end. Does **not** run `fix_gpu.bat`.

```bat
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Stemmy - install everything

echo ==========================================================
echo   Stemmy - install all  (self-contained; skips what's done)
echo ==========================================================
echo.
echo Installs, in order:
echo   1. core app + CUDA 12.8 torch (required)
echo   2. yt-dlp (YouTube import, kept current)
echo   3. song ID (shazamio)
echo   4. MIDI + Tab export (Basic Pitch + ONNX)
echo   5. Extended 53-stem depth (ZFTurbo MSST, ~2 GB - optional)
echo.
echo fix_gpu.bat is NOT run here - it needs admin and changes your
echo Windows power plan. Run it separately if the GPU throttles.
echo.
pause

set "FAILED="

REM ======================================================================
REM  1) CORE: virtual env + app deps + CUDA torch + yt-dlp
REM ======================================================================
echo.
echo ----------------------------------------------------------
echo   [1] Core app + CUDA 12.8 torch
echo ----------------------------------------------------------

REM pick a SUPPORTED Python (3.10 - 3.13); 3.14 has no wheels for the audio
REM stack and 3.13 dropped stdlib audioop, so we prefer 3.13..3.10.
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
  %PY% -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 || (
    echo [X] No supported Python found. Stemmy needs Python 3.10 - 3.13.
    %PY% --version 2>nul
    echo     Install Python 3.12 or 3.13 from https://www.python.org/downloads/
    echo     then re-run. ^(3.14 is too new; 3.13 dropped a module some libs need.^)
    set "FAILED=!FAILED! core:python-version"
    goto :after_core
  )
)
%PY% --version >nul 2>&1 || (
  echo [X] Python was not found on PATH. Install Python 3.12 or 3.13 and re-run.
  set "FAILED=!FAILED! core:no-python"
  goto :after_core
)
for /f "delims=" %%V in ('%PY% --version 2^>^&1') do echo Using %%V

set "NEWVENV=0"
if not exist ".venv\Scripts\activate.bat" (
  echo Creating virtual environment .venv ...
  %PY% -m venv .venv || (set "FAILED=!FAILED! core:venv" & goto :after_core)
  set "NEWVENV=1"
) else (
  echo .venv          already present - skipping.
)
call ".venv\Scripts\activate.bat" || (set "FAILED=!FAILED! core:activate" & goto :after_core)

if "!NEWVENV!"=="1" (
  python -m pip install --upgrade pip
)

REM app dependencies (may pull a CPU-only torch; the CUDA step below corrects it)
python -c "import flask, audio_separator, librosa, soundfile, numpy" 2>nul
if errorlevel 1 (
  echo requirements   installing app dependencies ...
  pip install -r requirements.txt || (set "FAILED=!FAILED! core:requirements" & goto :after_core)
) else (
  echo requirements   already satisfied - skipping.
)

REM PyTorch with CUDA 12.8 (Blackwell sm_120), asserted LAST so nothing overwrites it
python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul
if errorlevel 1 (
  echo torch          installing CUDA 12.8 build for Blackwell ^(force-reinstall^) ...
  pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128 || (set "FAILED=!FAILED! core:torch" & goto :after_core)
) else (
  echo torch          CUDA build already active - skipping.
)

echo.
echo Verifying the GPU is visible to torch ...
python -c "import torch as T; ok=T.cuda.is_available(); print('  torch  :', T.__version__); print('  CUDA   :', ok); print('  GPU    :', T.cuda.get_device_name(0) if ok else 'CPU only')"
python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul || (
  echo   [!] Still CPU-only. The cu128 index may not have a wheel for your
  echo       Python version. Use Python 3.12 or 3.13, or try the cu129 index.
)
:after_core

REM ======================================================================
REM  2) yt-dlp (keep current - fixes most YouTube 403 fetch failures)
REM ======================================================================
echo.
echo ----------------------------------------------------------
echo   [2] yt-dlp (YouTube import)
echo ----------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
  echo Updating yt-dlp to the newest version ...
  python -m pip install -U yt-dlp || set "FAILED=!FAILED! yt-dlp"
) else (
  echo [!] No .venv - core step must succeed first. Skipping.
  set "FAILED=!FAILED! yt-dlp:no-venv"
)

REM ======================================================================
REM  3) song ID (shazamio). Lyrics come from LRCLIB (free, no package).
REM ======================================================================
echo.
echo ----------------------------------------------------------
echo   [3] Song ID (shazamio)
echo ----------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
  echo Installing shazamio ^(song identification^) ...
  pip install shazamio >nul 2>nul
  rem Python 3.13 removed stdlib 'audioop' that pydub (shazamio dep) needs.
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,13) else 1)" >nul 2>&1 && pip install audioop-lts >nul 2>nul
  python -c "import shazamio; print('Song ID + lyrics ready.')" || (
    echo [!] Song ID install failed - you can still type a title/artist for lyrics.
    set "FAILED=!FAILED! song-id"
  )
) else (
  echo [!] No .venv - core step must succeed first. Skipping.
  set "FAILED=!FAILED! song-id:no-venv"
)

REM ======================================================================
REM  4) MIDI + Tab export (Basic Pitch, ONNX runtime).
REM     --no-deps on basic-pitch: its metadata hard-pins TensorFlow, which
REM     has no matching wheel on Windows/py3.12. We add the real runtime deps.
REM ======================================================================
echo.
echo ----------------------------------------------------------
echo   [4] MIDI + Tab export (Basic Pitch)
echo ----------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
  echo Installing Basic Pitch ^(audio-to-MIDI^) without its TensorFlow pin ...
  pip install "basic-pitch==0.4.0" --no-deps || (set "FAILED=!FAILED! tabs" & goto :after_tabs)
  echo Installing the ONNX runtime + light transcription deps ...
  pip install onnxruntime "pretty_midi>=0.2.9" "resampy>=0.2.2,<0.4.3" "mir_eval>=0.6" || (set "FAILED=!FAILED! tabs" & goto :after_tabs)
  pip install "librosa>=0.10" scikit-learn "setuptools<81" typing-extensions || (set "FAILED=!FAILED! tabs" & goto :after_tabs)
  python -c "from basic_pitch.inference import predict; import onnxruntime; print('Tab/MIDI export ready.')" || set "FAILED=!FAILED! tabs"
) else (
  echo [!] No .venv - core step must succeed first. Skipping.
  set "FAILED=!FAILED! tabs:no-venv"
)
:after_tabs

REM ======================================================================
REM  5) Extended 53-stem depth (ZFTurbo MSST + bs_roformer checkpoint).
REM     Big (~2 GB) and VRAM-hungry. We DON'T build the project (its build
REM     needs git + setuptools-scm); we drop the code in place and install
REM     only the libs inference.py needs.
REM ======================================================================
echo.
echo ----------------------------------------------------------
echo   [5] Extended 53-stem depth (ZFTurbo MSST, ~2 GB)
echo ----------------------------------------------------------
set "MODEL_TYPE=bs_roformer"
set "CFG_NAME=mvsep_mega_model_bs_roformer_53_stems.yaml"
set "CKPT_NAME=mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
set "REL=https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21"
set "MSST_DEPS=ml-collections omegaconf PyYAML librosa matplotlib soundfile tqdm numpy beartype einops packaging rotary-embedding-torch PoPE-pytorch"

if not exist ".venv\Scripts\activate.bat" (
  echo [!] No .venv - core step must succeed first. Skipping.
  set "FAILED=!FAILED! msst:no-venv"
  goto :after_msst
)
call ".venv\Scripts\activate.bat"
if not exist "models_cache" mkdir "models_cache"
if not exist "models_cache\msst_models" mkdir "models_cache\msst_models"

echo [5.1] MSST inference code ...
set "MSSTOK="
if exist "models_cache\msst\inference.py" if exist "models_cache\msst\pyproject.toml" set "MSSTOK=1"
if defined MSSTOK (
  echo       present and complete - skipping.
) else (
  echo       downloading + extracting ^(via PowerShell^) ...
  if exist "models_cache\msst" rmdir /s /q "models_cache\msst"
  if exist "models_cache\_msst_tmp" rmdir /s /q "models_cache\_msst_tmp"
  curl -fL -o "models_cache\msst.zip" "https://github.com/ZFTurbo/Music-Source-Separation-Training/archive/refs/heads/main.zip"
  if errorlevel 1 (set "FAILED=!FAILED! msst:download-code" & goto :after_msst)
  rem locate + move the folder containing inference.py inside PowerShell (robust)
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { Expand-Archive -LiteralPath 'models_cache\msst.zip' -DestinationPath 'models_cache\_msst_tmp' -Force; $inf = Get-ChildItem -Path 'models_cache\_msst_tmp' -Recurse -Filter 'inference.py' | Select-Object -First 1; if (-not $inf) { Write-Host '[X] inference.py not found in archive.'; exit 3 }; $src = $inf.Directory.FullName; New-Item -ItemType Directory -Force -Path 'models_cache\msst' | Out-Null; Get-ChildItem -LiteralPath $src -Force | Move-Item -Destination 'models_cache\msst' -Force; exit 0 } catch { Write-Host ('[X] ' + $_.Exception.Message); exit 4 }"
  if errorlevel 1 (set "FAILED=!FAILED! msst:extract" & goto :after_msst)
  rmdir /s /q "models_cache\_msst_tmp" >nul 2>&1
  del "models_cache\msst.zip" >nul 2>&1
  if not exist "models_cache\msst\inference.py" (
    echo [X] inference.py missing after extract.
    set "FAILED=!FAILED! msst:no-inference"
    goto :after_msst
  )
  if not exist "models_cache\msst\pyproject.toml" (
    echo [X] pyproject.toml missing after extract.
    set "FAILED=!FAILED! msst:no-pyproject"
    goto :after_msst
  )
)

echo [5.2] Installing MSST inference dependencies ...
pip install %MSST_DEPS%
if errorlevel 1 (set "FAILED=!FAILED! msst:deps" & goto :after_msst)
python -c "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul
if errorlevel 1 (
  echo       [!] torch lost CUDA - restoring the cu128 build ...
  pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128
)

echo [5.3] Downloading model config + checkpoint ...
if exist "models_cache\msst_models\%CFG_NAME%" (
  for %%F in ("models_cache\msst_models\%CFG_NAME%") do if %%~zF LSS 200 del "models_cache\msst_models\%CFG_NAME%"
)
if not exist "models_cache\msst_models\%CFG_NAME%" (
  curl -fL -o "models_cache\msst_models\%CFG_NAME%" "%REL%/%CFG_NAME%"
  if errorlevel 1 (set "FAILED=!FAILED! msst:config" & goto :after_msst)
)
if exist "models_cache\msst_models\%CKPT_NAME%" (
  for %%F in ("models_cache\msst_models\%CKPT_NAME%") do if %%~zF LSS 50000000 del "models_cache\msst_models\%CKPT_NAME%"
)
if not exist "models_cache\msst_models\%CKPT_NAME%" (
  echo       downloading checkpoint ^(~2 GB, this takes a while^) ...
  curl -fL -o "models_cache\msst_models\%CKPT_NAME%" "%REL%/%CKPT_NAME%"
  if errorlevel 1 (set "FAILED=!FAILED! msst:checkpoint" & goto :after_msst)
)
set "SZ="
for %%F in ("models_cache\msst_models\%CKPT_NAME%") do set "SZ=%%~zF"
if not defined SZ (set "FAILED=!FAILED! msst:checkpoint-missing" & goto :after_msst)
if !SZ! LSS 50000000 (
  echo [X] checkpoint only !SZ! bytes - download failed. Deleting.
  del "models_cache\msst_models\%CKPT_NAME%" >nul 2>&1
  set "FAILED=!FAILED! msst:checkpoint-small"
  goto :after_msst
)

echo [5.4] Writing manifest ...
> "models_cache\msst_models\manifest.json" echo {"model_type":"%MODEL_TYPE%","config":"%CFG_NAME%","checkpoint":"%CKPT_NAME%"}
echo       MSST ready (!SZ! bytes).
:after_msst

REM ======================================================================
REM  Summary
REM ======================================================================
echo.
echo ==========================================================
if defined FAILED (
  echo   Finished, but these steps reported a problem:
  echo  !FAILED!
  echo   Stemmy still runs without the optional ones. Re-run this
  echo   script - it self-heals - or the matching get_*.bat to retry.
) else (
  echo   All installers finished. Start Stemmy with run.bat.
)
echo ==========================================================
echo.
pause
exit /b 0
```

### setup.bat

```bat
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo   Stemmy - setup  (skips anything already installed)
echo ==========================================================
echo.

REM --- pick a SUPPORTED Python (3.10 - 3.13) ------------------------
REM The audio stack (diffq, numba/llvmlite, pydub, basic-pitch) has no
REM wheels for Python 3.14 yet, and 3.13 removed the stdlib 'audioop'
REM module pydub needs. So we prefer 3.13 down to 3.10 via the py
REM launcher, and refuse anything outside that range with a clear message.
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  REM no py launcher match - try bare py / python, then verify the version
  where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
  %PY% -c "import sys; raise SystemExit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 || (
    echo [X] No supported Python found. Stemmy needs Python 3.10 - 3.13.
    %PY% --version 2>nul
    echo     Python 3.14 is too new ^(no wheels yet^) and 3.13 dropped a
    echo     module some audio libs use. Install Python 3.12 or 3.13 from
    echo     https://www.python.org/downloads/  then re-run this script.
    goto :fail
  )
)
%PY% --version >nul 2>&1 || (
  echo [X] Python was not found on PATH. Install Python 3.12 or 3.13 and re-run.
  goto :fail
)
for /f "delims=" %%V in ('%PY% --version 2^>^&1') do echo Using %%V

REM --- virtual environment (.venv is gitignored) -------------------
set "NEWVENV=0"
if not exist ".venv\Scripts\activate.bat" (
  echo Creating virtual environment .venv ...
  %PY% -m venv .venv || goto :fail
  set "NEWVENV=1"
) else (
  echo .venv          already present - skipping.
)
call ".venv\Scripts\activate.bat" || goto :fail

REM --- upgrade pip only on a freshly created venv -----------------
if "!NEWVENV!"=="1" (
  python -m pip install --upgrade pip
)

REM --- 1) app dependencies ----------------------------------------
REM audio-separator etc. These can drag a CPU-only torch in from PyPI;
REM the next step corrects that, so it MUST come after this one.
python -c "import flask, audio_separator, librosa, soundfile, numpy" 2>nul
if errorlevel 1 (
  echo requirements   installing app dependencies ...
  pip install -r requirements.txt || goto :fail
) else (
  echo requirements   already satisfied - skipping.
)

REM --- 2) PyTorch with CUDA, asserted LAST so nothing overwrites it -
REM Your RTX 5060 is Blackwell (compute capability sm_120) and needs a
REM cu128 (CUDA 12.8) build - the default PyPI wheel is CPU-only and will
REM NOT use the GPU. force-reinstall guarantees the CUDA build wins even
REM if the step above pulled a CPU torch. Skipped when CUDA is already live.
python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul
if errorlevel 1 (
  echo torch          installing CUDA 12.8 build for Blackwell ^(force-reinstall^) ...
  pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128 || goto :fail
) else (
  echo torch          CUDA build already active - skipping.
)

REM --- 3) keep yt-dlp current (YouTube link import). YouTube changes often,
REM so re-running setup.bat refreshes it - this is what fixes most fetch fails.
echo yt-dlp         updating YouTube import (yt-dlp) ...
pip install -U yt-dlp >nul 2>&1

echo.
echo Verifying the GPU is visible to torch ...
python -c "import torch as T; ok=T.cuda.is_available(); print('  torch  :', T.__version__); print('  CUDA   :', ok); print('  GPU    :', T.cuda.get_device_name(0) if ok else 'CPU only')"
python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul || (
  echo.
  echo   [!] Still CPU-only. The cu128 index may not have a wheel for your
  echo       Python version. Use Python 3.12 or 3.13, or try the cu129 index.
)

echo.
echo ==========================================================
echo   Setup complete.  Double-click run.bat to start Stemmy.
echo ==========================================================
echo.
echo NOTE: before your first separation, confirm the model file
echo names in app\models.py against:  audio-separator --list_models
echo.
pause
exit /b 0

:fail
echo.
echo [X] Setup failed above. Fix the error and run setup.bat again.
echo.
pause
exit /b 1
```

### run.bat

```bat
@echo off
cd /d "%~dp0"

REM --- use the venv if setup.bat created one -----------------------
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo [!] No .venv found - run setup.bat first. Falling back to system Python.
)

echo.
echo Starting Stemmy at http://127.0.0.1:5002
echo Launching the server in a HIGH priority window to limit laptop
echo GPU throttling when this window loses focus. Keep it open while
echo you work; close it or run stop.bat to shut the server down.
echo.

REM --- server runs in its own HIGH-priority console ---------------
start "Stemmy" /HIGH python run_stemmy.py

REM --- give the server a few seconds, then open the studio --------
timeout /t 4 >nul
start "" http://127.0.0.1:5002

exit /b 0
```

### stop.bat

```bat
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Port Stemmy listens on. Change this if you start it with --port.
set "PORT=5002"

echo Stopping Stemmy on port %PORT% ...
set "FOUND=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') do (
  echo   killing PID %%P
  taskkill /F /PID %%P >nul 2>&1
  set "FOUND=1"
)

if "!FOUND!"=="0" (
  echo   Nothing was listening on port %PORT%.
) else (
  echo   Stemmy stopped.
)

echo.
timeout /t 2 >nul
exit /b 0
```

### check_gpu.bat

```bat
@echo off
setlocal
cd /d "%~dp0"
title Stemmy - GPU check

echo ==========================================================
echo   Stemmy - GPU check
echo ==========================================================
echo.

echo [ driver / nvidia-smi ] ---------------------------------
nvidia-smi 2>nul
if errorlevel 1 echo   nvidia-smi not found - NVIDIA driver may be missing or not on PATH.
echo.

echo [ torch sees the GPU ] ----------------------------------
set "VPY=python"
if exist ".venv\Scripts\python.exe" set "VPY=.venv\Scripts\python.exe"
"%VPY%" -c "import torch as T; ok=T.cuda.is_available(); print('  torch      :', T.__version__); print('  built CUDA :', T.version.cuda); print('  CUDA avail :', ok); print('  GPU        :', T.cuda.get_device_name(0) if ok else 'CPU only'); print('  VRAM total :', (str(round(T.cuda.get_device_properties(0).total_memory/1073741824,1))+' GB') if ok else 'n/a')" 2>nul
if errorlevel 1 echo   torch not importable here - run setup.bat first.
echo.

echo [ Windows power state ] ---------------------------------
powercfg /getactivescheme
echo.
echo   power-throttling opt-out for python:
powercfg /powerthrottling list 2>nul | findstr /i "python" || echo   (none set - run fix_gpu.bat to stop Windows throttling Stemmy)
echo.

pause
exit /b 0
```

### check_models.bat

```bat
@echo off
setlocal
cd /d "%~dp0"
title Stemmy - list separation models

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo [!] No .venv found - run setup.bat first.
  pause & exit /b 1
)

echo ==========================================================
echo   Models audio-separator can download automatically
echo ==========================================================
echo.
echo Tip: filter the list, e.g.   audio-separator -l --list_filter=drums
echo The names below are what you put in app\models.py.
echo.

audio-separator --list_models

echo.
echo ----------------------------------------------------------
echo Stemmy's models (all auto-downloaded by audio-separator):
echo   Quick     htdemucs_ft.yaml      (vocals/drums/bass/other)
echo   Standard  htdemucs_6s.yaml      (+ guitar + piano)
echo   Deep      htdemucs_6s.yaml      + MDX23C-DrumSep-aufr33-jarredou.ckpt
echo             (drums split into kick/snare/toms/hat/ride/crash)
echo.
echo No manual model download needed for Quick/Standard/Deep. For the
echo EXTENDED depth (synth/organ/strings/brass/... via ZFTurbo MSST),
echo run get_msst.bat once - see README, search "ZFTurbo MSST install".
echo ----------------------------------------------------------
echo.
pause
```

### fix_gpu.bat

```bat
@echo off
setlocal
title Stemmy - fix GPU throttling

REM --- powercfg power-throttling + scheme changes need admin -------
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

cd /d "%~dp0"

echo ==========================================================
echo   Stemmy - fix GPU throttling  (running as admin)
echo ==========================================================
echo.
echo Applies the OS-level counterparts to an in-app speed keep-alive:
echo a High Performance power plan, plus a power-throttling (EcoQoS)
echo opt-out for the Python that runs the models - so Windows stops
echo throttling the GPU when the Stemmy window loses focus on a laptop.
echo.

echo [1/2] Setting the High Performance power plan ...
powercfg /setactive SCHEME_MIN
if errorlevel 1 (echo       could not change the power plan.) else (echo       done.)
echo.

REM --- locate the python.exe Stemmy actually runs ------------------
set "PYEXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not defined PYEXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%P"

echo [2/2] Disabling power throttling for the model process ...
if not defined PYEXE (
  echo       no python.exe found - run setup.bat first, then re-run this.
  goto :end
)
echo       target: %PYEXE%
powercfg /powerthrottling disable /path "%PYEXE%"
if errorlevel 1 (
  echo       this Windows build may not support per-app power-throttling
  echo       control; the High Performance plan above and run.bat's HIGH
  echo       priority launch still help.
) else (
  echo       done - Windows will not EcoQoS-throttle that executable.
)

:end
echo.
echo ==========================================================
echo   Finished.  To undo later:
echo     powercfg /powerthrottling reset /path "the python.exe above"
echo     powercfg /setactive SCHEME_BALANCED
echo ==========================================================
echo.
pause
exit /b 0
```

### get_msst.bat

> Installs the optional **Extended** depth (ZFTurbo MSST + the 53-stem `bs_roformer` model, ~2 GB).
> Self-healing: re-running only fixes what's broken. To use a different MSST model, edit the
> `MODEL_TYPE` / `CFG_NAME` / `CKPT_NAME` / `REL` variables near the top.

```bat
@echo off
setlocal enableextensions enabledelayedexpansion
cd /d "%~dp0"
title Stemmy - install ZFTurbo MSST + 53-stem instrument model (optional)

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo [!] No .venv found - run setup.bat first.
  pause & exit /b 1
)
if not exist "models_cache" mkdir "models_cache"
if not exist "models_cache\msst_models" mkdir "models_cache\msst_models"

rem ==== the model to install (edit these to use a different MSST model) ========
set "MODEL_TYPE=bs_roformer"
set "CFG_NAME=mvsep_mega_model_bs_roformer_53_stems.yaml"
set "CKPT_NAME=mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
set "REL=https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21"
rem deps the bs_roformer *inference* path needs (torch/torchaudio already in .venv).
rem MSST dropped requirements.txt for pyproject.toml, and its build uses
rem setuptools-scm (needs git) - so we DON'T build the project, we just install
rem these and run inference.py in place. Edit if you switch model architectures.
set "MSST_DEPS=ml-collections omegaconf PyYAML librosa matplotlib soundfile tqdm numpy beartype einops packaging rotary-embedding-torch PoPE-pytorch"
rem ============================================================================

echo ==========================================================
echo   Stemmy - optional MSST install (extended instrument split)
echo   Installs ZFTurbo's MSST + the 53-stem bs_roformer model.
echo   Big download (model is ~2 GB) and VRAM-hungry. Optional.
echo   (self-healing: re-runs only fix what's broken)
echo ==========================================================
echo.

echo [1/4] MSST inference code ...
set "MSSTOK="
if exist "models_cache\msst\inference.py" if exist "models_cache\msst\pyproject.toml" set "MSSTOK=1"
if defined MSSTOK (
  echo       present and complete - skipping.
) else (
  echo       downloading + extracting ^(via PowerShell, reliable on Win10/11^) ...
  if exist "models_cache\msst" rmdir /s /q "models_cache\msst"
  if exist "models_cache\_msst_tmp" rmdir /s /q "models_cache\_msst_tmp"
  curl -fL -o "models_cache\msst.zip" "https://github.com/ZFTurbo/Music-Source-Separation-Training/archive/refs/heads/main.zip"
  if errorlevel 1 goto :fail
  rem Extract, then move the folder that actually contains inference.py straight
  rem into models_cache\msst. Doing the locate+move inside PowerShell avoids the
  rem fragile cmd for-loop / substring / MOVE chain that could leave msst as the
  rem parent folder (the "pyproject.toml missing" failure some users hit).
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { Expand-Archive -LiteralPath 'models_cache\msst.zip' -DestinationPath 'models_cache\_msst_tmp' -Force; $inf = Get-ChildItem -Path 'models_cache\_msst_tmp' -Recurse -Filter 'inference.py' | Select-Object -First 1; if (-not $inf) { Write-Host '[X] inference.py not found in archive.'; exit 3 }; $src = $inf.Directory.FullName; New-Item -ItemType Directory -Force -Path 'models_cache\msst' | Out-Null; Get-ChildItem -LiteralPath $src -Force | Move-Item -Destination 'models_cache\msst' -Force; exit 0 } catch { Write-Host ('[X] ' + $_.Exception.Message); exit 4 }"
  if errorlevel 1 goto :fail
  rmdir /s /q "models_cache\_msst_tmp" >nul 2>&1
  del "models_cache\msst.zip" >nul 2>&1
  if not exist "models_cache\msst\inference.py" (
    echo [X] inference.py missing after extract.
    goto :fail
  )
  if not exist "models_cache\msst\pyproject.toml" (
    echo [X] pyproject.toml missing after extract.
    goto :fail
  )
)

echo.
echo [2/4] Installing MSST inference dependencies into .venv ...
echo       (not building the project - just the libs inference.py needs)
pip install %MSST_DEPS%
if errorlevel 1 goto :fail
python -c "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)" 2>nul
if errorlevel 1 (
  echo       [!] torch lost CUDA - restoring the cu128 build ...
  pip install --force-reinstall --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cu128
)

echo.
echo [3/4] Downloading model config + checkpoint ...
if exist "models_cache\msst_models\%CFG_NAME%" (
  for %%F in ("models_cache\msst_models\%CFG_NAME%") do if %%~zF LSS 200 del "models_cache\msst_models\%CFG_NAME%"
)
if not exist "models_cache\msst_models\%CFG_NAME%" (
  curl -fL -o "models_cache\msst_models\%CFG_NAME%" "%REL%/%CFG_NAME%"
  if errorlevel 1 goto :fail
)
if exist "models_cache\msst_models\%CKPT_NAME%" (
  for %%F in ("models_cache\msst_models\%CKPT_NAME%") do if %%~zF LSS 50000000 del "models_cache\msst_models\%CKPT_NAME%"
)
if not exist "models_cache\msst_models\%CKPT_NAME%" (
  echo       downloading checkpoint ^(~2 GB, this takes a while^) ...
  curl -fL -o "models_cache\msst_models\%CKPT_NAME%" "%REL%/%CKPT_NAME%"
  if errorlevel 1 goto :fail
)
set "SZ="
for %%F in ("models_cache\msst_models\%CKPT_NAME%") do set "SZ=%%~zF"
if not defined SZ goto :fail
if !SZ! LSS 50000000 (
  echo [X] checkpoint only !SZ! bytes - download failed. Deleting.
  del "models_cache\msst_models\%CKPT_NAME%" >nul 2>&1
  goto :fail
)

echo.
echo [4/4] Writing manifest ...
> "models_cache\msst_models\manifest.json" echo {"model_type":"%MODEL_TYPE%","config":"%CFG_NAME%","checkpoint":"%CKPT_NAME%"}

echo.
echo ==========================================================
echo   DONE. Checkpoint OK (!SZ! bytes).
echo   In Stemmy, pick the EXTENDED depth to split into many
echo   instruments (synth/organ/strings/brass/...). First run is
echo   slow and needs lots of VRAM - if it runs out of memory the
echo   pass skips and the base stems still complete.
echo ==========================================================
echo.
pause
exit /b 0

:fail
echo.
echo [X] MSST setup failed above. Stemmy still works without it
echo     (Extended depth will just say it needs MSST).
echo     curl ships with Windows 10/11; if missing, update Windows.
echo     Re-running this script retries only the broken parts.
echo     See README - search "ZFTurbo MSST install" for details.
echo.
pause
exit /b 1
```

### get_tabs.bat

Installs Spotify's Basic Pitch (audio-to-MIDI) plus a light ONNX runtime so the **TAB** button appears on each stem. Installed with `--no-deps` on purpose: basic-pitch's metadata hard-pins TensorFlow on Python 3.11+, which has no matching wheel on Windows/py3.12 and would fail — Stemmy only needs the bundled `.onnx` model + `onnxruntime`. Run `setup.bat` first.

```bat
@echo off
REM ============================================================
REM  get_tabs.bat  -  enable MIDI + Tab export (beta) in Stemmy
REM
REM  This installs Spotify's Basic Pitch (audio -> MIDI) plus a
REM  light ONNX runtime. We install with --no-deps on purpose:
REM  basic-pitch's metadata hard-pins TensorFlow on Python 3.11+,
REM  which has no matching wheel on Windows/py3.12 and would fail.
REM  Stemmy only needs the ONNX runtime (the model ships as .onnx),
REM  so we add the handful of real runtime deps ourselves.
REM ============================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo No .venv found - run setup.bat first.
  pause
  exit /b 1
)

echo.
echo Installing Basic Pitch (audio-to-MIDI) without its TensorFlow pin ...
pip install "basic-pitch==0.4.0" --no-deps || goto :fail

echo.
echo Installing the ONNX runtime + light transcription deps ...
pip install onnxruntime "pretty_midi>=0.2.9" "resampy>=0.2.2,<0.4.3" "mir_eval>=0.6" || goto :fail
REM basic-pitch imports librosa + scikit-learn at runtime; we install with
REM --no-deps (to skip its TensorFlow pin) so we add these ourselves. They
REM normally come from requirements.txt too, but a failed/partial core install
REM can leave them missing - installing here makes tabs self-sufficient.
REM setuptools provides pkg_resources, which resampy 0.4.2 imports.
pip install "librosa>=0.10" scikit-learn "setuptools<81" typing-extensions || goto :fail

echo.
echo Verifying ...
python -c "from basic_pitch.inference import predict; import onnxruntime; print('Tab/MIDI export ready.')" || goto :fail

echo.
echo Done. Restart Stemmy (run.bat) and the TAB button will appear on each stem.
pause
exit /b 0

:fail
echo.
echo Install failed. You can retry, or open an issue with the message above.
pause
exit /b 1
```

### get_lyrics.bat

Installs **shazamio** so Stemmy can identify a track from its audio. Lyrics themselves come from LRCLIB over plain HTTP and need no package, so even without this you can type a title/artist and still get synced lyrics. Run `setup.bat` first.

```bat
@echo off
REM ============================================================
REM  get_lyrics.bat  -  enable song ID + lyrics in Stemmy
REM  Installs shazamio (song recognition). Lyrics come from
REM  LRCLIB (free, no key) and need no extra package.
REM ============================================================
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo No .venv found - run setup.bat first.
  pause
  exit /b 1
)
echo.
echo Installing shazamio (song identification) ...
pip install shazamio || goto :fail
REM Python 3.13 removed the stdlib 'audioop' module that pydub (a shazamio
REM dependency) imports. Install the audioop-lts backport so it works on 3.13.
REM (Harmless on 3.10-3.12, where it simply isn't needed.)
python -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,13) else 1)" >nul 2>&1 && pip install audioop-lts
echo.
python -c "import shazamio; print('Song ID + lyrics ready.')" || goto :fail
echo.
echo Done. Restart Stemmy (run.bat) and use "Show lyrics" in the studio.
pause
exit /b 0
:fail
echo.
echo Install failed. You can still type a title/artist to fetch lyrics without song ID.
pause
exit /b 1
```

### update_ytdlp.bat

Updates yt-dlp to the latest release. YouTube changes its stream signatures often, which is the
usual cause of **`HTTP Error 403: Forbidden`** on a *subset* of tracks in a karaoke batch (some
download fine, others 403). A stale yt-dlp is the most common reason. Run this, reopen Stemmy, then
use **Retry failed** in the karaoke panel to re-run just the blocked tracks — Stemmy also tries the
`android`/`ios`/`tv` player clients and retries automatically, but the latest yt-dlp fixes the rest.

```bat
@echo off
setlocal
cd /d "%~dp0"
title Stemmy - update yt-dlp

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else (
  echo [!] No .venv found - run setup.bat first.
  pause ^& exit /b 1
)

echo ==========================================================
echo   Updating yt-dlp
echo ==========================================================
echo.
echo YouTube changes its streams often, which is the usual cause of
echo "HTTP Error 403: Forbidden" on some tracks. Updating yt-dlp to the
echo latest release fixes the large majority of those failures.
echo.
echo Updating yt-dlp to the newest version ...
python -m pip install -U yt-dlp
echo.
if errorlevel 1 (
  echo [!] Update failed. Check your internet connection and try again.
) else (
  echo [ok] yt-dlp is up to date.
  echo     Reopen Stemmy, then use "Retry failed" in the karaoke panel
  echo     to re-run any tracks that hit a 403.
)
echo.
pause
```
