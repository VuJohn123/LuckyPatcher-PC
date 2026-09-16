"""Test ResignPatcher — mock subprocess, không chạy jarsigner thật."""
from unittest.mock import MagicMock, patch

from patcher.resign_patcher import ResignPatcher


def test_resign_with_testkey_success():
    with patch("patcher.resign_patcher.sign_apk") as mock_sign:
        mock_sign.return_value = "/tmp/app_signed.apk"
        p = ResignPatcher("/tmp/app.apk", log_callback=lambda *_: None)
        result = p.resign_with_testkey()
        assert result == "/tmp/app_signed.apk"


def test_resign_with_testkey_failure():
    with patch("patcher.resign_patcher.sign_apk") as mock_sign:
        mock_sign.side_effect = RuntimeError("signer failed")
        p = ResignPatcher("/tmp/app.apk", log_callback=lambda *_: None)
        result = p.resign_with_testkey()
        assert result is None


def test_patch_interface():
    with patch("patcher.resign_patcher.sign_apk") as mock_sign:
        mock_sign.return_value = "/tmp/signed.apk"
        p = ResignPatcher("/tmp/app.apk", log_callback=lambda *_: None)
        assert p.patch() == 1


def test_change_package_name_decompile_fails():
    with patch("core.apk_utils.decompile_apk") as mock_decomp:
        mock_decomp.side_effect = RuntimeError("fail")
        p = ResignPatcher("/tmp/app.apk", log_callback=lambda *_: None)
        result = p.change_package_name("com.new.app")
        assert result is None


def test_change_package_name_success():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        decomp = os.path.join(tmp, "decompiled")
        os.makedirs(decomp)

        manifest = os.path.join(decomp, "AndroidManifest.xml")
        with open(manifest, "w") as f:
            f.write('<manifest package="com.old.app"></manifest>')

        with patch("core.apk_utils.decompile_apk") as mock_decomp, \
             patch("core.apk_utils.recompile_apk") as mock_rec, \
             patch("patcher.resign_patcher.sign_apk") as mock_sign, \
             patch("patcher.resign_patcher.tempfile.mkdtemp", return_value=tmp), \
             patch("shutil.copy2"), \
             patch("shutil.rmtree"):

            def fake_decomp(apk, out, **kw):
                # Giả lập apktool đã giải nén manifest vào out
                os.makedirs(os.path.join(out), exist_ok=True)
                with open(os.path.join(out, "AndroidManifest.xml"), "w") as f:
                    f.write('<manifest package="com.old.app"></manifest>')

            mock_decomp.side_effect = fake_decomp
            mock_rec.return_value = "/tmp/out.apk"
            mock_sign.return_value = "/tmp/out_signed.apk"

            p = ResignPatcher("/tmp/app.apk", log_callback=lambda *_: None)
            p.change_package_name("com.new.app")
            # Không crash là đủ