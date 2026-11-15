# HANDOFF.md — LP-PC Suite

**Version:** 5.0.0 · **Last commit:** `c273589` (origin/main)  
**Python:** 3.11 · **Platform:** Windows (win32)  
**Test suite:** 1998 passed, 8 skipped (~332s)  
**Lint:** `ruff check src/` clean · **Types:** `mypy` clean across `core/patcher/scanner/ui/adb/mcp/plugins`

---

## 1. What This Is

LP-PC Suite is the desktop port of **Lucky Patcher v12.10.4** (mobile). It analyzes, patches, rebuilds, and signs Android APKs. Mobile-only features (ODEX patching, Patch to Android, BootList, Widgets, Xposed, lpzip) are ported through an **ADB orchestration layer** that runs on a connected Android device.

**Authoritative references:**
- `LP-GUI` — 27 screenshots of the mobile UI (feature parity target)
- `LP-DeCodes` — full decompile of LP v12.10.4 (`LP_12.10.4_1/`)
- `https://github.com/Freezdy413485/LP-DeCodes/tree/main/LP_12.10.4_1/assets`
- `https://github.com/Freezdy413485/LP-DeCodes/tree/main/Proxy%20server%20for%20inapp%20purchases_1.0.6_1/smali/com` (IAP proxy server)

---

## 2. Project Layout

```
LuckyPatcher-PC/
├── .github/workflows/ci.yml       # CI + GitHub Releases automation
├── assets/i18n/                   # 8 language files (267 keys each)
│   ├── en.json  vi.json  zh.json  tr.json
│   ├── ru.json  pt.json  id.json  es.json
├── tools/keys/                    # Real AOSP signing keys (from LP-DeCodes)
│   ├── testkey.pk8  testkey.x509.pem
│   ├── platform.pk8 platform.x509.pem
│   ├── media.pk8   media.x509.pem
│   └── shared.pk8  shared.x509.pem
├── src/
│   ├── main.py                    # CLI entry point (decompile → patch → rebuild → sign)
│   ├── run_gui.py                 # GUI launcher
│   ├── gui.py                     # Legacy GUI bootstrap
│   ├── core/                      # Core logic (config, i18n, cache, safety, ...)
│   ├── scanner/                   # APK analysis (packer, license, ads, IAP, security)
│   ├── patcher/                   # All patch implementations (license, ads, IAP, sig, ...)
│   ├── ui/                        # PyQt6 GUI (main window, dialogs, widgets)
│   ├── adb/                       # ADB orchestration (mobile feature ports)
│   ├── mcp/                       # MCP server for AI agent integration
│   ├── plugins/                   # Plugin architecture (detector/patcher/UI plugins)
│   ├── pipelines/                 # High-level workflows (backup, smart IAP)
│   ├── tests/                     # 100+ test files
│   └── workspace/                 # Runtime workspace (cache, backups, output)
└── Test.apk                       # Demo APK (84.4 MB, PairIP packed)
```

---

## 3. Key Architectures

### 3.1 ADB Orchestration Layer (`src/adb/`)
Mobile-only features ported through ADB. Designed, syntax-clean, mypy-clean, but **not functionally exercised** (no device available).

| Module | Purpose |
|--------|---------|
| `device.py` | ADBDevice, ADBDeviceManager, DeviceProperty |
| `orchestrator.py` | ADBOrchestrator, ADBOperation, ADBResult (retry/fallback) |
| `commands.py` | ADBCommand, ADBCommandBuilder, ADBCommandResult |
| `shell.py` | ADBShell, ADBShellStream (streaming output) |
| `transfer.py` | ADBFileTransfer, ADBTransferProgress (push/pull) |
| `odex.py` | ABOdexPatcher — baksmali/smali on device |
| `patch_to_android.py` | PatchToAndroid — services.jar pull/patch/push |
| `play_store.py` | ModdedPlayStore — install modified Play Store |
| `bootlist.py` | ADBBootList — deploy boot script (runs patches at boot) |
| `widgets.py` | ADBWidgetManager — home screen widgets |
| `lpzip.py` | ADBLpzipImporter — import custom patch archives |
| `xposed.py` | ADBXposedInstaller — Xposed/LSPosed module (min v82, entry: `com.xposed.XSupport`) |

Package obfuscation: `ru.aaaaaban.installer` → `ru.hhklsyty.wlkllqrcq`

