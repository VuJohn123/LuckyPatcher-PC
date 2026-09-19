$ErrorActionPreference = "Stop"

Write-Host "`n=== Coverage ===" -ForegroundColor Cyan
pytest --cov=src --cov-report=term-missing

Write-Host "`n=== Quality audit ===" -ForegroundColor Cyan
python scripts/audit_quality.py

Write-Host "`n=== Security audit ===" -ForegroundColor Cyan
python scripts/audit_security.py