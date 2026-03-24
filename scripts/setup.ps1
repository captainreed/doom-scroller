# Instagram Reels Daily Digest - Setup Script (PowerShell)
# Run this script once to set up all dependencies

$ErrorActionPreference = "Continue"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Instagram Reels Daily Digest Setup ===" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"
Write-Host ""

# Check Node.js
Write-Host "Checking Node.js..." -ForegroundColor Yellow
$nodeVersion = $null
try {
    $nodeVersion = & node --version 2>$null
    if ($nodeVersion) {
        Write-Host "Node.js found: $nodeVersion" -ForegroundColor Green
    }
} catch {}

if (-not $nodeVersion) {
    Write-Host "Node.js not found! Please install Node.js from https://nodejs.org/" -ForegroundColor Red
    Write-Host "After installing, restart PowerShell and run this script again." -ForegroundColor Yellow
    exit 1
}

# Check Python - try multiple methods
Write-Host "Checking Python..." -ForegroundColor Yellow
$pythonCmd = $null
$pythonVersion = $null

# Try 'py' launcher first (Windows Python Launcher)
try {
    $pythonVersion = & py --version 2>$null
    if ($pythonVersion) {
        $pythonCmd = "py"
        Write-Host "Python found (via py launcher): $pythonVersion" -ForegroundColor Green
    }
} catch {}

# Try 'python3' if py didn't work
if (-not $pythonCmd) {
    try {
        $pythonVersion = & python3 --version 2>$null
        if ($pythonVersion) {
            $pythonCmd = "python3"
            Write-Host "Python found: $pythonVersion" -ForegroundColor Green
        }
    } catch {}
}

# Try 'python' last
if (-not $pythonCmd) {
    try {
        $pythonVersion = & python --version 2>$null
        if ($pythonVersion -and $pythonVersion -notlike "*was not found*") {
            $pythonCmd = "python"
            Write-Host "Python found: $pythonVersion" -ForegroundColor Green
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "Python not found!" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.11+ from: https://python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "IMPORTANT during installation:" -ForegroundColor Cyan
    Write-Host "  - Check 'Add Python to PATH'" -ForegroundColor White
    Write-Host "  - Check 'Install py launcher for all users'" -ForegroundColor White
    Write-Host ""
    Write-Host "After installing, RESTART PowerShell and run this script again." -ForegroundColor Yellow
    Write-Host ""

    # Still continue with Node.js setup
    Write-Host "Continuing with Node.js setup (you can install Python later)..." -ForegroundColor Yellow
    Write-Host ""
}

# Install browser agent dependencies
Write-Host "=== Installing Browser Agent Dependencies ===" -ForegroundColor Yellow
Set-Location "$ProjectRoot\browser-agent"

# Clean up old node_modules if exists (to avoid permission issues)
if (Test-Path "node_modules") {
    Write-Host "Cleaning up old node_modules..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
}

# Clean npm cache
Write-Host "Cleaning npm cache..." -ForegroundColor Yellow
npm cache clean --force 2>$null

# Install dependencies
Write-Host "Installing npm packages..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "npm install had some issues, but continuing..." -ForegroundColor Yellow
}

# Install Playwright browsers
Write-Host "Installing Playwright browsers..." -ForegroundColor Yellow
npx playwright install chromium

Write-Host ""

# Install Python dependencies if Python is available
if ($pythonCmd) {
    Write-Host "=== Installing Python Dependencies ===" -ForegroundColor Yellow
    Set-Location "$ProjectRoot\analysis-worker"

    # Create virtual environment if it doesn't exist
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment..." -ForegroundColor Yellow
        & $pythonCmd -m venv .venv
    }

    # Activate and install
    Write-Host "Installing Python packages..." -ForegroundColor Yellow
    & "$ProjectRoot\analysis-worker\.venv\Scripts\python.exe" -m pip install --upgrade pip
    & "$ProjectRoot\analysis-worker\.venv\Scripts\pip.exe" install -r requirements.txt

    Write-Host ""

    # Initialize database
    Write-Host "=== Initializing Database ===" -ForegroundColor Yellow
    & "$ProjectRoot\analysis-worker\.venv\Scripts\python.exe" -m app.main init-db
} else {
    Write-Host "Skipping Python setup (Python not installed)" -ForegroundColor Yellow
    Write-Host "Install Python and run this script again to complete setup." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Make sure your API key is in: $ProjectRoot\api key.txt"
if (-not $pythonCmd) {
    Write-Host "2. Install Python from https://python.org and run this script again" -ForegroundColor Red
    Write-Host "3. Then run the daily pipeline: .\scripts\run_daily.ps1"
} else {
    Write-Host "2. Run the daily pipeline: .\scripts\run_daily.ps1"
    Write-Host "3. On first run, log into Instagram in the browser window that opens"
}
Write-Host ""

# Return to project root
Set-Location $ProjectRoot
