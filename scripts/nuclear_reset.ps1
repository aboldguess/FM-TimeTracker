<#
.SYNOPSIS
    Nuclear local reset for FM TimeTracker (Windows).

.DESCRIPTION
    Destroys local development state (.venv, .env, SQLite databases, Python
    cache artifacts) and then runs scripts/setup.ps1 to rebuild from scratch.
    This is intended for severe local-environment corruption only.

.USAGE
    PS> .\scripts\nuclear_reset.ps1 -ConfirmReset
#>

[CmdletBinding()]
param(
    [switch]$ConfirmReset
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmReset) {
    Write-Host "[nuclear-reset] Refusing to run without explicit confirmation."
    Write-Host ""
    Write-Host "This command permanently deletes LOCAL DEVELOPMENT state:"
    Write-Host "  - .venv"
    Write-Host "  - .env"
    Write-Host "  - SQLite database files (*.db / *.sqlite / *.sqlite3)"
    Write-Host "  - Python cache folders"
    Write-Host ""
    Write-Host "If you are sure, run:"
    Write-Host "  .\scripts\nuclear_reset.ps1 -ConfirmReset"
    exit 1
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "[nuclear-reset] Repository root: $repoRoot"
Write-Host "[nuclear-reset] Starting destructive local reset..."

if (Test-Path ".venv") {
    Remove-Item ".venv" -Recurse -Force
}
if (Test-Path ".env") {
    Remove-Item ".env" -Force
}

Get-ChildItem -Path . -Recurse -File -Include *.db,*.sqlite,*.sqlite3 |
    ForEach-Object {
        Write-Host "[nuclear-reset] deleting $($_.FullName)"
        Remove-Item $_.FullName -Force
    }

Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ |
    ForEach-Object {
        Write-Host "[nuclear-reset] deleting $($_.FullName)"
        Remove-Item $_.FullName -Recurse -Force
    }

Get-ChildItem -Path . -Recurse -File -Filter *.pyc |
    ForEach-Object {
        Remove-Item $_.FullName -Force
    }

& ".\scripts\setup.ps1"

Write-Host "[nuclear-reset] Complete. Start the app with .\scripts\dev.ps1"
