$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

Write-Host "`nAttendX Flet — Windows setup" -ForegroundColor Cyan
Write-Host "Project folder: $PSScriptRoot"

$requiredFiles = @('main.py', 'requirements.txt', 'requirements-desktop.txt', '.env.example')
$missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_)) })
if ($missing.Count -gt 0) {
    Write-Host "This is not the project root. Missing: $($missing -join ', ')" -ForegroundColor Red
    Write-Host 'Extract AttendX_Flet_Complete.zip, then run this script from the AttendX_Flet folder.'
    exit 2
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        foreach ($version in @('3.13', '3.12', '3.11')) {
            & $pyCommand.Source "-$version" --version *> $null
            if ($LASTEXITCODE -eq 0) {
                $pythonSelector = "-$version"
                break
            }
        }
        if ($pythonSelector) {
            & $pyCommand.Source $pythonSelector -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv using the Python Launcher.' }
        }
    }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        Write-Host 'Python 3.11 or newer was not found. Install 64-bit Python 3.12, enable Add Python to PATH, then reopen PowerShell.' -ForegroundColor Red
        exit 3
    }
} else {
    $versionOutput = & $pythonCommand.Source --version
    Write-Host "Detected $versionOutput"
    $versionLine = (& $pythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    $parts = $versionLine.Split('.')
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if (($major -lt 3) -or (($major -eq 3) -and ($minor -lt 11))) {
        throw "Python 3.11 or newer is required; found $versionOutput."
    }
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        & $pythonCommand.Source -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'The virtual-environment Python executable was not created.'
}

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example. Add your own Supabase URL/key when ready.' -ForegroundColor Yellow
}

Write-Host "`nInstalling core packages and desktop camera support..." -ForegroundColor Cyan
& $venvPython -m pip install --disable-pip-version-check --retries 2 --timeout 20 -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nDependency installation failed." -ForegroundColor Red
    Write-Host 'If the error mentions pypi.org, DNS, proxy, or network access, reconnect to the internet (or use a hotspot) and run this script again.' -ForegroundColor Yellow
    Write-Host 'No virtual-environment activation is needed. Your .venv and .env have been kept.'
    exit 4
}

Write-Host "`nCore/desktop dependencies installed." -ForegroundColor Green
Write-Host 'Optional face recognition package (may need dlib/C++ build tools): requirements-face.txt'
Write-Host 'Optional serial fingerprint reader package: requirements-fingerprint.txt'
Write-Host "`nNext: double-click Run_AttendX.bat or run .\.venv\Scripts\python.exe main.py" -ForegroundColor Cyan
Write-Host 'Real login and attendance require Supabase migrations, deployed Edge Functions, and your project settings.' -ForegroundColor Yellow
