# LuckyPatcher-PC

Unofficial native-PC adaptation of Lucky Patcher. No Android emulator needed. Static APK patcher for education / reverse-engineering research. Not affiliated with ChelpuS.

## Setup

```bat
uv venv --python 3.11 --seed
uv pip install -r requirements.txt
uv pip install pytest pytest-cov pytest-timeout pytest-qt
```

Tools (apktool, smali, signer, keys) are in `tools/bin/` and `tools/keys/`. Requires Java 8+, adb optional.

## Usage

```bat
Run.bat                 GUI
Run.bat test            pytest
Run.bat cli app.apk --mode license:auto,iap:dex --verbose
Run.bat e2e             tools/scripts/e2e_test.py <apk>
```

CLI: `python src/main.py <apk> --mode <mode> [--key-type testkey|platform|media|shared] [--fast] [--gda] [--clean] [--no-safety]`

Modes: `license:*`, `ads:*`, `iap:*`, `signature:*`, `resign:*`, `perms:change`, `backup`, `clone`, `gms_spoof`, `event_logger`. Full map: `src/core/mode_registry.py`. Config: `config/default.yaml` (6-layer precedence: CLI > env `LP_*` > preset > user yaml > default > auto-tune).

## Test / Lint

```bat
.pytest -v            src/tests
ruff check src
mypy src --ignore-missing-imports
```

## Disclaimer

Use responsibly. Static patching only — patched apps may need reinstall, data loss possible.
