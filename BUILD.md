# Stemmy — launchers (BUILD.md)

The `.bat` launchers make Stemmy a double-click app on Windows. They're **gitignored**
(kept out of the repo), so this file documents what each one does and includes its **full
contents** — paste them back into files of the same name in the project root if you cloned
from GitHub.

## Table of contents

- [One-time setup, then run](#one-time-setup-then-run)
- [What each launcher does](#what-each-launcher-does)
- [Encoding notes (CRLF / SmartScreen)](#encoding-notes-crlf--smartscreen)
- [Full contents](#full-contents)
  - [setup.bat](#setupbat)
  - [run.bat](#runbat)
  - [stop.bat](#stopbat)
  - [check_gpu.bat](#check_gpubat)
  - [check_models.bat](#check_modelsbat)
  - [fix_gpu.bat](#fix_gpubat)
  - [get_msst.bat](#get_msstbat)

## One-time setup, then run

1. **`setup.bat`** — creates `.venv`, installs dependencies, then force-installs the CUDA 12.8
   PyTorch build last so nothing overwrites it. Skips anything already installed.
2. **`run.bat`** — starts the server (HIGH priority, to limit laptop GPU throttling) and opens
   the studio at `http://127.0.0.1:5002`.
3. *(optional)* **`fix_gpu.bat`** — once, as admin, if the GPU throttles when the window loses focus.
4. *(optional)* **`get_msst.bat`** — once, to enable the experimental **Extended** depth.

## What each launcher does

| Launcher | What it does | When to run |
|----------|--------------|-------------|
| `setup.bat` | Build `.venv`, install deps, force CUDA `cu128` torch last. Idempotent. | First, and after dependency changes |
| `run.bat` | Activate `.venv`, launch the server in a HIGH-priority window, open the browser. | Every time you use Stemmy |
| `stop.bat` | Kill whatever is listening on port 5002. | To shut the server down |
| `check_gpu.bat` | `nvidia-smi`, whether torch sees CUDA + VRAM, and Windows power state. | Diagnosing GPU issues |
| `check_models.bat` | List every model `audio-separator` can auto-download, plus Stemmy's mapping. | Picking / verifying model names |
| `fix_gpu.bat` | (admin) High Performance power plan + EcoQoS opt-out for the model's `python.exe`. | If the GPU throttles on a laptop |
| `get_msst.bat` | Install ZFTurbo MSST + the 53-stem checkpoint for **Extended** (optional, ~2 GB). | Once, to try Extended |

## Encoding notes (CRLF / SmartScreen)

- All launchers use **Windows CRLF** line endings. If you recreate them, save with CRLF (Notepad,
  VS Code "CRLF", or run `unix2dos`), or `cmd.exe` may mis-parse multi-line blocks.
- First launch may trigger **SmartScreen** ("Windows protected your PC"): *More info → Run anyway*.
  These are plain scripts you can read in full below.
- `setup.bat` / `get_msst.bat` need normal user rights; **`fix_gpu.bat` self-elevates to admin**
  (it changes the power plan and per-process power-throttling).

## Full contents

### setup.bat

```bat
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo   Stemmy - setup  (skips anything already installed)
echo ==========================================================
echo.

REM --- pick a Python launcher (prefer the py launcher) ---------------
where py >nul 2>&1 && (set "PY=py") || (set "PY=python")
%PY% --version >nul 2>&1 || (
  echo [X] Python was not found on PATH. Install Python 3.10+ and re-run.
  goto :fail
)

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
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath 'models_cache\msst.zip' -DestinationPath 'models_cache\_msst_tmp' -Force"
  if errorlevel 1 goto :fail
  set "MSSTSRC="
  for /r "models_cache\_msst_tmp" %%F in (inference.py) do if not defined MSSTSRC set "MSSTSRC=%%~dpF"
  if not defined MSSTSRC (
    echo [X] inference.py not found after extract.
    goto :fail
  )
  move "!MSSTSRC:~0,-1!" "models_cache\msst" >nul
  rmdir /s /q "models_cache\_msst_tmp" >nul 2>&1
  del "models_cache\msst.zip" >nul 2>&1
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
