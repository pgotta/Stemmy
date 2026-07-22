param(
  [string]$Url = "http://127.0.0.1:5002",
  [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = "SilentlyContinue"

function Find-Browser {
  $candidates = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
  }
  return $null
}

function Maximize-StemmyWindow {
  param(
    [System.Diagnostics.Process]$InitialProcess,
    [string]$BrowserPath,
    [datetime]$LaunchTime
  )

  try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class StemmyNativeWindow {
  [DllImport("user32.dll")]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
  } catch {}

  $browserName = [System.IO.Path]::GetFileNameWithoutExtension($BrowserPath)
  $chosen = $null

  # Chromium may hand the app window to a child process. Wait briefly for the
  # newest visible process from this launch rather than assuming Start-Process
  # returned the final window-owning process.
  for ($attempt = 0; $attempt -lt 80; $attempt++) {
    Start-Sleep -Milliseconds 250
    $visible = @(
      Get-Process -Name $browserName -ErrorAction SilentlyContinue |
      Where-Object {
        $_.MainWindowHandle -ne 0 -and
        $_.StartTime -ge $LaunchTime.AddSeconds(-5)
      } |
      Sort-Object StartTime -Descending
    )

    if ($visible.Count -gt 0) {
      $chosen = $visible[0]
      break
    }

    try {
      $InitialProcess.Refresh()
      if ($InitialProcess.MainWindowHandle -ne 0) {
        $chosen = $InitialProcess
        break
      }
    } catch {}
  }

  if ($chosen -and $chosen.MainWindowHandle -ne 0) {
    try {
      # SW_MAXIMIZE = 3
      [StemmyNativeWindow]::ShowWindowAsync($chosen.MainWindowHandle, 3) | Out-Null
      [StemmyNativeWindow]::SetForegroundWindow($chosen.MainWindowHandle) | Out-Null
    } catch {}
    return $chosen
  }

  return $InitialProcess
}

$browser = Find-Browser
if (-not $browser) {
  Start-Process $Url
  exit 0
}

# A dedicated Chromium profile keeps this window tied to Stemmy rather than the
# user's ordinary browser session. Closing the app window therefore gives the
# launcher a dependable shutdown signal.
$profile = Join-Path $Root ".stemmy-browser-profile"
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$args = @(
  "--app=$Url",
  "--user-data-dir=$profile",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-mode",
  "--start-maximized",
  "--window-position=0,0"
)

$launchTime = Get-Date
$process = Start-Process -FilePath $browser -ArgumentList $args -PassThru
if (-not $process) {
  Start-Process $Url
  exit 0
}

$windowProcess = Maximize-StemmyWindow -InitialProcess $process -BrowserPath $browser -LaunchTime $launchTime
Set-Content -LiteralPath (Join-Path $Root ".stemmy.browser.pid") -Value $windowProcess.Id

try { $windowProcess.WaitForExit() } catch {}
Remove-Item -LiteralPath (Join-Path $Root ".stemmy.browser.pid") -Force -ErrorAction SilentlyContinue

# Give pagehide/sendBeacon and a quick refresh/navigation a chance to reconnect.
# The server only exits if no Stemmy page is still sending fresh heartbeats.
Start-Sleep -Seconds 5
try {
  Invoke-RestMethod -Uri "$Url/api/stemmy/shutdown" -Method Post -ContentType "application/json" -Body '{"only_if_idle":true}' -TimeoutSec 3 | Out-Null
} catch {}
