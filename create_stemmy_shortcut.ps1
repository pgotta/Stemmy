param(
    [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Stemmy.lnk"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
$launcher = Join-Path $rootPath "stemmy_launcher.vbs"
$icon = Join-Path $rootPath "stemmy.ico"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Missing launcher: $launcher"
}
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Missing icon: $icon"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscript
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $rootPath
$shortcut.IconLocation = $icon + ",0"
$shortcut.Description = "Open Stemmy separation studio"
$shortcut.Save()

Write-Host ""
Write-Host "[OK] Stemmy shortcut created on your desktop." -ForegroundColor Green
Write-Host "     $shortcutPath"