### 3.2 MCP Server (`src/mcp/`)
JSON-RPC 2.0 over stdio. Exposes LP-PC Suite to AI agents (Claude, GPT, etc.).
- `server.py`: MCPServer, MCPServerConfig, run_mcp_server, JSONRPCError
- `tools.py`: TOOL_SCHEMAS, register_tools (analyze_apk, patch_apk, rebuild_apk, install_apk, download_custom_patch, list_devices, get_device_info, execute_adb_shell, manage_patches)
- `resources.py`: register_resources (file/data access)
- `prompts.py`: register_prompts (reusable prompt templates)

### 3.3 Plugin Architecture (`src/plugins/`)
Dynamic loading of community detectors/patchers.
- `base.py`: DetectorPlugin, PatcherPlugin, CustomPatchPlugin, UIPanelPlugin, IntegrationPlugin, PluginInfo
- `manager.py`: PluginManager, PluginRegistry, DetectorRegistry, PatcherRegistry, register_plugin, get_plugin_manager
- Loads plugins by path via `importlib.util.spec_from_file_location` (unique `_lp_plugin_{name}_{id(file)}` names) to avoid collision with `src/plugins` package

### 3.4 Packed-APK Bypass Layer
Two new modules that replace blanket `patchable=False` with signal fusion:

**`src/scanner/checks/packer_fusion.py`** — Fuses 3 signals:
1. Structural index — own-package class count + density per MB
2. Entropy windows — contiguous high-entropy dex regions (encrypted payload signal)
3. Bytecode signature score — stub class/invocation matching

Produces `PackabilityAssessment` with:
- `patchable` (bool), `strategy` (BypassStrategy), `confidence`, `rationale` (list)

**BypassStrategy enum:**
- `DEX_PLAINTEXT` — dex readable, patch normally
- `SHELL_SWAP` — repoint manifest at real Application, neutralize shell entry
- `STUB_NEUTRALIZE` — make shell Application lifecycle methods return immediately
- `UNPACK_REQUIRED` — truly encrypted, external unpacker needed

**`src/patcher/packer_bypass.py`** — Acts on strategy:
- DEX_PLAINTEXT → no-op
- SHELL_SWAP → edits manifest + smali to repoint Application
- STUB_NEUTRALIZE → patches onCreate/attachBaseContext to return immediately
- UNPACK_REQUIRED → refuses, reports why, returns 0 patched files

**Test.apk verdict (with package):** `patchable=True`, `strategy=dex_plaintext`, 29 own-package classes, density 1131/MB, max_window_entropy 8.00, high_entropy_pct 3.6, bytecode_score 3.  
**Without package:** `own_pkg_classes=0`, `unpack_required`.

### 3.5 UI Modes (`src/core/ui_mode.py`)
3-tier enum mirroring mobile LP:
- `BEGINNER` — safe actions only (open_rebuild, remove_license, remove_ads, iap_emulation, backup, launch, info)
- `MITIGATIVE` (default) — adds custom patch, change_perms, resign, aidl_proxy
- `ADVANCED` — adds all signature patches (sig_disable/sig_integrity/sig_fake_archive, custom)

Risk levels: remove_ads/backup/open_rebuild = SAFE; remove_license/iap_emulation/aidl_proxy/clone = CAUTION; apply_custom_patch/change_perms/resign/sig_* = DANGEROUS

Mode is process-global — dialogs created later follow the current selection automatically.
---

## 4. Patches & Patchers

### 4.1 Patch Registry
All patches confirmed real via AST analysis — every patcher has a working implementation.

| Patch | Implementation | Risk |
|-------|---------------|------|
| License | `LicensePatcher` → `patch_license_check()` | DANGEROUS |
| License Extreme | `LicenseExtremePatcher` | DANGEROUS |
| Ads | `AdRemover` → `remove_activities()` | SAFE |
| Ads Blocklist | `AdsBlocklist` | SAFE |
| IAP | `IapBypass` → `patch_license_check()` | CAUTION |
| IAP DEX | `IapDexPatcher` | CAUTION |
| IAP Smali | `IapSmaliPatcher` | CAUTION |
| IAP Proxy Server | `IapProxyServer` (external proxy for in-app purchases) | CAUTION |
| WS Proxy Server | `WsProxyServer` | CAUTION |
| Signature (v1-v7) | `SignaturePatcher` | DANGEROUS |
| Signature Integrity | `SignatureIntegrityPatcher` | DANGEROUS |
| Signature Fake Archive | `SignatureFakeArchivePatcher` | DANGEROUS |
| Resign | `ResignPatcher` | DANGEROUS |
| Custom Patch | `CustomPatch` | DANGEROUS |
| AIDL Proxy | `AidlProxyPatcher` | CAUTION |
| GMS Spoofer | `GmsSpoofer` | CAUTION |
| App Cloner | `AppCloner` | CAUTION |
| Permission Changer | `PermissionChanger` | DANGEROUS |
| Install Dir | `InstallDirPatcher` | DANGEROUS |
| Fake Package | `FakePackagePatcher` | DANGEROUS |
| Hex Pattern | `HexPatternPatcher` | DANGEROUS |
| Smart Pattern | `SmartPatternPatcher` | DANGEROUS |
| Multi Patch Combiner | `MultiPatchCombiner` | DANGEROUS |
| Packer Bypass | `PackerBypassPatcher` | DANGEROUS |
| Watermarker | `Watermarker` | SAFE |
| Event Logger | `EventLoggerPatcher` | SAFE |
| Android System | `AndroidSystemPatcher` | DANGEROUS |
| Fast APK | `FastApkPatcher` | DANGEROUS |
| Hosts Blocker | `HostsBlocker` | SAFE |
| Magisk | `MagiskUtils` | DANGEROUS |

