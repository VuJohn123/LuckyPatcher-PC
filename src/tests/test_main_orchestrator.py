"""Test src/main.py orchestrator — mock tất cả external."""
import os
import zipfile
from unittest.mock import MagicMock, patch

import pytest


# Import lazy — main.py import nặng
def _import_main():
    import importlib
    import main as main_mod
    importlib.reload(main_mod)
    return main_mod


def _make_apk(tmp_path) -> str:
    apk = tmp_path / "test.apk"
    with zipfile.ZipFile(apk, "w") as z:
        z.writestr("AndroidManifest.xml", b"<manifest/>")
        z.writestr("classes.dex", b"\x00" * 10)
    return str(apk)


# ============================================================
# _emit_step
# ============================================================
def test_emit_step_without_signals():
    from main import _emit_step
    logs = []
    _emit_step(None, "Test step", 50, logs.append)
    assert any("50" in l and "Test step" in l for l in logs)


def test_emit_step_with_signals():
    from main import _emit_step
    signals = MagicMock()
    logs = []
    _emit_step(signals, "Test", 75, logs.append)
    signals.step.emit.assert_called_once_with("Test", 75)
    assert any("Test" in l for l in logs)


def test_emit_step_signal_failure_isolated():
    """Signal emit lỗi → không crash."""
    from main import _emit_step
    signals = MagicMock()
    signals.step.emit.side_effect = RuntimeError("signal broken")
    logs = []
    _emit_step(signals, "Test", 50, logs.append)
    assert any("Test" in l for l in logs)


# ============================================================
# _record_metric
# ============================================================
def test_record_metric_success():
    from main import _record_metric
    with patch("core.metrics.get_metrics") as mock_get:
        _record_metric(
            "test.apk", "license", True, 1.5, patches=3
        )
        # Không crash; get_metrics được gọi
        assert mock_get.called


def test_record_metric_failure_isolated():
    """Lỗi trong metrics không lan ra."""
    from main import _record_metric
    with patch(
        "core.metrics.get_metrics", side_effect=Exception("boom")
    ):
        _record_metric("x.apk", "m", True, 1.0)  # Không raise


# ============================================================
# run_pipeline — validation failures
# ============================================================
def test_run_pipeline_invalid_input(tmp_path):
    from main import run_pipeline
    with patch(
        "main.normalize_input",
        side_effect=ValueError("bad input"),
    ):
        success, out, reports = run_pipeline(
            str(tmp_path / "nonexistent.apk"),
            mode="license",
            log_callback=lambda *_: None,
            config={"conversion": {}},
        )
        assert success is False
        assert out is None
        assert reports == {}


def test_run_pipeline_no_modes(tmp_path):
    """Mode rỗng → fail sớm."""
    from main import run_pipeline
    apk = _make_apk(tmp_path)
    with patch(
        "main.normalize_input", return_value=apk
    ):
        success, out, _ = run_pipeline(
            apk, mode="", log_callback=lambda *_: None,
            config={"conversion": {}, "pipeline": {}},
        )
        assert success is False


