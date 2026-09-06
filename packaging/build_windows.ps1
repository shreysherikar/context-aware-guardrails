$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

uv python install 3.12
uv sync --extra desktop --group package
uv run pyinstaller packaging/contextguard.spec --noconfirm --clean

$zip = Join-Path "dist" "ContextGuard-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path "dist" "ContextGuard") -DestinationPath $zip
Write-Host "Built $zip"
