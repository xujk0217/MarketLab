# MarketLab Dashboard launcher - works from any working directory.
# Usage:  .\run_dashboard.ps1   (or right-click -> Run with PowerShell)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$streamlit = Join-Path $repoRoot ".venv\Scripts\streamlit.exe"
if (-not (Test-Path $streamlit)) {
    Write-Host "[MarketLab] venv not found - creating it first..." -ForegroundColor Yellow
    python -m venv .venv
    & (Join-Path $repoRoot ".venv\Scripts\pip.exe") install -e ".[dev,dashboard]"
}

Write-Host "[MarketLab] starting dashboard at http://localhost:8501 (Ctrl+C to stop)" -ForegroundColor Cyan
& $streamlit run app/dashboard.py