# ============================================================
# run_pipeline — full success path (all external mocked)
# ============================================================
def test_run_pipeline_full_success(tmp_path):
    """Full pipeline với mọi external mock."""
    from main import run_pipeline
    apk = _make_apk(tmp_path)
    output_apk = str(tmp_path / "output" / "patched.apk")
    os.makedirs(os.path.dirname(output_apk), exist_ok=True)

    # Tạo output giả để os.path.exists pass
    with open(output_apk, "w") as f:
        f.write("fake")

    with patch("main.normalize_input", return_value=apk), \
         patch(
             "core.pipeline_executor.execute_modes",
             return_value=(["license patched"], {"license": {}}),
         ), \
         patch(
             "core.smali_utils.FileContentCache"
         ) as mock_cache, \
         patch(
             "core.pipeline_executor.set_file_cache"
         ), \
         patch("core.apk_utils.decompile_apk"), \
         patch(
             "core.apk_utils.recompile_apk",
             side_effect=lambda d, o, **kw: open(o, "w").close() or o,
         ), \
         patch(
             "core.apk_utils.sign_apk",
             return_value=output_apk,
         ), \
         patch("core.device_bridge.install_apk"), \
         patch("core.patch_history.PatchHistory"), \
         patch("patcher.watermarker.Watermarker.add_watermark"), \
         patch("scanner.analyzer.AppDeepAnalyzer"), \
         patch("scanner.ad_scanner.AdScanner"):
        # Mock cache instance
        mock_cache.return_value.flush = MagicMock()

        success, out, _ = run_pipeline(
            apk,
            mode="license",
            log_callback=lambda *_: None,
            config={
                "conversion": {"auto_convert_xapk": True},
                "pipeline": {},
                "logging": {"level": "INFO", "file": str(tmp_path / "log.log")},
            },
        )
        assert success is True
        assert out is not None


def test_run_pipeline_catches_exception(tmp_path):
    """Exception trong decompile → trả về (False, None, {})."""
    from main import run_pipeline
    apk = _make_apk(tmp_path)

    with patch("main.normalize_input", return_value=apk), \
         patch(
             "core.apk_utils.decompile_apk",
             side_effect=RuntimeError("decompile boom"),
         ), \
         patch("scanner.analyzer.AppDeepAnalyzer"), \
         patch("core.patch_history.PatchHistory"), \
         patch("core.smali_utils.FileContentCache"), \
         patch("core.pipeline_executor.set_file_cache"):
        success, out, reports = run_pipeline(
            apk, mode="license",
            log_callback=lambda *_: None,
            config={
                "conversion": {},
                "pipeline": {},
                "logging": {"file": str(tmp_path / "log.log")},
            },
        )
        assert success is False
        assert out is None
        assert reports == {}


# ============================================================
# main() — CLI
# ============================================================
def test_main_no_args_prints_help(capsys):
    """Không có arg → in help, return 1."""
    import sys
    from main import main
    with patch.object(sys, "argv", ["lp-pc-suite"]):
        rc = main()
        assert rc == 1


def test_main_with_invalid_apk(tmp_path):
    """APK không tồn tại → pipeline fail, return 1."""
    import sys
    from main import main
    with patch.object(
        sys, "argv",
        ["lp-pc-suite", str(tmp_path / "nonexistent.apk"),
         "--mode", "license"],
    ):
        rc = main()
        assert rc == 1


def test_main_success_returns_0(tmp_path):
    import sys
    from main import main
    apk = _make_apk(tmp_path)

    with patch.object(
        sys, "argv",
        ["lp-pc-suite", apk, "--mode", "license"],
    ), patch("main.run_pipeline", return_value=(True, "/out.apk", {})):
        rc = main()
        assert rc == 0


def test_main_custom_patch_env(tmp_path, monkeypatch):
    """--custom-patch set env var."""
    import sys
    from main import main
    apk = _make_apk(tmp_path)
    patch_file = tmp_path / "patch.txt"
    patch_file.write_text("x")

    monkeypatch.delenv("LP_CUSTOM_PATCH", raising=False)

    with patch.object(
        sys, "argv",
        ["lp-pc-suite", apk, "--mode", "custom",
         "--custom-patch", str(patch_file)],
    ), patch("main.run_pipeline", return_value=(True, "/out.apk", {})):
        main()
        assert os.environ.get("LP_CUSTOM_PATCH") == str(patch_file)


def test_main_verbose_sets_debug(tmp_path):
    import sys
    from main import main
    apk = _make_apk(tmp_path)

    with patch.object(
        sys, "argv",
        ["lp-pc-suite", apk, "--mode", "license", "-v"],
    ), patch("main.run_pipeline") as mock_run:
        mock_run.return_value = (True, "/out.apk", {})
        main()
        # Verify config có level DEBUG
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["config"]["logging"]["level"] == "DEBUG"