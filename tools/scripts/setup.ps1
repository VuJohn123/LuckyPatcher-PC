#Requires -Version 5.0
$ErrorActionPreference = "Stop"

Write-Host "=== LP-PC Suite Setup ===" -ForegroundColor Cyan

# 1. Python check
$py = (python --version 2>&1) -replace "Python ", ""
if (-not $py.StartsWith("3.1")) {
    Write-Error "Python 3.11+ required, found: $py"
}
Write-Host "[OK] Python $py"

# 2. Create venv
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Creating venv..."
    uv venv --python 3.11 --seed
}
Write-Host "[OK] Venv ready"

# 3. Install deps
Write-Host "[*] Installing dependencies..."
uv pip sync requirements.txt
uv pip install pytest pytest-cov pytest-timeout pytest-qt
Write-Host "[OK] Deps installed"

# 4. Windows Defender exclusion (CRITICAL)
$wsPath = (Resolve-Path "workspace" -ErrorAction SilentlyContinue).Path
$toolsPath = (Resolve-Path "tools" -ErrorAction SilentlyContinue).Path
if ($wsPath) {
    Write-Host "[*] Adding Defender exclusion for workspace..."
    Add-MpPreference -ExclusionPath $wsPath -ErrorAction SilentlyContinue
}
if ($toolsPath) {
    Write-Host "[*] Adding Defender exclusion for tools..."
    Add-MpPreference -ExclusionPath $toolsPath -ErrorAction SilentlyContinue
}

# 5. Verify
Write-Host "[*] Running smoke test..."
pytest src/tests/test_trace_context.py -v --no-header -q

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Activate: .\.venv\Scripts\Activate.ps1"