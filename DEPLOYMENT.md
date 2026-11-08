# Deployment

## Environments
- Python 3.11 (`.venv` via uv), Java 8+, Windows 10/11.
- Tools: `tools/bin/*.jar`, `tools/keys/*.pk8/.x509.pem` (git-ignored, fetch via `tools/scripts/setup.ps1` + `tools/reorganize.py`).

## Install
```bat
uv venv --python 3.11 --seed
uv pip install -r requirements.txt
```

## Run
- GUI: `python src/run_gui.py` (or `Run.bat`)
- CLI: `python src/main.py <apk> --mode <mode>`

## Verify
```bat
.venv\Scripts\python.exe -m pytest src/tests -q
.venv\Scripts\python.exe -m ruff check src
.venv\Scripts\python.exe -m mypy src --ignore-missing-imports
```

## Rollback
`git revert <commit>` then re-run install. Workspace/output is disposable (`workspace/` git-ignored).
