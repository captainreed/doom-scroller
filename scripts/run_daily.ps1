# Instagram Reels Daily Digest - Daily Run Script (PowerShell)
# This script runs the full daily pipeline:
# 1. Collect reels using the browser agent
# 2. Analyze collected reels
# 3. Generate daily report

$ErrorActionPreference = "Continue"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Instagram Reels Daily Digest ===" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host ""

# Step 1: Run browser agent to collect reels
Write-Host "=== Step 1: Collecting Reels ===" -ForegroundColor Yellow
Set-Location "$ProjectRoot\browser-agent"

$collectionSuccess = $false
try {
    npm run dev
    $collectionSuccess = $true
    Write-Host "Reel collection complete!" -ForegroundColor Green
} catch {
    Write-Host "Warning: Browser agent encountered an error. Continuing with analysis..." -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Run analysis and report generation
Write-Host "=== Step 2: Analyzing Reels & Generating Report ===" -ForegroundColor Yellow
Set-Location "$ProjectRoot\analysis-worker"

$pythonExe = "$ProjectRoot\analysis-worker\.venv\Scripts\python.exe"

if (Test-Path $pythonExe) {
    try {
        & $pythonExe -m app.main run-daily
        Write-Host "Analysis and report generation complete!" -ForegroundColor Green
    } catch {
        Write-Host "Error during analysis: $_" -ForegroundColor Red
    }
} else {
    Write-Host "Python virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run .\scripts\setup.ps1 first" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Daily Pipeline Complete ===" -ForegroundColor Cyan

# Return to project root
Set-Location $ProjectRoot