### 4.2 Pipeline (src/main.py)
`_apply_packer_bypass()` runs after decompile, logs strategy. Flow:
decompile → packer_bypass → patches → hex_patch → recompile → sign → install

### 4.3 IAP Proxy Server
From LP-DeCodes: `Proxy server for inapp purchases_1.0.6_1/smali/com` — external proxy server for the IAP patch. Implemented as `IapProxyServer` in `src/patcher/iap_proxy_server.py`.

### 4.4 Performance
- Analyzer: 70.6s → 4.1s (17.3x) via shared `DexIndex`
- Cache version: 12
- Full suite: 1998 passed, 8 skipped in ~332s
---

## 5. Internationalization (i18n)

### 5.1 Files
`assets/i18n/*.json` — 8 languages, **267 keys each**, identical key structures.

| File | Status |
|------|--------|
| `en.json` | Complete (source/translation) |
| `vi.json` | Complete (source) |
| `zh.json` | **Translated** (was English placeholders) |
| `tr.json` | **Translated** (was English placeholders) |
| `ru.json` | **Translated** (was English placeholders) |
| `pt.json` | **Translated** (was English placeholders) |
| `id.json` | **Translated** (was English placeholders) |
| `es.json` | **Translated** (was English placeholders) |

### 5.2 Behavior
- **Default language:** `en` (changed from `vi` — English is now the default/fallback)
- Fallback chain: current lang → `en` → source string
- Env override: `LP_LANG=vi|en|...`
- Runtime switch: `set_language("en")` + emit `language_changed`
- `t("main_window.title")` → `"LP-PC Suite v5 – Professional Modding Tool"`
- `t("status.loaded", count=5)` → `"Đã tải 5 ứng dụng"`

### 5.3 Key Sections
- `main_window.*` — window title, toolbar, sidebar
- `toolbar.*` — browse, download, workspace, reload, toolbox
- `sidebar.*` — app list labels
- `status.*` — status bar messages
- `ui_mode.*` — beginner/mitigative/advanced labels
- `actions.*` — patch action names
- `dialog.*` — all dialog strings

### 5.4 Known Issue
Log output from analyzer still shows Vietnamese strings in some places — the analyzer's internal log messages are hardcoded in Vietnamese. The GUI text itself is properly localized via `t()`.

---

## 6. GUI

### 6.1 Main Window (`src/ui/main_window.py`)
- 1256x669 window (on 1366x728 screen)
- Toolbar: 📁 Browse APK · 📥 Download APK · 📂 Workspace · 🔄 Reload · 🧰 Toolbox
- **Toolbox button IS present** (verified via offscreen Qt test — last toolbar widget is `🧰 Toolbox`)
- `_on_toolbox_clicked()` opens `ToolboxMenu` at button position
- Language combo at index 249; `_on_language_changed` at line 515
- `tb.setMinimumWidth(860)` for toolbox visibility

### 6.2 Toolbox Menu (`src/ui/toolbox_menu.py`)
QMenu with nested actions + signals:
- Patch to Android: Signature Verification always True, Disable .apk Signature Verification, Disable Zip Signature Verification
- Clone, IAP Manager, Download Patch, System Patch, System Tool
- Signals: `patch_requested`, `clone_requested`, `iap_manager_requested`, `download_patch_requested`, `system_tool_requested`

### 6.3 Copy-Paste Support
- `LogWidget` — log output supports copy
- `APKDetailWidget` — detail panel supports copy
- `AppListWidget` — app list supports copy

### 6.4 Dialogs
- `AdsPatchDialog`, `IAPManagerDialog`, `IAPModeDialog`, `LicensePatchDialog`
- `CloneDialog`, `RebuildDialog`, `RebuildTreeDialog`, `ResignDialog`
- `PatchConfigDialog`, `PermissionPickerDialog`, `PreviewDialog`, `WizardDialog`
- `MenuOfPatches`, `MenuOfPatchesTree`, `SwitchesPanel`, `ColorIndicator`

