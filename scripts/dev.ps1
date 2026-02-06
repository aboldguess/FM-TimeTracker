<#!
.SYNOPSIS
    FM TimeTracker Windows development launcher.

.DESCRIPTION
    Ensures a local Python virtual environment exists, activates it, installs or
    upgrades dependencies from requirements.txt, and runs the FastAPI app with
    Uvicorn on the configured port. This script is intended as the preferred
    entry point for Windows-based local development.

.USAGE
    PS> $env:PORT=8000
    PS> .\scripts\dev.ps1

.NOTES
    - Runs from the repository root to keep paths consistent.
    - Uses $env:PORT when set; otherwise defaults to 8000.
#>

$ErrorActionPreference = "Stop"

Write-Host "[dev] Starting Windows development launcher..."

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPath = Join-Path $repoRoot ".venv"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvPath)) {
    Write-Host "[dev] Creating virtual environment at $venvPath"
    python -m venv .venv
}

if (-not (Test-Path $venvActivate)) {
    throw "[dev] Virtual environment activation script not found: $venvActivate"
}

Write-Host "[dev] Activating virtual environment"
. $venvActivate

Write-Host "[dev] Installing/upgrading dependencies"
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

$port = if ($env:PORT) { $env:PORT } else { "8000" }
Write-Host "[dev] Launching Uvicorn on port $port"

uvicorn app.main:app --host 0.0.0.0 --port $port --reload