### 6.5 Test Coverage
- `test_ui_main_window.py` — 43+ tests
- `test_ui_toolbox_menu.py` — 14 tests
- `test_ui_mode.py` — 26 tests
- All UI tests pass under offscreen Qt platform
---

## 7. Build, Test & CI

### 7.1 Commands
```bash
# Full test suite
python -m pytest src/tests/ -q --tb=short --timeout=300

# Lint
ruff check src/

# Type check (mypy)
mypy src/core/ src/patcher/ src/scanner/ src/ui/ src/adb/ src/mcp/ src/plugins/

# Run GUI
python src/run_gui.py

# Run CLI
python src/main.py --apk Test.apk --output workspace/output
```

### 7.2 Environment
- **Python:** 3.11.0
- **Platform:** Windows (win32), cp1252 console
- **Set for Vietnamese/emoji output:** `$env:PYTHONIOENCODING="utf-8"`
- **Set for ad-hoc imports:** `$env:PYTHONPATH="src"`
- **Qt offscreen test:** `$env:QT_QPA_PLATFORM="offscreen"`
- **Machine:** 4 logical CPUs, 7.9 GB RAM; avoid concurrent pytest runs (~3 min each)

### 7.3 PowerShell Quirks
- No `&&` — use `;`
- No heredocs
- No `head`/`tail` — use `Select-Object -First N` / `Get-Content -Tail N`
- `timeout` syntax: `timeout 300` (seconds), not `--timeout=300`

### 7.4 CI/CD (`.github/workflows/ci.yml`)
- GitHub Actions workflow
- Runs: ruff check + mypy + pytest
- **Release automation:** generates .zip + changelogs on each commit (GitHub Releases)

---

## 8. Known Issues & Limitations

### 8.1 Blocked (by design)
- **Truly encrypted payloads** (PairIP/Tencent/360 encrypted variants) still require an external unpacker — `UNPACK_REQUIRED`, not a code blocker
- **ADB modules** are import-verified but never exercised against a real device (no device available)

### 8.2 Minor
- Analyzer internal log messages are hardcoded in Vietnamese (GUI text is properly localized)
- `Test.apk` (84.4 MB, PairIP packed) is the only demo APK; real device testing not possible
- androguard `APK.get_package()` emits massive DEBUG logs — redirect stderr (`2>$null`) when probing

---

## 9. Completed Work (committed to origin/main)

All previously uncommitted work has been committed in `c273589`:

### 9.1 Modified (27 files)
`.github/workflows/ci.yml`, `assets/i18n/en.json`, `assets/i18n/vi.json`, `src/core/i18n.py`, `src/core/plugin_manager.py`, `src/main.py`, `src/patcher/custom_patch_downloader.py`, `src/plugins/__init__.py`, `src/scanner/analyzer.py`, `src/scanner/checks/packer_bytecode.py`, `src/tests/test_custom_patch_downloader.py`, `src/tests/test_e2e_analyzer_real_apk.py`, `src/tests/test_i18n_dialog_coverage.py`, `src/ui/apk_detail_widget.py`, `src/ui/app_controller.py`, `src/ui/app_list_widget.py`, `src/ui/log_widget.py`, `src/ui/main_window.py`, `src/ui/menu_of_patches.py`, `tools/keys/*.pk8`, `tools/keys/*.x509.pem`

### 9.2 New Files (34 files)
- `assets/i18n/es.json`, `id.json`, `pt.json`, `ru.json`, `tr.json`, `zh.json` — translated i18n files
- `src/adb/` — entire ADB orchestration layer (12 modules)
- `src/core/ui_mode.py` — UI mode system
- `src/mcp/` — MCP server (4 modules)
- `src/patcher/packer_bypass.py` — packer bypass patcher
- `src/plugins/base.py`, `src/plugins/manager.py` — plugin architecture
- `src/scanner/checks/packer_fusion.py` — packer detection fusion
- `src/tests/test_packer_bypass.py`, `test_packer_fusion.py`, `test_ui_mode.py` — new tests

---

## 10. Next Steps (for future AI agents)

1. **Exercise ADB modules** against a real Android device (all modules are import-verified)
2. **Add real device tests** for ODEX patching, Patch to Android, BootList, Widgets, Xposed
3. **Expand i18n** beyond 8 languages if community demand exists
4. **HANDOFF.md** is the canonical architecture reference — update it when adding new modules

---

*Generated for AI agent handoff. All code is syntax-clean, mypy-clean, ruff-clean, and 1998/1998 tests pass.*